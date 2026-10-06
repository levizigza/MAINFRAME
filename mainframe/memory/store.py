"""Local SQLite project memory — isolated per root; no hosted storage."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.config import STATE_DIR, ensure_state
from mainframe.memory.filter import reject_if_unsafe
from mainframe.memory.trust import (
    AUTHORITY,
    authority_score,
    is_trusted_guidance,
    provenance_label,
)

DB_NAME = "project_memory.sqlite"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def project_key(root: Path) -> str:
    return str(root.resolve()).replace("\\", "/").casefold()


def _db_path() -> Path:
    ensure_state()
    mem = STATE_DIR / "memory"
    mem.mkdir(parents=True, exist_ok=True)
    return mem / DB_NAME


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()))
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS entries (
          id TEXT PRIMARY KEY,
          project_key TEXT NOT NULL,
          kind TEXT NOT NULL,
          source_class TEXT NOT NULL,
          title TEXT NOT NULL,
          body TEXT NOT NULL,
          scope_json TEXT,
          source_refs_json TEXT,
          support_hashes_json TEXT,
          verification_status TEXT NOT NULL,
          trusted_guidance INTEGER NOT NULL DEFAULT 0,
          rejected INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          last_validated_at TEXT,
          metadata_json TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_mem_project ON entries(project_key);
        CREATE INDEX IF NOT EXISTS idx_mem_kind ON entries(project_key, kind);
        """
    )
    conn.commit()
    return conn


def _hash_files(root: Path, rels: list[str]) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for rel in rels:
        p = root / rel
        try:
            out[rel.replace("\\", "/")] = hashlib.sha256(p.read_bytes()).hexdigest()
        except OSError:
            out[rel.replace("\\", "/")] = None
    return out


def _new_id(project: str, kind: str, title: str) -> str:
    raw = f"{project}|{kind}|{title}|{_utc()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def remember(
    root: Path,
    *,
    kind: str,
    source_class: str,
    title: str,
    body: str,
    scope: dict[str, Any] | None = None,
    source_refs: list[str] | None = None,
    support_paths: list[str] | None = None,
    verification_status: str = "unverified",
    rejected: bool = False,
    metadata: dict[str, Any] | None = None,
    save_conversation: bool = False,
) -> dict[str, Any]:
    """Insert a memory entry. Generated summaries never become trusted guidance."""
    from mainframe.cost_gate import authorize

    gate = authorize("tool", "local.project_memory_write", local=True)
    if not gate.allowed:
        return {"ok": False, "cost_gate": gate.to_dict()}

    root = root.resolve()
    unsafe = reject_if_unsafe(
        body, paths=support_paths or source_refs, save_conversation=save_conversation
    )
    if not unsafe.get("ok"):
        return {"ok": False, **unsafe, "hosted_storage_used": False, "model_training_used": False}

    # Enforce: generated_summary / external_text / rejected never trusted
    if source_class == "generated_summary":
        verification_status = verification_status if verification_status != "verified" else "unverified"
        # Summaries cannot be verified into trusted guidance
        trusted = False
    elif rejected or verification_status == "rejected":
        verification_status = "rejected"
        rejected = True
        trusted = False
    else:
        trusted = is_trusted_guidance(source_class, verification_status, rejected=rejected)

    # Injected repo instructions must be external_text
    if source_class == "user_instruction" and metadata and metadata.get("from_repository_file"):
        return {
            "ok": False,
            "error": "repository_file_cannot_be_user_instruction",
            "hint": "Store as external_text; it has no authority over the user",
            "hosted_storage_used": False,
        }

    support_hashes = _hash_files(root, support_paths or [])
    eid = _new_id(project_key(root), kind, title)
    now = _utc()
    conn = connect()
    conn.execute(
        """
        INSERT INTO entries(
          id, project_key, kind, source_class, title, body, scope_json,
          source_refs_json, support_hashes_json, verification_status,
          trusted_guidance, rejected, created_at, updated_at, last_validated_at,
          metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            eid,
            project_key(root),
            kind,
            source_class,
            title,
            body,
            json.dumps(scope or {}),
            json.dumps(source_refs or []),
            json.dumps(support_hashes),
            verification_status,
            1 if trusted else 0,
            1 if rejected else 0,
            now,
            now,
            now if trusted else None,
            json.dumps({**(metadata or {}), **provenance_label(source_class)}),
        ),
    )
    conn.commit()
    conn.close()
    return {
        "ok": True,
        "id": eid,
        "trusted_guidance": trusted,
        "verification_status": verification_status,
        "source_class": source_class,
        "support_hashes": support_hashes,
        "hosted_storage_used": False,
        "model_training_used": False,
    }


def revalidate(root: Path, entry_id: str | None = None) -> dict[str, Any]:
    """Expire or mark needs_revalidation when supporting file hashes change."""
    from mainframe.cost_gate import authorize

    gate = authorize("tool", "local.project_memory_revalidate", local=True)
    if not gate.allowed:
        return {"ok": False, "cost_gate": gate.to_dict()}

    root = root.resolve()
    pk = project_key(root)
    conn = connect()
    if entry_id:
        rows = conn.execute(
            "SELECT * FROM entries WHERE project_key=? AND id=?", (pk, entry_id)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM entries WHERE project_key=?", (pk,)).fetchall()

    changed: list[dict[str, Any]] = []
    for row in rows:
        stored = json.loads(row["support_hashes_json"] or "{}")
        if not stored:
            continue
        current = _hash_files(root, list(stored.keys()))
        drift = {p: {"was": stored[p], "now": current.get(p)} for p in stored if stored[p] != current.get(p)}
        if drift:
            conn.execute(
                """
                UPDATE entries SET verification_status=?, trusted_guidance=0,
                  updated_at=?, metadata_json=?
                WHERE id=?
                """,
                (
                    "needs_revalidation",
                    _utc(),
                    json.dumps(
                        {
                            **json.loads(row["metadata_json"] or "{}"),
                            "hash_drift": drift,
                            "revalidated_at": _utc(),
                        }
                    ),
                    row["id"],
                ),
            )
            changed.append({"id": row["id"], "title": row["title"], "drift": drift})
    conn.commit()
    conn.close()
    return {
        "ok": True,
        "invalidated": changed,
        "count": len(changed),
        "hosted_storage_used": False,
    }


def retrieve(
    root: Path,
    *,
    query: str = "",
    kind: str | None = None,
    trusted_only: bool = False,
    limit: int = 20,
) -> dict[str, Any]:
    """Retrieve only relevant memory for this project (isolated)."""
    from mainframe.cost_gate import authorize

    gate = authorize("tool", "local.project_memory_retrieve", local=True)
    if not gate.allowed:
        return {"ok": False, "cost_gate": gate.to_dict()}

    # Revalidate before retrieve so stale hashes are visible
    revalidate(root)

    root = root.resolve()
    pk = project_key(root)
    conn = connect()
    sql = "SELECT * FROM entries WHERE project_key=?"
    args: list[Any] = [pk]
    if kind:
        sql += " AND kind=?"
        args.append(kind)
    if trusted_only:
        sql += " AND trusted_guidance=1 AND rejected=0"
    sql += " ORDER BY trusted_guidance DESC, updated_at DESC"
    rows = conn.execute(sql, args).fetchall()
    conn.close()

    q = query.casefold()
    items: list[dict[str, Any]] = []
    for row in rows:
        d = dict(row)
        d["scope"] = json.loads(d.pop("scope_json") or "{}")
        d["source_refs"] = json.loads(d.pop("source_refs_json") or "[]")
        d["support_hashes"] = json.loads(d.pop("support_hashes_json") or "{}")
        d["metadata"] = json.loads(d.pop("metadata_json") or "{}")
        d["trusted_guidance"] = bool(d["trusted_guidance"])
        d["rejected"] = bool(d["rejected"])
        d["authority"] = authority_score(d["source_class"], d["verification_status"])
        # Relevance filter
        if q:
            blob = f"{d['title']} {d['body']} {d['kind']}".casefold()
            if q not in blob and not any(q in str(x).casefold() for x in d["source_refs"]):
                continue
        # Never present generated_summary as overriding user
        d["may_override_user"] = False
        d["classes_separated"] = True
        items.append(d)
        if len(items) >= limit:
            break

    return {
        "ok": True,
        "project_key": pk,
        "count": len(items),
        "items": items,
        "hosted_storage_used": False,
        "model_training_used": False,
        "full_conversations_saved": False,
    }


def mark_rejected(root: Path, entry_id: str) -> dict[str, Any]:
    """Rejected patches/solutions cannot become trusted guidance."""
    root = root.resolve()
    pk = project_key(root)
    conn = connect()
    conn.execute(
        """
        UPDATE entries SET rejected=1, trusted_guidance=0,
          verification_status='rejected', updated_at=?
        WHERE project_key=? AND id=?
        """,
        (_utc(), pk, entry_id),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id, trusted_guidance, verification_status, rejected FROM entries WHERE id=?",
        (entry_id,),
    ).fetchone()
    conn.close()
    if not row:
        return {"ok": False, "error": "not_found"}
    return {
        "ok": True,
        "id": row["id"],
        "trusted_guidance": bool(row["trusted_guidance"]),
        "verification_status": row["verification_status"],
        "rejected": bool(row["rejected"]),
    }


def clear_project(root: Path) -> dict[str, Any]:
    """Test helper: wipe one project's entries only."""
    pk = project_key(root)
    conn = connect()
    conn.execute("DELETE FROM entries WHERE project_key=?", (pk,))
    conn.commit()
    conn.close()
    return {"ok": True, "project_key": pk}
