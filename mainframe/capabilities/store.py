"""Durable capability grants, queue, and emergency-stop state (local SQLite)."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.config import STATE_DIR, ensure_state

DB_NAME = "capability_grants.sqlite"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_expires(expires_at: str | None) -> bool:
    if not expires_at:
        return False
    try:
        exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > exp
    except ValueError:
        return True


class CapabilityStore:
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
            CREATE TABLE IF NOT EXISTS grants (
              grant_id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL,
              capabilities_json TEXT NOT NULL,
              destinations_json TEXT NOT NULL,
              operations_json TEXT NOT NULL,
              expires_at TEXT,
              source TEXT NOT NULL,
              revoked INTEGER NOT NULL DEFAULT 0,
              carried_forward_from TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS queue (
              item_id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL,
              capability TEXT NOT NULL,
              operation TEXT NOT NULL,
              destination TEXT,
              payload_json TEXT,
              state TEXT NOT NULL,
              hold_reason TEXT,
              preview_json TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS control (
              key TEXT PRIMARY KEY,
              value_json TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            """
        )
        conn.commit()
        conn.close()

    def grant(
        self,
        *,
        project_id: str,
        capabilities: list[str],
        destinations: list[str],
        operations: list[str],
        expires_at: str | None = None,
        source: str = "user_authorization",
    ) -> dict[str, Any]:
        gid = f"gr_{uuid.uuid4().hex[:16]}"
        now = _utc()
        row = {
            "grant_id": gid,
            "project_id": project_id,
            "capabilities": list(capabilities),
            "destinations": list(destinations),
            "operations": list(operations),
            "expires_at": expires_at,
            "source": source,
            "revoked": False,
            "carried_forward_from": None,
            "created_at": now,
            "updated_at": now,
        }
        conn = self._connect()
        conn.execute(
            """
            INSERT INTO grants(
              grant_id, project_id, capabilities_json, destinations_json,
              operations_json, expires_at, source, revoked, carried_forward_from,
              created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                gid,
                project_id,
                json.dumps(row["capabilities"]),
                json.dumps(row["destinations"]),
                json.dumps(row["operations"]),
                expires_at,
                source,
                0,
                None,
                now,
                now,
            ),
        )
        conn.commit()
        conn.close()
        return {"ok": True, "grant": row}

    def carry_forward(self, grant_id: str) -> dict[str, Any]:
        prev = self.get_grant(grant_id)
        if not prev or prev.get("revoked"):
            return {"ok": False, "error": "missing_or_revoked_grant"}
        out = self.grant(
            project_id=prev["project_id"],
            capabilities=list(prev["capabilities"]),
            destinations=list(prev["destinations"]),
            operations=list(prev["operations"]),
            expires_at=prev.get("expires_at"),
            source="user_authorization",
        )
        if not out.get("ok"):
            return out
        new_id = out["grant"]["grant_id"]
        conn = self._connect()
        conn.execute(
            "UPDATE grants SET carried_forward_from=?, updated_at=? WHERE grant_id=?",
            (grant_id, _utc(), new_id),
        )
        conn.commit()
        conn.close()
        g = self.get_grant(new_id)
        return {"ok": True, "grant": g}

    def get_grant(self, grant_id: str) -> dict[str, Any] | None:
        conn = self._connect()
        row = conn.execute("SELECT * FROM grants WHERE grant_id=?", (grant_id,)).fetchone()
        conn.close()
        return self._grant_row(row) if row else None

    def active_grants(self, project_id: str) -> list[dict[str, Any]]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM grants WHERE project_id=? AND revoked=0 ORDER BY created_at",
            (project_id,),
        ).fetchall()
        conn.close()
        out = [self._grant_row(r) for r in rows]
        return [g for g in out if g and not _parse_expires(g.get("expires_at"))]

    @staticmethod
    def _grant_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "grant_id": row["grant_id"],
            "project_id": row["project_id"],
            "capabilities": json.loads(row["capabilities_json"]),
            "destinations": json.loads(row["destinations_json"]),
            "operations": json.loads(row["operations_json"]),
            "expires_at": row["expires_at"],
            "source": row["source"],
            "revoked": bool(row["revoked"]),
            "carried_forward_from": row["carried_forward_from"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def revoke(self, grant_id: str) -> dict[str, Any]:
        conn = self._connect()
        conn.execute(
            "UPDATE grants SET revoked=1, updated_at=? WHERE grant_id=?",
            (_utc(), grant_id),
        )
        conn.commit()
        conn.close()
        g = self.get_grant(grant_id)
        if g:
            g["revoked"] = True
        return {"ok": True, "grant": g}

    def enqueue(
        self,
        *,
        project_id: str,
        capability: str,
        operation: str,
        destination: str | None = None,
        payload: dict[str, Any] | None = None,
        state: str = "queued",
        hold_reason: str | None = None,
        preview: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        iid = f"q_{uuid.uuid4().hex[:12]}"
        now = _utc()
        conn = self._connect()
        conn.execute(
            """
            INSERT INTO queue(
              item_id, project_id, capability, operation, destination,
              payload_json, state, hold_reason, preview_json, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                iid,
                project_id,
                capability,
                operation,
                destination,
                json.dumps(payload or {}),
                state,
                hold_reason,
                json.dumps(preview) if preview else None,
                now,
                now,
            ),
        )
        conn.commit()
        conn.close()
        return {"item_id": iid, "state": state, "project_id": project_id}

    def list_queue(self, project_id: str, *, state: str | None = None) -> list[dict[str, Any]]:
        conn = self._connect()
        if state:
            rows = conn.execute(
                "SELECT * FROM queue WHERE project_id=? AND state=?",
                (project_id, state),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM queue WHERE project_id=?",
                (project_id,),
            ).fetchall()
        conn.close()
        return [self._queue_row(r) for r in rows]

    def get_queue_item(self, item_id: str) -> dict[str, Any] | None:
        conn = self._connect()
        row = conn.execute("SELECT * FROM queue WHERE item_id=?", (item_id,)).fetchone()
        conn.close()
        return self._queue_row(row) if row else None

    def update_queue_item(self, item_id: str, *, state: str) -> dict[str, Any] | None:
        conn = self._connect()
        conn.execute(
            "UPDATE queue SET state=?, updated_at=? WHERE item_id=?",
            (state, _utc(), item_id),
        )
        conn.commit()
        conn.close()
        return self.get_queue_item(item_id)

    @staticmethod
    def _queue_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "item_id": row["item_id"],
            "project_id": row["project_id"],
            "capability": row["capability"],
            "operation": row["operation"],
            "destination": row["destination"],
            "payload": json.loads(row["payload_json"] or "{}"),
            "state": row["state"],
            "hold_reason": row["hold_reason"],
            "preview": json.loads(row["preview_json"]) if row["preview_json"] else None,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def set_emergency_stop(self, *, active: bool, reason: str = "") -> None:
        conn = self._connect()
        conn.execute(
            """
            INSERT INTO control(key, value_json, updated_at) VALUES (?,?,?)
            ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at
            """,
            (
                "emergency_stop",
                json.dumps({"active": active, "reason": reason}),
                _utc(),
            ),
        )
        conn.commit()
        conn.close()

    def emergency_stop_active(self) -> dict[str, Any]:
        conn = self._connect()
        row = conn.execute("SELECT value_json FROM control WHERE key='emergency_stop'").fetchone()
        conn.close()
        if not row:
            return {"active": False}
        return json.loads(row["value_json"])

    def cancel_all_queue(self, project_id: str | None = None) -> int:
        conn = self._connect()
        if project_id:
            cur = conn.execute(
                "DELETE FROM queue WHERE project_id=?",
                (project_id,),
            )
        else:
            cur = conn.execute("DELETE FROM queue")
        n = cur.rowcount
        conn.commit()
        conn.close()
        return n
