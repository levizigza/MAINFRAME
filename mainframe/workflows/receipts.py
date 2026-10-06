"""FreeForge-owned workflow run receipts — checkpoints, effects, cancel, concurrency."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.config import STATE_DIR, ensure_state
from mainframe.workflows.redact_diag import redact_diag

DB_NAME = "freeforge_workflow_receipts.sqlite"
_LOCK = threading.Lock()


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkflowReceiptStore:
    """Local receipts for workflow step outcomes (FreeForge semantics only)."""

    def __init__(self, path: Path | None = None) -> None:
        ensure_state()
        self.path = path or (STATE_DIR / DB_NAME)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _migrate(self) -> None:
        conn = self._connect()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS workflow_runs (
              run_id TEXT PRIMARY KEY,
              workflow_id TEXT NOT NULL,
              format_version TEXT NOT NULL,
              state TEXT NOT NULL,
              inputs_json TEXT NOT NULL,
              outputs_json TEXT,
              error TEXT,
              cancel_requested INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS step_receipts (
              receipt_id TEXT PRIMARY KEY,
              run_id TEXT NOT NULL,
              step_id TEXT NOT NULL,
              kind TEXT NOT NULL,
              state TEXT NOT NULL,
              attempt INTEGER NOT NULL,
              operation_id TEXT,
              output_json TEXT,
              artifact_refs_json TEXT,
              effect_receipt_json TEXT,
              delivery_status TEXT,
              checkpoint_json TEXT,
              error TEXT,
              created_at TEXT NOT NULL,
              FOREIGN KEY(run_id) REFERENCES workflow_runs(run_id)
            );
            CREATE TABLE IF NOT EXISTS effect_index (
              operation_id TEXT PRIMARY KEY,
              run_id TEXT NOT NULL,
              step_id TEXT NOT NULL,
              effect_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS concurrency (
              slot_key TEXT PRIMARY KEY,
              holder_run_id TEXT,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS control (
              key TEXT PRIMARY KEY,
              value_json TEXT NOT NULL
            );
            """
        )
        # Additive columns for older DBs
        cols = {r[1] for r in conn.execute("PRAGMA table_info(workflow_runs)").fetchall()}
        if "cancel_requested" not in cols:
            conn.execute(
                "ALTER TABLE workflow_runs ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0"
            )
        scols = {r[1] for r in conn.execute("PRAGMA table_info(step_receipts)").fetchall()}
        for col, decl in (
            ("operation_id", "TEXT"),
            ("effect_receipt_json", "TEXT"),
            ("delivery_status", "TEXT"),
            ("checkpoint_json", "TEXT"),
        ):
            if col not in scols:
                conn.execute(f"ALTER TABLE step_receipts ADD COLUMN {col} {decl}")
        conn.commit()
        conn.close()

    def start_run(self, workflow_id: str, format_version: str, inputs: dict[str, Any]) -> str:
        run_id = f"wfr_{uuid.uuid4().hex[:16]}"
        now = _utc()
        with _LOCK:
            conn = self._connect()
            conn.execute(
                """
                INSERT INTO workflow_runs(
                  run_id, workflow_id, format_version, state, inputs_json,
                  cancel_requested, created_at, updated_at
                ) VALUES (?,?,?,?,?,0,?,?)
                """,
                (run_id, workflow_id, format_version, "started", json.dumps(inputs), now, now),
            )
            conn.commit()
            conn.close()
        return run_id

    def request_cancel(self, run_id: str) -> None:
        with _LOCK:
            conn = self._connect()
            conn.execute(
                "UPDATE workflow_runs SET cancel_requested=1, updated_at=? WHERE run_id=?",
                (_utc(), run_id),
            )
            conn.commit()
            conn.close()

    def cancel_requested(self, run_id: str) -> bool:
        conn = self._connect()
        row = conn.execute(
            "SELECT cancel_requested FROM workflow_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        conn.close()
        return bool(row and row["cancel_requested"])

    def acquire_slot(self, *, max_concurrent: int, run_id: str) -> dict[str, Any]:
        if max_concurrent <= 0:
            return {"ok": True, "unlimited": True}
        with _LOCK:
            conn = self._connect()
            active = conn.execute(
                "SELECT COUNT(*) AS n FROM concurrency WHERE holder_run_id IS NOT NULL"
            ).fetchone()["n"]
            if active >= max_concurrent:
                conn.close()
                return {"ok": False, "error": "concurrency_limit", "active": active, "max": max_concurrent}
            slot = f"slot_{active}"
            conn.execute(
                """
                INSERT INTO concurrency(slot_key, holder_run_id, updated_at) VALUES (?,?,?)
                ON CONFLICT(slot_key) DO UPDATE SET holder_run_id=excluded.holder_run_id, updated_at=excluded.updated_at
                """,
                (slot, run_id, _utc()),
            )
            conn.commit()
            conn.close()
            return {"ok": True, "slot": slot}

    def release_slot(self, run_id: str) -> None:
        with _LOCK:
            conn = self._connect()
            conn.execute(
                "UPDATE concurrency SET holder_run_id=NULL, updated_at=? WHERE holder_run_id=?",
                (_utc(), run_id),
            )
            conn.commit()
            conn.close()

    def record_step(
        self,
        run_id: str,
        *,
        step_id: str,
        kind: str,
        state: str,
        attempt: int = 1,
        output: dict[str, Any] | None = None,
        artifact_refs: list[str] | None = None,
        error: str | None = None,
        operation_id: str | None = None,
        effect_receipt: dict[str, Any] | None = None,
        delivery_status: str | None = None,
        checkpoint: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        rid = f"wsr_{uuid.uuid4().hex[:12]}"
        now = _utc()
        safe_output = redact_diag(output) if output is not None else None
        safe_effect = redact_diag(effect_receipt) if effect_receipt is not None else None
        with _LOCK:
            conn = self._connect()
            conn.execute(
                """
                INSERT INTO step_receipts(
                  receipt_id, run_id, step_id, kind, state, attempt, operation_id,
                  output_json, artifact_refs_json, effect_receipt_json, delivery_status,
                  checkpoint_json, error, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    rid,
                    run_id,
                    step_id,
                    kind,
                    state,
                    attempt,
                    operation_id,
                    json.dumps(safe_output) if safe_output is not None else None,
                    json.dumps(artifact_refs or []),
                    json.dumps(safe_effect) if safe_effect is not None else None,
                    delivery_status,
                    json.dumps(checkpoint) if checkpoint is not None else None,
                    error,
                    now,
                ),
            )
            if operation_id and safe_effect:
                conn.execute(
                    """
                    INSERT INTO effect_index(operation_id, run_id, step_id, effect_json, created_at)
                    VALUES (?,?,?,?,?)
                    ON CONFLICT(operation_id) DO UPDATE SET
                      effect_json=excluded.effect_json
                    """,
                    (operation_id, run_id, step_id, json.dumps(safe_effect), now),
                )
            conn.commit()
            conn.close()
        return {
            "receipt_id": rid,
            "run_id": run_id,
            "step_id": step_id,
            "state": state,
            "attempt": attempt,
            "operation_id": operation_id,
            "output": safe_output,
            "effect_receipt": safe_effect,
            "delivery_status": delivery_status,
            "checkpoint": checkpoint,
            "error": error,
        }

    def get_effect(self, operation_id: str) -> dict[str, Any] | None:
        conn = self._connect()
        row = conn.execute(
            "SELECT effect_json FROM effect_index WHERE operation_id=?", (operation_id,)
        ).fetchone()
        conn.close()
        return json.loads(row["effect_json"]) if row else None

    def latest_checkpoint(self, run_id: str, step_id: str) -> dict[str, Any] | None:
        conn = self._connect()
        row = conn.execute(
            """
            SELECT * FROM step_receipts
            WHERE run_id=? AND step_id=? AND state='succeeded'
            ORDER BY created_at DESC LIMIT 1
            """,
            (run_id, step_id),
        ).fetchone()
        conn.close()
        if not row:
            return None
        return {
            "step_id": row["step_id"],
            "state": row["state"],
            "operation_id": row["operation_id"],
            "output": json.loads(row["output_json"]) if row["output_json"] else None,
            "effect_receipt": json.loads(row["effect_receipt_json"])
            if row["effect_receipt_json"]
            else None,
            "delivery_status": row["delivery_status"],
            "checkpoint": json.loads(row["checkpoint_json"]) if row["checkpoint_json"] else None,
        }

    def succeeded_steps(self, run_id: str) -> dict[str, dict[str, Any]]:
        conn = self._connect()
        rows = conn.execute(
            """
            SELECT * FROM step_receipts WHERE run_id=? AND state='succeeded'
            ORDER BY created_at
            """,
            (run_id,),
        ).fetchall()
        conn.close()
        out: dict[str, dict[str, Any]] = {}
        for row in rows:
            out[row["step_id"]] = {
                "output": json.loads(row["output_json"]) if row["output_json"] else None,
                "operation_id": row["operation_id"],
                "effect_receipt": json.loads(row["effect_receipt_json"])
                if row["effect_receipt_json"]
                else None,
                "delivery_status": row["delivery_status"],
            }
        return out

    def finish_run(
        self,
        run_id: str,
        *,
        state: str,
        outputs: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        with _LOCK:
            conn = self._connect()
            conn.execute(
                """
                UPDATE workflow_runs
                SET state=?, outputs_json=?, error=?, updated_at=?
                WHERE run_id=?
                """,
                (
                    state,
                    json.dumps(redact_diag(outputs)) if outputs is not None else None,
                    error,
                    _utc(),
                    run_id,
                ),
            )
            conn.commit()
            conn.close()
        self.release_slot(run_id)

    def list_step_receipts(self, run_id: str) -> list[dict[str, Any]]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM step_receipts WHERE run_id=? ORDER BY created_at",
            (run_id,),
        ).fetchall()
        conn.close()
        out = []
        for r in rows:
            out.append(
                {
                    "receipt_id": r["receipt_id"],
                    "run_id": r["run_id"],
                    "step_id": r["step_id"],
                    "kind": r["kind"],
                    "state": r["state"],
                    "attempt": r["attempt"],
                    "operation_id": r["operation_id"] if "operation_id" in r.keys() else None,
                    "output": json.loads(r["output_json"]) if r["output_json"] else None,
                    "artifact_refs": json.loads(r["artifact_refs_json"] or "[]"),
                    "effect_receipt": json.loads(r["effect_receipt_json"])
                    if r["effect_receipt_json"]
                    else None,
                    "delivery_status": r["delivery_status"] if "delivery_status" in r.keys() else None,
                    "error": r["error"],
                    "created_at": r["created_at"],
                }
            )
        return out

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        conn = self._connect()
        row = conn.execute("SELECT * FROM workflow_runs WHERE run_id=?", (run_id,)).fetchone()
        conn.close()
        if not row:
            return None
        return {
            "run_id": row["run_id"],
            "workflow_id": row["workflow_id"],
            "format_version": row["format_version"],
            "state": row["state"],
            "inputs": json.loads(row["inputs_json"]),
            "outputs": json.loads(row["outputs_json"]) if row["outputs_json"] else None,
            "error": row["error"],
            "cancel_requested": bool(row["cancel_requested"])
            if "cancel_requested" in row.keys()
            else False,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_recent_runs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        conn = self._connect()
        rows = conn.execute(
            """
            SELECT run_id, workflow_id, state, error, created_at, updated_at, cancel_requested
            FROM workflow_runs
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        conn.close()
        return [
            {
                "run_id": r["run_id"],
                "workflow_id": r["workflow_id"],
                "state": r["state"],
                "error": r["error"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
                "cancel_requested": bool(r["cancel_requested"])
                if "cancel_requested" in r.keys()
                else False,
            }
            for r in rows
        ]

    def failed_deliveries(self, run_id: str) -> list[dict[str, Any]]:
        return [
            r
            for r in self.list_step_receipts(run_id)
            if r.get("delivery_status") == "failed" or (r.get("effect_receipt") or {}).get("delivery_status") == "failed"
        ]
