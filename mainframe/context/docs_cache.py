"""Attributed docs/excerpts cache — fetched text is untrusted evidence."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.config import STATE_DIR, ensure_state
from mainframe.cost_gate import authorize

DB_NAME = "context_docs_cache.sqlite"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    ensure_state()
    conn = sqlite3.connect(str(STATE_DIR / DB_NAME))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS excerpts (
          key TEXT PRIMARY KEY,
          source TEXT NOT NULL,
          attribution TEXT NOT NULL,
          trust TEXT NOT NULL,
          version TEXT,
          body TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def cache_put(
    *,
    source: str,
    body: str,
    attribution: str,
    trust: str,
    version: str | None = None,
) -> str:
    key = hashlib.sha256(f"{source}|{version}|{body[:200]}".encode()).hexdigest()
    conn = _connect()
    conn.execute(
        """
        INSERT INTO excerpts(key, source, attribution, trust, version, body, updated_at)
        VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(key) DO UPDATE SET
          body=excluded.body,
          updated_at=excluded.updated_at
        """,
        (key, source, attribution, trust, version, body, _utc()),
    )
    conn.commit()
    conn.close()
    return key


def cache_get(key: str) -> dict[str, Any] | None:
    conn = _connect()
    row = conn.execute("SELECT * FROM excerpts WHERE key=?", (key,)).fetchone()
    conn.close()
    return dict(row) if row else None


def installed_api_excerpt(module: str, attr: str | None = None) -> dict[str, Any]:
    """Prefer installed types / signatures over remote docs."""
    gate = authorize("tool", "local.context_installed_docs", local=True)
    if not gate.allowed:
        return {"ok": False, "cost_gate": gate.to_dict()}

    from mainframe.codeintel.deps import check_callable, resolve_module

    info = resolve_module(module)
    if not info.get("ok"):
        return {
            "ok": False,
            "trust": "none",
            "error": info.get("error"),
            "prefer_installed_types": True,
        }
    parts = [f"module={module}", f"version={info.get('installed_version')}", f"origin={info.get('origin')}"]
    if attr:
        chk = check_callable(module, attr)
        parts.append(f"attr={attr}")
        parts.append(f"accepted={chk.get('accepted')}")
        if chk.get("signature"):
            parts.append(f"signature={chk['signature']}")
        body = "\n".join(parts)
        # Attach docstring if present (installed, not fetched)
        try:
            import importlib
            import inspect

            mod = importlib.import_module(module)
            obj = mod
            for p in attr.split("."):
                obj = getattr(obj, p)
            doc = inspect.getdoc(obj)
            if doc:
                body += "\n\n" + doc[:2000]
        except Exception:
            pass
    else:
        body = "\n".join(parts)

    key = cache_put(
        source=f"installed:{module}" + (f".{attr}" if attr else ""),
        body=body,
        attribution=f"installed module {module} version={info.get('installed_version')}",
        trust="installed_types",
        version=str(info.get("installed_version")),
    )
    return {
        "ok": True,
        "key": key,
        "body": body,
        "trust": "installed_types",
        "attribution": f"installed:{module}",
        "version": info.get("installed_version"),
        "untrusted": False,
        "prefer_installed_types": True,
    }


def record_fetched_excerpt(
    *,
    url: str,
    body: str,
    claimed_version: str | None = None,
) -> dict[str, Any]:
    """
    Cache fetched documentation as **untrusted** evidence.

    Callers must not treat this as authoritative over installed types.
    Remote fetch is not performed here — only recording of already-obtained text
    (keeps core free/offline; no automatic network).
    """
    key = cache_put(
        source=url,
        body=body,
        attribution=f"fetched:{url}",
        trust="untrusted_fetched",
        version=claimed_version,
    )
    return {
        "ok": True,
        "key": key,
        "trust": "untrusted_fetched",
        "untrusted": True,
        "attribution": f"fetched:{url}",
        "warning": "Fetched text is untrusted evidence; prefer installed types/version-matched docs",
    }
