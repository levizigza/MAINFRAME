"""Deduplication — duplicate events create at most one intended run."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.config import STATE_DIR, ensure_state

DB_NAME = "freeforge_triggers.sqlite"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class TriggerStore:
    def __init__(self, path: Path | None = None) -> None:
        ensure_state()
        self.path = path or (STATE_DIR / DB_NAME)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _migrate(self) -> None:
        conn = self._connect()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS bindings (
              binding_id TEXT PRIMARY KEY,
              source TEXT NOT NULL,
              job_id TEXT NOT NULL,
              permission_scope TEXT NOT NULL,
              filter_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS seen_events (
              dedupe_key TEXT PRIMARY KEY,
              event_id TEXT NOT NULL,
              binding_id TEXT,
              run_id TEXT,
              seen_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS webhook_nonces (
              nonce TEXT PRIMARY KEY,
              seen_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS debounce (
              watch_key TEXT PRIMARY KEY,
              last_fire_at TEXT NOT NULL,
              pending_fingerprint TEXT
            );
            """
        )
        conn.commit()
        conn.close()

    def register_binding(
        self,
        *,
        binding_id: str,
        source: str,
        job_id: str,
        permission_scope: str,
        filter_spec: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        conn = self._connect()
        conn.execute(
            """
            INSERT OR REPLACE INTO bindings(
              binding_id, source, job_id, permission_scope, filter_json, created_at
            ) VALUES (?,?,?,?,?,?)
            """,
            (
                binding_id,
                source,
                job_id,
                permission_scope,
                json.dumps(filter_spec or {}),
                _utc(),
            ),
        )
        conn.commit()
        conn.close()
        return self.get_binding(binding_id) or {}

    def get_binding(self, binding_id: str) -> dict[str, Any] | None:
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM bindings WHERE binding_id=?", (binding_id,)
        ).fetchone()
        conn.close()
        if not row:
            return None
        return {
            "binding_id": row["binding_id"],
            "source": row["source"],
            "job_id": row["job_id"],
            "permission_scope": row["permission_scope"],
            "filter": json.loads(row["filter_json"] or "{}"),
            "created_at": row["created_at"],
        }

    def claim_event(self, event: dict[str, Any], *, run_id: str | None = None) -> dict[str, Any]:
        """Return first=True only once per dedupe_key."""
        key = event["dedupe_key"]
        conn = self._connect()
        existing = conn.execute(
            "SELECT dedupe_key, run_id FROM seen_events WHERE dedupe_key=?", (key,)
        ).fetchone()
        if existing:
            conn.close()
            return {
                "first": False,
                "duplicate": True,
                "dedupe_key": key,
                "prior_run_id": existing["run_id"],
            }
        conn.execute(
            """
            INSERT INTO seen_events(dedupe_key, event_id, binding_id, run_id, seen_at)
            VALUES (?,?,?,?,?)
            """,
            (
                key,
                event.get("event_id"),
                event.get("binding_id"),
                run_id,
                _utc(),
            ),
        )
        conn.commit()
        conn.close()
        return {"first": True, "duplicate": False, "dedupe_key": key, "run_id": run_id}

    def nonce_seen(self, nonce: str) -> bool:
        conn = self._connect()
        row = conn.execute(
            "SELECT nonce FROM webhook_nonces WHERE nonce=?", (nonce,)
        ).fetchone()
        if row:
            conn.close()
            return True
        conn.execute(
            "INSERT INTO webhook_nonces(nonce, seen_at) VALUES (?,?)",
            (nonce, _utc()),
        )
        conn.commit()
        conn.close()
        return False

    def debounce_allow(
        self,
        watch_key: str,
        fingerprint: str,
        *,
        window_ms: int = 500,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Debounce file storms — coalesce rapid identical/nearby fires."""
        now = now or datetime.now(timezone.utc)
        conn = self._connect()
        row = conn.execute(
            "SELECT last_fire_at, pending_fingerprint FROM debounce WHERE watch_key=?",
            (watch_key,),
        ).fetchone()
        if row:
            try:
                last = datetime.fromisoformat(row["last_fire_at"].replace("Z", "+00:00"))
            except ValueError:
                last = now
            delta_ms = (now - last).total_seconds() * 1000
            if delta_ms < window_ms:
                conn.execute(
                    "UPDATE debounce SET pending_fingerprint=? WHERE watch_key=?",
                    (fingerprint, watch_key),
                )
                conn.commit()
                conn.close()
                return {
                    "allow": False,
                    "reason": "debounced",
                    "delta_ms": delta_ms,
                    "window_ms": window_ms,
                }
        conn.execute(
            """
            INSERT INTO debounce(watch_key, last_fire_at, pending_fingerprint)
            VALUES (?,?,?)
            ON CONFLICT(watch_key) DO UPDATE SET
              last_fire_at=excluded.last_fire_at,
              pending_fingerprint=excluded.pending_fingerprint
            """,
            (watch_key, now.isoformat(), fingerprint),
        )
        conn.commit()
        conn.close()
        return {"allow": True, "reason": "ok"}
