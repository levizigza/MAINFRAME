"""Project-scoped exact cache helpers (namespace by explicit project_id)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.cache.redact import redact_for_storage
from mainframe.projects.isolation import refuse_cross_project_retrieval
from mainframe.projects.registry import get_project


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _db(project_id: str) -> Path:
    rec = get_project(project_id)
    if not rec:
        raise FileNotFoundError("project_not_found")
    path = Path(rec["paths"]["cache"]) / "project_cache.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect(project_id: str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db(project_id)))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS entries (
          cache_key TEXT PRIMARY KEY,
          payload_json TEXT NOT NULL,
          created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def put(project_id: str, cache_key: str, payload: Any) -> dict[str, Any]:
    if not get_project(project_id):
        return {"ok": False, "error": "project_not_found"}
    safe = redact_for_storage(payload)
    conn = _connect(project_id)
    conn.execute(
        """
        INSERT INTO entries(cache_key, payload_json, created_at) VALUES (?,?,?)
        ON CONFLICT(cache_key) DO UPDATE SET payload_json=excluded.payload_json, created_at=excluded.created_at
        """,
        (cache_key, json.dumps(safe), _utc()),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "project_id": project_id, "cache_key": cache_key}


def get(
    *,
    requester_project_id: str,
    resource_project_id: str,
    cache_key: str,
) -> dict[str, Any]:
    gate = refuse_cross_project_retrieval(
        requester_project_id=requester_project_id,
        resource_project_id=resource_project_id,
        resource_kind="cache",
    )
    if not gate.get("allowed"):
        return {**gate, "payload": None}
    if not get_project(resource_project_id):
        return {"ok": False, "error": "project_not_found", "payload": None}
    conn = _connect(resource_project_id)
    row = conn.execute("SELECT * FROM entries WHERE cache_key=?", (cache_key,)).fetchone()
    conn.close()
    if not row:
        return {"ok": True, "allowed": True, "hit": False, "payload": None}
    return {
        "ok": True,
        "allowed": True,
        "hit": True,
        "payload": json.loads(row["payload_json"]),
        "project_id": resource_project_id,
        "exposed": False,
    }
