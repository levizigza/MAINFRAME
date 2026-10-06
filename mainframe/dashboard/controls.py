"""Stop / resume controls — reuse existing FreeForge stores; no duplicate work."""

from __future__ import annotations

from typing import Any

from mainframe.editor.bridge import cancel_task as editor_cancel
from mainframe.editor.bridge import resume_task as editor_resume
from mainframe.workflows.receipts import WorkflowReceiptStore


def stop_task(task_id: str, *, kind: str | None = None) -> dict[str, Any]:
    """
    Cancel new effects. Completed effects remain recorded.
    Does not re-deliver or change destinations.
    """
    if task_id.startswith("edt_") or kind == "editor":
        out = editor_cancel(task_id)
        return {
            **out,
            "control": "stop",
            "completed_effects_preserved": True,
            "outbound_retargeted": False,
            "work_rerun": False,
        }

    # Workflow run
    store = WorkflowReceiptStore()
    run = store.get_run(task_id)
    if run:
        store.request_cancel(task_id)
        return {
            "ok": True,
            "control": "stop",
            "task_id": task_id,
            "kind": "workflow",
            "cancelled": True,
            "completed_effects_preserved": True,
            "outbound_retargeted": False,
            "work_rerun": False,
            "prior_state": run.get("state"),
        }

    return {"ok": False, "error": "unknown_task", "task_id": task_id, "work_rerun": False}


def resume_task(task_id: str, *, kind: str | None = None) -> dict[str, Any]:
    """
    Resume only when not cancelled. Does not invent a second execution of completed ops.
    Caller / CLI still runs the workflow resume — this records the control intent.
    """
    if task_id.startswith("edt_") or kind == "editor":
        out = editor_resume(task_id)
        return {
            **out,
            "control": "resume",
            "work_rerun_of_completed": False,
            "note": "Editor resume does not re-apply a successful patch (operation_id dedupe).",
        }

    store = WorkflowReceiptStore()
    run = store.get_run(task_id)
    if not run:
        return {"ok": False, "error": "unknown_task", "task_id": task_id}
    if run.get("cancel_requested") or run.get("state") == "cancelled":
        return {
            "ok": False,
            "error": "cancelled_not_resumable",
            "task_id": task_id,
            "work_rerun": False,
        }
    return {
        "ok": True,
        "control": "resume",
        "task_id": task_id,
        "kind": "workflow",
        "hint": "Use: python -m mainframe workflow run --resume-run-id <id> (when supported) "
        "or re-open the fixture workdir; succeeded steps stay suppressed.",
        "work_rerun_of_completed": False,
        "state": run.get("state"),
    }
