"""Project-isolated exact cache store (local SQLite)."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.cache.keys import project_id
from mainframe.cache.redact import redact_for_storage
from mainframe.config import STATE_DIR, ensure_state

DB_NAME = "exact_reuse_cache.sqlite"
_LOCK = threading.Lock()


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _db_path() -> Path:
    ensure_state()
    cache_dir = STATE_DIR / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / DB_NAME


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS exact_entries (
          project_id TEXT NOT NULL,
          kind TEXT NOT NULL,
          cache_key TEXT NOT NULL,
          content_hash TEXT NOT NULL,
          permission_ver TEXT NOT NULL,
          config_ver TEXT NOT NULL,
          model_ver TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          work_units INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL,
          expires_at TEXT,
          PRIMARY KEY (project_id, cache_key)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_exact_kind
        ON exact_entries(project_id, kind)
        """
    )
    conn.commit()
    return conn


def put_exact(
    *,
    root: Path,
    kind: str,
    cache_key: str,
    payload: Any,
    content_hash: str,
    permission_ver: str,
    config_ver: str,
    model_ver: str = "none",
    work_units: int = 1,
    expires_at: str | None = None,
) -> dict[str, Any]:
    pid = project_id(root)
    safe = redact_for_storage(payload)
    with _LOCK:
        conn = _connect()
        conn.execute(
            """
            INSERT INTO exact_entries(
              project_id, kind, cache_key, content_hash, permission_ver,
              config_ver, model_ver, payload_json, work_units, created_at, expires_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(project_id, cache_key) DO UPDATE SET
              payload_json=excluded.payload_json,
              content_hash=excluded.content_hash,
              permission_ver=excluded.permission_ver,
              config_ver=excluded.config_ver,
              model_ver=excluded.model_ver,
              work_units=excluded.work_units,
              created_at=excluded.created_at,
              expires_at=excluded.expires_at
            """,
            (
                pid,
                kind,
                cache_key,
                content_hash,
                permission_ver,
                config_ver,
                model_ver,
                json.dumps(safe),
                int(work_units),
                _utc(),
                expires_at,
            ),
        )
        conn.commit()
        conn.close()
    return {
        "ok": True,
        "project_id": pid,
        "kind": kind,
        "cache_key": cache_key,
        "stored": True,
        "redacted": True,
    }


def get_exact(
    *,
    root: Path,
    cache_key: str,
    expect_content_hash: str | None = None,
    expect_permission_ver: str | None = None,
    now: str | None = None,
) -> dict[str, Any] | None:
    """
    Fetch exact entry. Returns None on miss, hash/permission mismatch, or expiry.
    Never serves approximate matches.
    """
    pid = project_id(root)
    with _LOCK:
        conn = _connect()
        row = conn.execute(
            """
            SELECT * FROM exact_entries
            WHERE project_id=? AND cache_key=?
            """,
            (pid, cache_key),
        ).fetchone()
        conn.close()
    if not row:
        return None
    if expect_content_hash is not None and row["content_hash"] != expect_content_hash:
        return None
    if expect_permission_ver is not None and row["permission_ver"] != expect_permission_ver:
        return None
    exp = row["expires_at"]
    if exp:
        stamp = now or _utc()
        if stamp > exp:
            return None
    return {
        "project_id": row["project_id"],
        "kind": row["kind"],
        "cache_key": row["cache_key"],
        "content_hash": row["content_hash"],
        "permission_ver": row["permission_ver"],
        "config_ver": row["config_ver"],
        "model_ver": row["model_ver"],
        "payload": json.loads(row["payload_json"]),
        "work_units": row["work_units"],
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
        "exact": True,
        "approximate": False,
    }


def delete_keys(root: Path, keys: list[str]) -> int:
    pid = project_id(root)
    if not keys:
        return 0
    with _LOCK:
        conn = _connect()
        n = 0
        for k in keys:
            cur = conn.execute(
                "DELETE FROM exact_entries WHERE project_id=? AND cache_key=?",
                (pid, k),
            )
            n += cur.rowcount
        conn.commit()
        conn.close()
    return n


def delete_kind(root: Path, kind: str) -> int:
    pid = project_id(root)
    with _LOCK:
        conn = _connect()
        cur = conn.execute(
            "DELETE FROM exact_entries WHERE project_id=? AND kind=?",
            (pid, kind),
        )
        n = cur.rowcount
        conn.commit()
        conn.close()
    return n


def delete_project(root: Path) -> int:
    pid = project_id(root)
    with _LOCK:
        conn = _connect()
        cur = conn.execute("DELETE FROM exact_entries WHERE project_id=?", (pid,))
        n = cur.rowcount
        conn.commit()
        conn.close()
    return n


def list_entries(root: Path, kind: str | None = None) -> list[dict[str, Any]]:
    pid = project_id(root)
    with _LOCK:
        conn = _connect()
        if kind:
            rows = conn.execute(
                "SELECT project_id, kind, cache_key, content_hash, permission_ver, created_at "
                "FROM exact_entries WHERE project_id=? AND kind=?",
                (pid, kind),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT project_id, kind, cache_key, content_hash, permission_ver, created_at "
                "FROM exact_entries WHERE project_id=?",
                (pid,),
            ).fetchall()
        conn.close()
    return [dict(r) for r in rows]


def clear_all_for_tests() -> None:
    """Wipe entire exact cache DB — test/accept only."""
    with _LOCK:
        path = _db_path()
        if path.is_file():
            path.unlink()
