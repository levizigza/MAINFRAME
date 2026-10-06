"""Cache dependency maps by file + configuration hashes (local SQLite only)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.config import STATE_DIR, ensure_state
from mainframe.depmap.build import build_map

DB_NAME = "depmap_cache.sqlite"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _db() -> Path:
    ensure_state()
    return STATE_DIR / DB_NAME


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db()))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dep_maps (
          root_key TEXT NOT NULL,
          config_hash TEXT NOT NULL,
          content_hash TEXT NOT NULL,
          map_json TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          PRIMARY KEY (root_key, config_hash, content_hash)
        )
        """
    )
    conn.commit()
    return conn


def root_key(root: Path) -> str:
    return str(root.resolve()).replace("\\", "/").casefold()


def get_or_build(
    root: Path,
    *,
    observed_runs: list[dict[str, Any]] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Return cached map when hashes match; otherwise rebuild and store."""
    root = root.resolve()
    # Build fresh to compute hashes (lightweight for fixtures); compare to cache
    fresh = build_map(root, observed_runs=observed_runs)
    ck = fresh["cache_key"]
    rk = root_key(root)
    conn = _connect()
    if not force:
        row = conn.execute(
            """
            SELECT map_json FROM dep_maps
            WHERE root_key=? AND config_hash=? AND content_hash=?
            """,
            (rk, ck["config_hash"], ck["content_hash"]),
        ).fetchone()
        if row:
            cached = json.loads(row["map_json"])
            cached["cache_hit"] = True
            cached["graph_service_used"] = False
            conn.close()
            return cached

    fresh["cache_hit"] = False
    conn.execute(
        """
        INSERT INTO dep_maps(root_key, config_hash, content_hash, map_json, updated_at)
        VALUES (?,?,?,?,?)
        ON CONFLICT(root_key, config_hash, content_hash) DO UPDATE SET
          map_json=excluded.map_json,
          updated_at=excluded.updated_at
        """,
        (rk, ck["config_hash"], ck["content_hash"], json.dumps(fresh), _utc()),
    )
    conn.commit()
    conn.close()
    return fresh
