"""FreeForge local job/receipt store for OpenClaw-compatible command payloads."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.config import STATE_DIR, ensure_state
from mainframe.schedule.openclaw_payload import SCHEDULER_OWNER

DB_NAME = "freeforge_schedule.sqlite"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class ScheduleStore:
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
            CREATE TABLE IF NOT EXISTS jobs (
              job_id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              next_run_at TEXT,
              enabled INTEGER NOT NULL DEFAULT 1,
              running INTEGER NOT NULL DEFAULT 0,
              scheduler_owner TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS run_receipts (
              run_id TEXT PRIMARY KEY,
              job_id TEXT NOT NULL,
              status TEXT NOT NULL,
              started_at TEXT NOT NULL,
              finished_at TEXT,
              instrument_json TEXT,
              result_json TEXT,
              error TEXT,
              FOREIGN KEY(job_id) REFERENCES jobs(job_id)
            );
            """
        )
        conn.commit()
        conn.close()

    def upsert_job(
        self,
        *,
        name: str,
        payload: dict[str, Any],
        next_run_at: str | None,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        jid = job_id or f"job_{uuid.uuid4().hex[:12]}"
        now = _utc()
        conn = self._connect()
        existing = conn.execute("SELECT job_id FROM jobs WHERE job_id=?", (jid,)).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE jobs SET name=?, payload_json=?, next_run_at=?, updated_at=?, enabled=1
                WHERE job_id=?
                """,
                (name, json.dumps(payload), next_run_at, now, jid),
            )
        else:
            conn.execute(
                """
                INSERT INTO jobs(
                  job_id, name, payload_json, next_run_at, enabled, running,
                  scheduler_owner, created_at, updated_at
                ) VALUES (?,?,?,?,1,0,?,?,?)
                """,
                (jid, name, json.dumps(payload), next_run_at, SCHEDULER_OWNER, now, now),
            )
        conn.commit()
        conn.close()
        return self.get_job(jid) or {}

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        conn = self._connect()
        row = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        conn.close()
        return self._job_row(row) if row else None

    def list_jobs(self) -> list[dict[str, Any]]:
        conn = self._connect()
        rows = conn.execute("SELECT * FROM jobs ORDER BY created_at").fetchall()
        conn.close()
        return [self._job_row(r) for r in rows]

    @staticmethod
    def _job_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "job_id": row["job_id"],
            "name": row["name"],
            "payload": json.loads(row["payload_json"]),
            "next_run_at": row["next_run_at"],
            "enabled": bool(row["enabled"]),
            "running": bool(row["running"]),
            "scheduler_owner": row["scheduler_owner"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def set_running(self, job_id: str, running: bool) -> None:
        conn = self._connect()
        conn.execute(
            "UPDATE jobs SET running=?, updated_at=? WHERE job_id=?",
            (1 if running else 0, _utc(), job_id),
        )
        conn.commit()
        conn.close()

    def record_receipt(
        self,
        *,
        job_id: str,
        status: str,
        instrument: dict[str, Any],
        result: dict[str, Any] | None = None,
        error: str | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        rid = run_id or f"run_{uuid.uuid4().hex[:12]}"
        now = _utc()
        conn = self._connect()
        conn.execute(
            """
            INSERT INTO run_receipts(
              run_id, job_id, status, started_at, finished_at,
              instrument_json, result_json, error
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                rid,
                job_id,
                status,
                now,
                now,
                json.dumps(instrument),
                json.dumps(result) if result is not None else None,
                error,
            ),
        )
        conn.commit()
        conn.close()
        return self.get_receipt(rid) or {"run_id": rid}

    def get_receipt(self, run_id: str) -> dict[str, Any] | None:
        conn = self._connect()
        row = conn.execute("SELECT * FROM run_receipts WHERE run_id=?", (run_id,)).fetchone()
        conn.close()
        if not row:
            return None
        return {
            "run_id": row["run_id"],
            "job_id": row["job_id"],
            "status": row["status"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "instrument": json.loads(row["instrument_json"] or "{}"),
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "error": row["error"],
        }

    def list_receipts(self, job_id: str) -> list[dict[str, Any]]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT run_id FROM run_receipts WHERE job_id=? ORDER BY started_at",
            (job_id,),
        ).fetchall()
        conn.close()
        out = []
        for r in rows:
            rec = self.get_receipt(r["run_id"])
            if rec:
                out.append(rec)
        return out

    def set_enabled(self, job_id: str, enabled: bool) -> dict[str, Any] | None:
        conn = self._connect()
        conn.execute(
            "UPDATE jobs SET enabled=?, updated_at=? WHERE job_id=?",
            (1 if enabled else 0, _utc(), job_id),
        )
        conn.commit()
        conn.close()
        return self.get_job(job_id)

    def delete_job(self, job_id: str) -> dict[str, Any]:
        conn = self._connect()
        existing = conn.execute(
            "SELECT job_id FROM jobs WHERE job_id=?", (job_id,)
        ).fetchone()
        if not existing:
            conn.close()
            return {"ok": True, "deleted": False, "job_id": job_id, "detail": "not_found"}
        conn.execute("DELETE FROM run_receipts WHERE job_id=?", (job_id,))
        conn.execute("DELETE FROM jobs WHERE job_id=?", (job_id,))
        conn.commit()
        conn.close()
        return {"ok": True, "deleted": True, "job_id": job_id}
