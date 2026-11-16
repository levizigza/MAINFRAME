"""Verified-patch memory — reuse edits that already passed tests (zero model calls)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.config import STATE_DIR, ensure_state

STORE_NAME = "verified_patches"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def store_root() -> Path:
    ensure_state()
    root = STATE_DIR / STORE_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def fingerprint_goal(*, goal: str, paths: list[str] | None = None) -> str:
    # Goal-only key so lookup(goal=...) matches remember(goal=..., paths=...).
    # paths are stored on the doc for diagnostics, not part of the fingerprint.
    _ = paths
    blob = json.dumps({"goal": (goal or "").strip().lower()}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:24]


def remember_verified(
    *,
    goal: str,
    edits: list[dict[str, Any]],
    paths: list[str] | None = None,
    tests_ok: bool = True,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not tests_ok or not edits:
        return {"ok": False, "error": "refused_unverified_or_empty"}
    fp = fingerprint_goal(goal=goal, paths=paths or [e.get("path", "") for e in edits])
    path = store_root() / f"{fp}.json"
    doc = {
        "fingerprint": fp,
        "goal": goal,
        "paths": paths or [e.get("path") for e in edits],
        "edits": edits,
        "tests_ok": True,
        "saved_at": _utc(),
        "meta": meta or {},
    }
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "fingerprint": fp, "path": str(path)}


def lookup_verified(*, goal: str, paths: list[str] | None = None) -> dict[str, Any]:
    fp = fingerprint_goal(goal=goal, paths=paths)
    path = store_root() / f"{fp}.json"
    if not path.is_file():
        return {"ok": False, "hit": False, "fingerprint": fp}
    doc = json.loads(path.read_text(encoding="utf-8"))
    return {
        "ok": True,
        "hit": True,
        "fingerprint": fp,
        "edits": list(doc.get("edits") or []),
        "saved_at": doc.get("saved_at"),
        "source": "verified_patch_memory",
    }
