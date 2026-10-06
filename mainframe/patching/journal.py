"""Patch journal for recovery when multi-file atomicity is unavailable."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.config import STATE_DIR, ensure_state


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def journal_root() -> Path:
    ensure_state()
    d = STATE_DIR / "patch_journal"
    d.mkdir(parents=True, exist_ok=True)
    return d


def begin_journal(batch_id: str, *, snapshot_id: str, root: str) -> Path:
    jdir = journal_root() / batch_id
    jdir.mkdir(parents=True, exist_ok=True)
    (jdir / "meta.json").write_text(
        json.dumps(
            {
                "batch_id": batch_id,
                "snapshot_id": snapshot_id,
                "root": root,
                "started_at": _utc(),
                "status": "in_progress",
                "filesystem_atomicity_claimed": False,
                "files_written": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return jdir


def save_preimage(jdir: Path, rel: str, raw: bytes) -> Path:
    safe = rel.replace("\\", "/").replace("/", "__")
    dest = jdir / f"preimage__{safe}"
    dest.write_bytes(raw)
    return dest


def mark_written(jdir: Path, rel: str, preimage: Path) -> None:
    meta_path = jdir / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.setdefault("files_written", []).append(
        {"path": rel.replace("\\", "/"), "preimage": preimage.name, "at": _utc()}
    )
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def complete_journal(jdir: Path, status: str = "completed") -> None:
    meta_path = jdir / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["status"] = status
    meta["finished_at"] = _utc()
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def load_journal(batch_id: str) -> dict[str, Any] | None:
    jdir = journal_root() / batch_id
    meta_path = jdir / "meta.json"
    if not meta_path.is_file():
        return None
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["_jdir"] = str(jdir)
    return meta


def recover_journal(batch_id: str, root: Path) -> dict[str, Any]:
    """
    Restore only files this agent batch wrote (from preimages).
    Does not reset the working tree; leaves unrelated user changes alone.
    """
    meta = load_journal(batch_id)
    if not meta:
        return {"ok": False, "error": "journal_not_found", "batch_id": batch_id}
    jdir = Path(meta["_jdir"])
    root = root.resolve()
    restored: list[str] = []
    for entry in meta.get("files_written") or []:
        rel = entry["path"]
        pre = jdir / entry["preimage"]
        if not pre.is_file():
            continue
        dest = (root / rel).resolve()
        if not str(dest).startswith(str(root)):
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pre, dest)
        restored.append(rel)
    complete_journal(jdir, status="recovered")
    return {
        "ok": True,
        "batch_id": batch_id,
        "restored": restored,
        "unrelated_files_untouched": True,
        "working_tree_reset": False,
        "filesystem_atomicity_claimed": False,
    }
