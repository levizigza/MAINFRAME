"""Inventory store: content hashes + provenance; incremental updates."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.config import STATE_DIR, ensure_state

DB_NAME = "inventory.sqlite"
SCHEMA_VERSION = 1


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def db_path(root: Path | None = None) -> Path:
    ensure_state()
    # Per-target inventory keyed by scan root hash folder name when needed;
    # default shared DB with root column.
    return STATE_DIR / DB_NAME


def connect(root: Path) -> sqlite3.Connection:
    ensure_state()
    path = db_path()
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
          version INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS scan_roots (
          root_key TEXT PRIMARY KEY,
          root_path TEXT NOT NULL,
          last_scan_at TEXT,
          summary_json TEXT
        );
        CREATE TABLE IF NOT EXISTS file_entries (
          root_key TEXT NOT NULL,
          path_key TEXT NOT NULL,
          display_path TEXT NOT NULL,
          content_sha256 TEXT,
          size_bytes INTEGER,
          mtime_ns INTEGER,
          is_symlink INTEGER NOT NULL DEFAULT 0,
          symlink_target TEXT,
          language TEXT,
          kind TEXT,
          git_status TEXT,
          privacy_excluded INTEGER NOT NULL DEFAULT 0,
          ignored INTEGER NOT NULL DEFAULT 0,
          provenance_json TEXT,
          updated_at TEXT NOT NULL,
          PRIMARY KEY (root_key, path_key)
        );
        CREATE INDEX IF NOT EXISTS idx_file_entries_kind
          ON file_entries(root_key, kind);
        """
    )
    row = conn.execute("SELECT COUNT(*) AS c FROM schema_meta").fetchone()
    if row and int(row["c"]) == 0:
        conn.execute("INSERT INTO schema_meta(version) VALUES (?)", (SCHEMA_VERSION,))
    conn.commit()


def root_key(root: Path) -> str:
    # Case-insensitive identity for Windows
    return str(root.resolve()).replace("\\", "/").casefold()


def upsert_file(conn: sqlite3.Connection, root_key_s: str, entry: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO file_entries(
          root_key, path_key, display_path, content_sha256, size_bytes, mtime_ns,
          is_symlink, symlink_target, language, kind, git_status,
          privacy_excluded, ignored, provenance_json, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(root_key, path_key) DO UPDATE SET
          display_path=excluded.display_path,
          content_sha256=excluded.content_sha256,
          size_bytes=excluded.size_bytes,
          mtime_ns=excluded.mtime_ns,
          is_symlink=excluded.is_symlink,
          symlink_target=excluded.symlink_target,
          language=excluded.language,
          kind=excluded.kind,
          git_status=excluded.git_status,
          privacy_excluded=excluded.privacy_excluded,
          ignored=excluded.ignored,
          provenance_json=excluded.provenance_json,
          updated_at=excluded.updated_at
        """,
        (
            root_key_s,
            entry["path_key"],
            entry["display_path"],
            entry.get("content_sha256"),
            entry.get("size_bytes"),
            entry.get("mtime_ns"),
            int(entry.get("is_symlink") or 0),
            entry.get("symlink_target"),
            entry.get("language"),
            entry.get("kind"),
            entry.get("git_status"),
            int(entry.get("privacy_excluded") or 0),
            int(entry.get("ignored") or 0),
            json.dumps(entry.get("provenance") or {}),
            _utc(),
        ),
    )


def get_entry(conn: sqlite3.Connection, root_key_s: str, path_key: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM file_entries WHERE root_key=? AND path_key=?",
        (root_key_s, path_key),
    ).fetchone()
    return dict(row) if row else None


def save_summary(conn: sqlite3.Connection, root_key_s: str, root_path: str, summary: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO scan_roots(root_key, root_path, last_scan_at, summary_json)
        VALUES (?,?,?,?)
        ON CONFLICT(root_key) DO UPDATE SET
          root_path=excluded.root_path,
          last_scan_at=excluded.last_scan_at,
          summary_json=excluded.summary_json
        """,
        (root_key_s, root_path, _utc(), json.dumps(summary)),
    )
    conn.commit()


def load_summary(conn: sqlite3.Connection, root_key_s: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT summary_json FROM scan_roots WHERE root_key=?", (root_key_s,)
    ).fetchone()
    if not row or not row["summary_json"]:
        return None
    return json.loads(row["summary_json"])
