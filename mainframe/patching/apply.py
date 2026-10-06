"""Apply validated patch batches bound to a base snapshot; selective rollback."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any

from mainframe.cost_gate import authorize
from mainframe.patching.io_preserve import read_preserved, write_preserved
from mainframe.patching.journal import (
    begin_journal,
    complete_journal,
    mark_written,
    recover_journal,
    save_preimage,
)
from mainframe.patching.snapshot import create_snapshot, load_snapshot, verify_against_disk
from mainframe.patching.validate import validate_batch


def apply_batch(
    root: Path,
    edits: list[dict[str, Any]],
    *,
    snapshot_id: str,
    scope_paths: list[str] | None = None,
    simulate_interrupt_after: int | None = None,
) -> dict[str, Any]:
    """
    Validate entire batch, then write file-by-file with journaling.

    ``simulate_interrupt_after``: for acceptance — stop after N successful writes
    leaving journal ``interrupted`` (recovery restores those files only).
    Never claims multi-file filesystem atomicity.
    """
    gate = authorize("tool", "local.patch_apply_batch", local=True)
    if not gate.allowed:
        return {"ok": False, "cost_gate": gate.to_dict()}

    root = root.resolve()
    plan = validate_batch(root, edits, snapshot_id=snapshot_id, scope_paths=scope_paths)
    if not plan.get("ok"):
        return {**plan, "applied": False, "side_effects": False}

    batch_id = uuid.uuid4().hex[:16]
    jdir = begin_journal(batch_id, snapshot_id=snapshot_id, root=str(root))
    applied: list[dict[str, Any]] = []

    try:
        for n, item in enumerate(plan["planned"]):
            rel = item["path"]
            path = root / rel
            fb = read_preserved(path)
            # Re-check hash immediately before write (concurrent edit race)
            now_hash = hashlib.sha256(fb.raw).hexdigest()
            if now_hash != item["content_sha256"]:
                complete_journal(jdir, status="aborted_stale")
                # Roll back what we already wrote in this batch
                rec = recover_journal(batch_id, root)
                return {
                    "ok": False,
                    "error": "concurrent_modification_detected",
                    "path": rel,
                    "applied_before_abort": applied,
                    "recovery": rec,
                    "filesystem_atomicity_claimed": False,
                    "working_tree_reset": False,
                }
            pre = save_preimage(jdir, rel, fb.raw)
            after = fb.text.replace(item["old"], item["new"], 1)
            write_meta = write_preserved(path, after, fb)
            mark_written(jdir, rel, pre)
            applied.append(
                {
                    "path": rel,
                    "unified_diff": item["unified_diff"],
                    "new_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "io": write_meta,
                    "agent_owned": True,
                }
            )
            if simulate_interrupt_after is not None and (n + 1) >= simulate_interrupt_after:
                complete_journal(jdir, status="interrupted")
                return {
                    "ok": False,
                    "error": "interrupted_multi_file_write",
                    "batch_id": batch_id,
                    "snapshot_id": snapshot_id,
                    "applied": applied,
                    "filesystem_atomicity_claimed": False,
                    "journal_status": "interrupted",
                    "hint": "Call recover(batch_id) to restore agent-written files only",
                }
        complete_journal(jdir, status="completed")
        return {
            "ok": True,
            "batch_id": batch_id,
            "snapshot_id": snapshot_id,
            "applied": applied,
            "reviewable_diffs": [a["unified_diff"] for a in applied],
            "filesystem_atomicity_claimed": False,
            "working_tree_reset": False,
        }
    except Exception as exc:  # noqa: BLE001
        complete_journal(jdir, status="failed")
        rec = recover_journal(batch_id, root)
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "batch_id": batch_id,
            "recovery": rec,
            "filesystem_atomicity_claimed": False,
            "working_tree_reset": False,
        }


def rollback_batch(root: Path, batch_id: str) -> dict[str, Any]:
    """Selective rollback of agent-owned edits from journal preimages only."""
    gate = authorize("tool", "local.patch_rollback", local=True)
    if not gate.allowed:
        return {"ok": False, "cost_gate": gate.to_dict()}
    out = recover_journal(batch_id, root.resolve())
    out["selective"] = True
    out["entire_working_tree_reset"] = False
    return out


def inspect_and_snapshot(root: Path, paths: list[str]) -> dict[str, Any]:
    gate = authorize("tool", "local.patch_snapshot", local=True)
    if not gate.allowed:
        return {"ok": False, "cost_gate": gate.to_dict()}
    return create_snapshot(root.resolve(), paths)
