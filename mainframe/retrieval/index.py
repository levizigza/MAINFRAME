"""Optional local SQLite FTS5 index — used only when measured helpful."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from mainframe.config import STATE_DIR, ensure_state
from mainframe.inventory.ignore import is_privacy_excluded, should_skip_dir

DB_NAME = "retrieval_fts.sqlite"
CODE_SUFFIXES = frozenset(
    {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".cs", ".md", ".txt"}
)


def db_path() -> Path:
    ensure_state()
    return STATE_DIR / DB_NAME


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path()))
    conn.row_factory = sqlite3.Row
    return conn


def fts5_available() -> bool:
    try:
        conn = _connect()
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts_probe USING fts5(x)")
        conn.execute("DROP TABLE IF EXISTS _fts_probe")
        conn.close()
        return True
    except sqlite3.OperationalError:
        return False


def list_code_files(root: Path) -> list[tuple[str, Path]]:
    root = root.resolve()
    out: list[tuple[str, Path]] = []
    for dirpath, dirnames, filenames in __import__("os").walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
        base = Path(dirpath)
        for name in filenames:
            full = base / name
            if full.suffix.lower() not in CODE_SUFFIXES:
                continue
            try:
                rel = full.relative_to(root).as_posix()
            except ValueError:
                continue
            if is_privacy_excluded(rel):
                continue
            out.append((rel, full))
    return out


def build_index(root: Path) -> dict[str, Any]:
    """Rebuild FTS5 corpus for root. Returns status; never uses remote/paid embeddings."""
    if not fts5_available():
        return {"ok": False, "fts5": False, "reason": "fts5_unavailable"}

    root = root.resolve()
    root_key = str(root).replace("\\", "/").casefold()
    files = list_code_files(root)
    conn = _connect()
    conn.execute("DROP TABLE IF EXISTS code_fts")
    conn.execute("DROP TABLE IF EXISTS code_meta")
    conn.execute(
        "CREATE VIRTUAL TABLE code_fts USING fts5(path, body, tokenize='porter unicode61')"
    )
    conn.execute(
        """
        CREATE TABLE code_meta(
          root_key TEXT NOT NULL,
          path TEXT NOT NULL,
          PRIMARY KEY(root_key, path)
        )
        """
    )
    n = 0
    for rel, full in files:
        try:
            body = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # Strip BOM
        if body.startswith("\ufeff"):
            body = body[1:]
        conn.execute(
            "INSERT INTO code_fts(path, body) VALUES (?, ?)",
            (rel, body),
        )
        conn.execute(
            "INSERT INTO code_meta(root_key, path) VALUES (?, ?)",
            (root_key, rel),
        )
        n += 1
    conn.commit()
    conn.close()
    return {
        "ok": True,
        "fts5": True,
        "indexed_files": n,
        "root": str(root),
        "paid_embedding_used": False,
        "remote_vector_db_used": False,
    }


def fts_search(root: Path, terms: list[str], *, limit: int = 20) -> list[dict[str, Any]]:
    """BM25-ish FTS5 query. Empty if index missing or FTS5 unavailable."""
    if not terms or not fts5_available():
        return []
    root_key = str(root.resolve()).replace("\\", "/").casefold()
    # Sanitize: keep alnum underscore only for FTS tokens
    clean: list[str] = []
    for t in terms:
        tok = "".join(ch if ch.isalnum() or ch == "_" else " " for ch in t).strip()
        if len(tok) >= 3:
            clean.append(tok)
    if not clean:
        return []
    # OR query
    q = " OR ".join(f'"{c}"' if " " in c else c for c in clean[:12])
    conn = _connect()
    try:
        # Ensure table exists
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='code_fts'"
        ).fetchone()
        if not row:
            conn.close()
            return []
        # Restrict to this root via meta join when possible
        sql = """
        SELECT f.path AS path, bm25(code_fts) AS rank, snippet(code_fts, 1, '<<', '>>', '…', 12) AS snip
        FROM code_fts f
        JOIN code_meta m ON m.path = f.path
        WHERE m.root_key = ? AND code_fts MATCH ?
        ORDER BY rank
        LIMIT ?
        """
        rows = conn.execute(sql, (root_key, q, limit)).fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return []
    conn.close()
    out: list[dict[str, Any]] = []
    for r in rows:
        # bm25: lower is better in SQLite; convert to positive score
        bm = float(r["rank"])
        score = max(0.0, 10.0 - abs(bm))
        out.append(
            {
                "path": r["path"],
                "fts_score": score,
                "snippet": r["snip"],
                "signal": "fts5_bm25",
            }
        )
    return out
