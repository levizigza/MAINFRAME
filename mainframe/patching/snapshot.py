"""Base snapshots bind patches to inspected file hashes (scoped paths only)."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.config import STATE_DIR, ensure_state
from mainframe.patching.io_preserve import read_preserved


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def snapshot_dir() -> Path:
    ensure_state()
    d = STATE_DIR / "patch_snapshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def create_snapshot(root: Path, paths: list[str]) -> dict[str, Any]:
    """
    Capture content hashes (+ metadata) for scoped paths only.
    Does not copy the whole working tree.
    """
    root = root.resolve()
    sid = uuid.uuid4().hex[:16]
    files: dict[str, Any] = {}
    for rel in paths:
        rel_n = rel.replace("\\", "/")
        path = (root / rel_n).resolve()
        if not str(path).startswith(str(root)):
            return {"ok": False, "error": "path_escape", "path": rel_n}
        if not path.is_file():
            return {"ok": False, "error": "missing_file", "path": rel_n}
        fb = read_preserved(path)
        files[rel_n] = {
            "sha256": hashlib.sha256(fb.raw).hexdigest(),
            "size": len(fb.raw),
            "encoding": fb.encoding,
            "newline": fb.newline,
            "mode": fb.mode,
            "mtime_ns": getattr(path.stat(), "st_mtime_ns", None),
        }
    meta = {
        "snapshot_id": sid,
        "root": str(root),
        "created_at": _utc(),
        "paths": sorted(files.keys()),
        "files": files,
        "filesystem_atomicity_claimed": False,
    }
    (snapshot_dir() / f"{sid}.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
    return {"ok": True, **meta}


def load_snapshot(snapshot_id: str) -> dict[str, Any] | None:
    p = snapshot_dir() / f"{snapshot_id}.json"
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def verify_against_disk(root: Path, snap: dict[str, Any]) -> dict[str, Any]:
    """Detect modifications after inspection (hash drift)."""
    root = root.resolve()
    stale: list[dict[str, Any]] = []
    ok_paths: list[str] = []
    for rel, info in (snap.get("files") or {}).items():
        path = root / rel
        if not path.is_file():
            stale.append({"path": rel, "reason": "missing"})
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != info.get("sha256"):
            stale.append(
                {
                    "path": rel,
                    "reason": "hash_mismatch_after_inspection",
                    "expected": info.get("sha256"),
                    "actual": actual,
                }
            )
        else:
            ok_paths.append(rel)
    return {
        "ok": len(stale) == 0,
        "fresh": ok_paths,
        "stale": stale,
        "snapshot_id": snap.get("snapshot_id"),
    }
