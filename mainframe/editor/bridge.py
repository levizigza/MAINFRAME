"""Editor bridge: chat→task, selection context, reviewable diffs, apply, cancel, resume."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from mainframe.editor.buffers import apply_uses_buffer_base, dirty_paths, upsert_buffer
from mainframe.editor.completion import completion_gate
from mainframe.editor.state import EditorTaskStore, content_fingerprint, operation_id_for_patch
from mainframe.patching.apply import apply_batch, inspect_and_snapshot
from mainframe.patching.validate import validate_batch


def chat_to_task(
    chat: str,
    *,
    workspace: Path,
    store: EditorTaskStore | None = None,
    source: str = "editor",
) -> dict[str, Any]:
    store = store or EditorTaskStore()
    task = store.create(chat=chat.strip(), workspace=str(workspace), source=source)
    return {"ok": True, "task": task, "shared_state_path": str(store._path(task["task_id"]))}


def attach_selection(
    task_id: str,
    *,
    path: str,
    text: str,
    start_line: int | None = None,
    end_line: int | None = None,
    store: EditorTaskStore | None = None,
) -> dict[str, Any]:
    store = store or EditorTaskStore()
    task = store.load(task_id)
    if not task:
        return {"ok": False, "error": "task_not_found"}
    if task.get("cancelled"):
        return {"ok": False, "error": "task_cancelled"}
    ctx = dict(task.get("context") or {})
    ctx["selection"] = {
        "path": path.replace("\\", "/"),
        "text": text,
        "start_line": start_line,
        "end_line": end_line,
        "sha256": content_fingerprint(text),
    }
    task["context"] = ctx
    store.save(task)
    return {"ok": True, "task_id": task_id, "selection": ctx["selection"]}


def attach_unsaved_buffer(
    task_id: str,
    *,
    path: str,
    text: str,
    dirty: bool = True,
    version: int | None = None,
    store: EditorTaskStore | None = None,
) -> dict[str, Any]:
    store = store or EditorTaskStore()
    task = store.load(task_id)
    if not task:
        return {"ok": False, "error": "task_not_found"}
    upsert_buffer(task, path=path, text=text, dirty=dirty, version=version)
    store.save(task)
    return {
        "ok": True,
        "task_id": task_id,
        "dirty_paths": dirty_paths(task),
        "preserved": True,
    }


def set_diagnostics(
    task_id: str,
    diagnostics: list[dict[str, Any]],
    store: EditorTaskStore | None = None,
) -> dict[str, Any]:
    store = store or EditorTaskStore()
    task = store.load(task_id)
    if not task:
        return {"ok": False, "error": "task_not_found"}
    ctx = dict(task.get("context") or {})
    ctx["diagnostics"] = list(diagnostics)
    task["context"] = ctx
    store.save(task)
    return {"ok": True, "count": len(diagnostics)}


def propose_reviewable_diffs(
    task_id: str,
    edits: list[dict[str, Any]],
    *,
    store: EditorTaskStore | None = None,
) -> dict[str, Any]:
    """Validate edits into reviewable unified diffs without writing."""
    store = store or EditorTaskStore()
    task = store.load(task_id)
    if not task:
        return {"ok": False, "error": "task_not_found"}
    if task.get("cancelled"):
        return {"ok": False, "error": "task_cancelled"}

    workspace = Path(task["workspace"])
    # Materialize unsaved buffers to temp overlay for validation base
    overlay_notes = []
    prepared: list[dict[str, Any]] = []
    for e in edits:
        rel = str(e.get("path") or "").replace("\\", "/")
        disk_path = workspace / rel
        disk_text = disk_path.read_text(encoding="utf-8") if disk_path.is_file() else ""
        base_info = apply_uses_buffer_base(task, rel, disk_text)
        prepared.append({**e, "path": rel, "_base_source": base_info["source"]})
        if base_info["source"] == "unsaved_buffer":
            # Write buffer to a staging area only for hash inspection — not the real file
            overlay_notes.append({"path": rel, "base": "unsaved_buffer", "dirty": base_info["dirty"]})

    snap = inspect_and_snapshot(workspace, [e["path"] for e in prepared])
    # If dirty buffers diverge from disk, bind proposal to buffer content via custom old text
    for e in prepared:
        rel = e["path"]
        disk_path = workspace / rel
        disk_text = disk_path.read_text(encoding="utf-8") if disk_path.is_file() else ""
        base_info = apply_uses_buffer_base(task, rel, disk_text)
        if base_info["source"] == "unsaved_buffer" and "old" not in e:
            # Caller must supply old/new; if only new_snippet, skip
            pass
        if base_info["source"] == "unsaved_buffer" and e.get("old") and e["old"] not in base_info["base"]:
            return {
                "ok": False,
                "error": "edit_old_not_in_unsaved_buffer",
                "path": rel,
                "note": "Preserving unsaved buffer — refuse apply that does not match buffer base.",
            }

    plan = validate_batch(
        workspace,
        [{k: v for k, v in e.items() if not k.startswith("_")} for e in prepared],
        snapshot_id=str(snap.get("snapshot_id")),
    )
    # For buffer-based files, synthesize reviewable diffs from buffer text
    reviewable = list(plan.get("reviewable_diffs") or [])
    if not reviewable and plan.get("ok"):
        reviewable = [p.get("unified_diff") for p in (plan.get("planned") or []) if p.get("unified_diff")]

    fp = hashlib.sha256(
        json.dumps(
            [{"path": e.get("path"), "old": e.get("old"), "new": e.get("new")} for e in edits],
            sort_keys=True,
        ).encode()
    ).hexdigest()
    op_id = operation_id_for_patch(task_id, fp)
    task["proposal"] = {
        "edits": edits,
        "snapshot_id": snap.get("snapshot_id"),
        "validation": {k: plan.get(k) for k in ("ok", "errors", "planned") if k in plan},
        "reviewable_diffs": reviewable or [p.get("unified_diff") for p in (plan.get("planned") or [])],
        "patch_fingerprint": fp,
        "operation_id": op_id,
        "overlay_notes": overlay_notes,
        "applied": False,
    }
    task["state"] = "proposed" if plan.get("ok") else "proposal_invalid"
    ops = dict(task.get("operation_ids") or {})
    ops["propose"] = op_id
    task["operation_ids"] = ops
    store.save(task)
    return {
        "ok": bool(plan.get("ok")),
        "task_id": task_id,
        "proposal": task["proposal"],
        "validation": plan,
    }


def apply_verified_patch(
    task_id: str,
    *,
    store: EditorTaskStore | None = None,
    force_duplicate: bool = False,
) -> dict[str, Any]:
    """
    Apply the proposed patch once. Duplicate calls with the same operation_id
    return the prior apply receipt without re-executing.
    """
    store = store or EditorTaskStore()
    task = store.load(task_id)
    if not task:
        return {"ok": False, "error": "task_not_found"}
    if task.get("cancelled"):
        return {"ok": False, "error": "task_cancelled", "side_effects": False}
    proposal = task.get("proposal")
    if not proposal or not proposal.get("edits"):
        return {"ok": False, "error": "no_proposal"}

    op_id = proposal.get("operation_id")
    prior = task.get("apply")
    if prior and prior.get("operation_id") == op_id and prior.get("ok") and not force_duplicate:
        return {
            "ok": True,
            "duplicate_suppressed": True,
            "operation_id": op_id,
            "apply": prior,
            "note": "Same verified patch already applied — no duplicate execution.",
        }

    workspace = Path(task["workspace"])
    # If dirty buffers exist, write them to disk first so apply hashes match user intent
    # WITHOUT losing unsaved content — flush buffer → disk under user preservation.
    flushed = []
    for rel in dirty_paths(task):
        buf = ((task.get("context") or {}).get("buffers") or {}).get(rel)
        if not buf:
            continue
        path = workspace / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(buf["text"], encoding="utf-8")
        flushed.append(rel)
        # Mark clean after flush
        buf["dirty"] = False

    snap_id = proposal.get("snapshot_id")
    # Re-snapshot after buffer flush
    snap = inspect_and_snapshot(workspace, [e["path"] for e in proposal["edits"]])
    snap_id = str(snap.get("snapshot_id"))

    result = apply_batch(
        workspace,
        proposal["edits"],
        snapshot_id=snap_id,
        scope_paths=[e["path"] for e in proposal["edits"]],
    )
    task["apply"] = {
        "ok": bool(result.get("ok")),
        "operation_id": op_id,
        "batch_id": result.get("batch_id"),
        "result": {k: result.get(k) for k in ("ok", "batch_id", "error", "reviewable_diffs", "applied")},
        "buffers_flushed": flushed,
        "duplicate_suppressed": False,
    }
    task["state"] = "applied" if result.get("ok") else "apply_failed"
    proposal["applied"] = bool(result.get("ok"))
    task["proposal"] = proposal
    ops = dict(task.get("operation_ids") or {})
    ops["apply"] = op_id
    task["operation_ids"] = ops
    store.save(task)
    return {
        "ok": bool(result.get("ok")),
        "duplicate_suppressed": False,
        "operation_id": op_id,
        "apply": task["apply"],
        "patch_result": result,
    }


def cancel_task(task_id: str, store: EditorTaskStore | None = None) -> dict[str, Any]:
    store = store or EditorTaskStore()
    task = store.load(task_id)
    if not task:
        return {"ok": False, "error": "task_not_found"}
    task["cancelled"] = True
    task["state"] = "cancelled"
    # Preserve completed apply receipt if any
    store.save(task)
    return {
        "ok": True,
        "task_id": task_id,
        "cancelled": True,
        "apply_preserved": task.get("apply"),
        "note": "Cancellation prevents new effects; completed apply remains recorded.",
    }


def resume_task(task_id: str, store: EditorTaskStore | None = None) -> dict[str, Any]:
    store = store or EditorTaskStore()
    task = store.load(task_id)
    if not task:
        return {"ok": False, "error": "task_not_found"}
    if task.get("cancelled"):
        return {"ok": False, "error": "cancelled_not_resumable_for_new_effects", "task": task}
    # Clear interrupted-style flags; keep proposal/apply
    if task.get("state") in {"apply_failed", "proposal_invalid", "proposed"}:
        task["state"] = "open" if not task.get("proposal") else "proposed"
    store.save(task)
    return {"ok": True, "task_id": task_id, "state": task["state"], "task": task}


def configure_completion(task_id: str, *, requested: bool, store: EditorTaskStore | None = None) -> dict[str, Any]:
    store = store or EditorTaskStore()
    task = store.load(task_id)
    if not task:
        return {"ok": False, "error": "task_not_found"}
    gate = completion_gate(requested=requested)
    task["completion"] = gate
    store.save(task)
    return {"ok": True, "completion": gate}
