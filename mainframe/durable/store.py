"""Durable SQLite store for tasks, checkpoints, leases, and effect receipts."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.config import STATE_DIR, ensure_state
from mainframe.durable.states import ALL_STATES, can_transition, transition

DB_NAME = "durable_tasks.sqlite"
_LOCK = threading.Lock()


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def db_path() -> Path:
    ensure_state()
    return STATE_DIR / DB_NAME


def connect(path: Path | None = None) -> sqlite3.Connection:
    p = path or db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS tasks (
          operation_id TEXT PRIMARY KEY,
          freeforge_record_id TEXT NOT NULL,
          engine TEXT NOT NULL,
          destination TEXT NOT NULL,
          state TEXT NOT NULL,
          goal TEXT,
          idempotency_key TEXT,
          lease_owner TEXT,
          lease_until TEXT,
          checkpoint_json TEXT,
          effect_receipt_json TEXT,
          engine_status_json TEXT,
          error TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS transitions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          operation_id TEXT NOT NULL,
          from_state TEXT NOT NULL,
          to_state TEXT NOT NULL,
          reason TEXT,
          at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS effect_sink (
          idempotency_key TEXT PRIMARY KEY,
          operation_id TEXT NOT NULL,
          effect_id TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          applied_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_tasks_state ON tasks(state);
        CREATE INDEX IF NOT EXISTS idx_tasks_ff ON tasks(freeforge_record_id);
        """
    )
    conn.commit()


def new_operation_id() -> str:
    return f"op_{uuid.uuid4().hex}"


def new_freeforge_record_id() -> str:
    return f"ff_{uuid.uuid4().hex[:16]}"


class DurableStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or db_path()

    def create_task(
        self,
        *,
        goal: str,
        engine: str,
        destination: str = "local_effect_sink",
        idempotency_key: str | None = None,
        operation_id: str | None = None,
        freeforge_record_id: str | None = None,
    ) -> dict[str, Any]:
        oid = operation_id or new_operation_id()
        ffid = freeforge_record_id or new_freeforge_record_id()
        now = _utc()
        with _LOCK:
            conn = connect(self.path)
            conn.execute(
                """
                INSERT INTO tasks(
                  operation_id, freeforge_record_id, engine, destination, state,
                  goal, idempotency_key, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (oid, ffid, engine, destination, "planned", goal, idempotency_key, now, now),
            )
            conn.execute(
                "INSERT INTO transitions(operation_id, from_state, to_state, reason, at) VALUES (?,?,?,?,?)",
                (oid, "none", "planned", "create", now),
            )
            conn.commit()
            conn.close()
        return self.get(oid)  # type: ignore[return-value]

    def get(self, operation_id: str) -> dict[str, Any] | None:
        conn = connect(self.path)
        row = conn.execute("SELECT * FROM tasks WHERE operation_id=?", (operation_id,)).fetchone()
        conn.close()
        return self._row(row) if row else None

    def list_by_state(self, state: str) -> list[dict[str, Any]]:
        conn = connect(self.path)
        rows = conn.execute("SELECT * FROM tasks WHERE state=?", (state,)).fetchall()
        conn.close()
        return [self._row(r) for r in rows]

    def transition(
        self,
        operation_id: str,
        to_state: str,
        *,
        reason: str = "",
        error: str | None = None,
        checkpoint: dict[str, Any] | None = None,
        effect_receipt: dict[str, Any] | None = None,
        engine_status: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with _LOCK:
            conn = connect(self.path)
            row = conn.execute(
                "SELECT * FROM tasks WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if not row:
                conn.close()
                return {"ok": False, "error": "unknown_operation"}
            current = row["state"]
            tr = transition(current, to_state)
            if not tr["ok"]:
                conn.close()
                return tr
            now = _utc()
            fields = ["state=?", "updated_at=?"]
            vals: list[Any] = [to_state, now]
            if error is not None:
                fields.append("error=?")
                vals.append(error)
            if checkpoint is not None:
                fields.append("checkpoint_json=?")
                vals.append(json.dumps(checkpoint))
            if effect_receipt is not None:
                fields.append("effect_receipt_json=?")
                vals.append(json.dumps(effect_receipt))
            if engine_status is not None:
                fields.append("engine_status_json=?")
                vals.append(json.dumps(engine_status))
            vals.append(operation_id)
            conn.execute(
                f"UPDATE tasks SET {', '.join(fields)} WHERE operation_id=?",
                vals,
            )
            conn.execute(
                "INSERT INTO transitions(operation_id, from_state, to_state, reason, at) VALUES (?,?,?,?,?)",
                (operation_id, current, to_state, reason, now),
            )
            conn.commit()
            conn.close()
        out = self.get(operation_id)
        return {"ok": True, "task": out, **tr}

    def save_checkpoint(self, operation_id: str, checkpoint: dict[str, Any]) -> dict[str, Any]:
        with _LOCK:
            conn = connect(self.path)
            conn.execute(
                "UPDATE tasks SET checkpoint_json=?, updated_at=? WHERE operation_id=?",
                (json.dumps(checkpoint), _utc(), operation_id),
            )
            conn.commit()
            conn.close()
        return {"ok": True, "operation_id": operation_id, "checkpoint": checkpoint}

    def acquire_lease(
        self,
        operation_id: str,
        owner: str,
        *,
        ttl_seconds: int = 30,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        stamp = now or datetime.now(timezone.utc)
        until = datetime.fromtimestamp(stamp.timestamp() + ttl_seconds, tz=timezone.utc).isoformat()
        with _LOCK:
            conn = connect(self.path)
            row = conn.execute(
                "SELECT lease_owner, lease_until, state FROM tasks WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if not row:
                conn.close()
                return {"ok": False, "error": "unknown_operation"}
            existing_until = row["lease_until"]
            existing_owner = row["lease_owner"]
            if existing_owner and existing_until:
                try:
                    exp = datetime.fromisoformat(existing_until)
                    if exp.tzinfo is None:
                        exp = exp.replace(tzinfo=timezone.utc)
                    if exp > stamp and existing_owner != owner:
                        conn.close()
                        return {
                            "ok": False,
                            "error": "lease_held",
                            "lease_owner": existing_owner,
                            "lease_until": existing_until,
                        }
                except ValueError:
                    pass
            conn.execute(
                "UPDATE tasks SET lease_owner=?, lease_until=?, updated_at=? WHERE operation_id=?",
                (owner, until, _utc(), operation_id),
            )
            conn.commit()
            conn.close()
        return {"ok": True, "lease_owner": owner, "lease_until": until, "operation_id": operation_id}

    def release_lease(self, operation_id: str, owner: str) -> dict[str, Any]:
        with _LOCK:
            conn = connect(self.path)
            row = conn.execute(
                "SELECT lease_owner FROM tasks WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if not row:
                conn.close()
                return {"ok": False, "error": "unknown_operation"}
            if row["lease_owner"] and row["lease_owner"] != owner:
                conn.close()
                return {"ok": False, "error": "not_lease_owner"}
            conn.execute(
                "UPDATE tasks SET lease_owner=NULL, lease_until=NULL, updated_at=? WHERE operation_id=?",
                (_utc(), operation_id),
            )
            conn.commit()
            conn.close()
        return {"ok": True, "released": True}

    def record_effect(
        self,
        *,
        operation_id: str,
        idempotency_key: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Apply to local effect sink with idempotency — returns existing receipt on replay."""
        with _LOCK:
            conn = connect(self.path)
            existing = conn.execute(
                "SELECT * FROM effect_sink WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
            if existing:
                receipt = {
                    "effect_id": existing["effect_id"],
                    "operation_id": existing["operation_id"],
                    "idempotency_key": idempotency_key,
                    "applied_at": existing["applied_at"],
                    "payload": json.loads(existing["payload_json"]),
                    "duplicate_suppressed": True,
                    "side_effect_occurred": True,
                }
                conn.close()
                return {"ok": True, "receipt": receipt, "applied_now": False}
            effect_id = f"eff_{uuid.uuid4().hex[:12]}"
            now = _utc()
            conn.execute(
                """
                INSERT INTO effect_sink(idempotency_key, operation_id, effect_id, payload_json, applied_at)
                VALUES (?,?,?,?,?)
                """,
                (idempotency_key, operation_id, effect_id, json.dumps(payload), now),
            )
            receipt = {
                "effect_id": effect_id,
                "operation_id": operation_id,
                "idempotency_key": idempotency_key,
                "applied_at": now,
                "payload": payload,
                "duplicate_suppressed": False,
                "side_effect_occurred": True,
            }
            conn.execute(
                "UPDATE tasks SET effect_receipt_json=?, updated_at=? WHERE operation_id=?",
                (json.dumps(receipt), now, operation_id),
            )
            conn.commit()
            conn.close()
        return {"ok": True, "receipt": receipt, "applied_now": True}

    def get_effect_by_key(self, idempotency_key: str) -> dict[str, Any] | None:
        conn = connect(self.path)
        row = conn.execute(
            "SELECT * FROM effect_sink WHERE idempotency_key=?", (idempotency_key,)
        ).fetchone()
        conn.close()
        if not row:
            return None
        return {
            "effect_id": row["effect_id"],
            "operation_id": row["operation_id"],
            "idempotency_key": idempotency_key,
            "applied_at": row["applied_at"],
            "payload": json.loads(row["payload_json"]),
            "side_effect_occurred": True,
        }

    def transitions_for(self, operation_id: str) -> list[dict[str, Any]]:
        conn = connect(self.path)
        rows = conn.execute(
            "SELECT * FROM transitions WHERE operation_id=? ORDER BY id",
            (operation_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        for k in ("checkpoint_json", "effect_receipt_json", "engine_status_json"):
            raw = d.pop(k, None)
            name = k.replace("_json", "")
            d[name] = json.loads(raw) if raw else None
        return d
