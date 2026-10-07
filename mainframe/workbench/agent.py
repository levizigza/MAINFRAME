"""Workbench agent session — chat/context/tools/diff apply via MAINFRAME bridges."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mainframe.ai import probe_free_inference, run_ai_step
from mainframe.codingloop.loop import propose_fixes
from mainframe.config import STATE_DIR, ensure_state
from mainframe.editor.bridge import (
    apply_verified_patch,
    attach_selection,
    cancel_task,
    chat_to_task,
    propose_reviewable_diffs,
    resume_task,
)
from mainframe.editor.state import EditorTaskStore

SESSIONS = STATE_DIR / "workbench_sessions"


def _ensure() -> None:
    ensure_state()
    SESSIONS.mkdir(parents=True, exist_ok=True)


def _load_session(session_id: str) -> tuple[Path, dict[str, Any]] | tuple[None, dict[str, Any]]:
    sp = SESSIONS / f"{session_id}.json"
    if not sp.is_file():
        return None, {"ok": False, "error": "session_not_found"}
    return sp, json.loads(sp.read_text(encoding="utf-8"))


def start_session(*, workspace: Path | str, chat: str) -> dict[str, Any]:
    """Create editor task + workbench session (streaming UI consumes same task id)."""
    _ensure()
    ws = Path(workspace)
    out = chat_to_task(chat, workspace=ws, source="workbench")
    if not out.get("ok"):
        return out
    task = out["task"]
    tid = task["task_id"]
    session = {
        "session_id": f"wbs_{tid}",
        "task_id": tid,
        "workspace": str(ws),
        "messages": [{"role": "user", "content": chat}],
        "ai_probe": probe_free_inference().to_dict(),
        "cancelled": False,
        "context_chips": [],
    }
    path = SESSIONS / f"{session['session_id']}.json"
    path.write_text(json.dumps(session, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "session": session, "path": str(path)}


def attach_context(
    session_id: str,
    *,
    path: str,
    text: str,
    start_line: int | None = None,
    end_line: int | None = None,
) -> dict[str, Any]:
    _ensure()
    sp, session = _load_session(session_id)
    if sp is None:
        return session
    if session.get("cancelled"):
        return {"ok": False, "error": "session_cancelled"}
    att = attach_selection(
        session["task_id"],
        path=path,
        text=text,
        start_line=start_line,
        end_line=end_line,
    )
    if not att.get("ok"):
        return att
    session.setdefault("context_chips", []).append(
        {"path": path, "start_line": start_line, "end_line": end_line}
    )
    sp.write_text(json.dumps(session, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "session_id": session_id, "selection": att.get("selection")}


def agent_turn(
    session_id: str,
    *,
    message: str,
    use_model: bool = True,
) -> dict[str, Any]:
    """
    One agent turn: deterministic propose first; optional local model when available.
    Never calls paid/hosted providers.
    """
    _ensure()
    sp, session = _load_session(session_id)
    if sp is None:
        return session
    if session.get("cancelled"):
        return {"ok": False, "error": "session_cancelled", "fallback_used": False}

    session.setdefault("messages", []).append({"role": "user", "content": message})
    workspace = Path(session["workspace"])
    probe = probe_free_inference()
    session["ai_probe"] = probe.to_dict()

    proposal = propose_fixes(workspace, message, allow_model=use_model)
    model_note: dict[str, Any] | None = None
    source = proposal.get("source") or "deterministic"

    if (
        use_model
        and not proposal.get("edits")
        and not proposal.get("impossible")
        and probe.status not in ("available", "ok")
    ):
        model_note = {
            "ok": False,
            "paused": True,
            "fallback_used": False,
            "detail": probe.detail,
        }
    elif use_model and proposal.get("model_step"):
        model_note = proposal.get("model_step")
    elif (
        use_model
        and not proposal.get("edits")
        and not proposal.get("impossible")
        and probe.status in ("available", "ok")
        and not proposal.get("model_step")
    ):
        # Advisory plan only — never invent file paths as applied edits
        prompt = (
            "You are FreeForge local coding agent. Reply with a short plan only — "
            "do not invent file paths. Task:\n"
            + message
        )
        model_note = run_ai_step(prompt)
        if model_note.get("paused") or not model_note.get("ok"):
            model_note = {
                "ok": False,
                "paused": True,
                "fallback_used": False,
                "detail": model_note.get("message") or model_note.get("detail"),
            }

    staged = None
    if proposal.get("edits"):
        staged = propose_reviewable_diffs(session["task_id"], proposal["edits"])

    assistant = {
        "role": "assistant",
        "content": (
            "Proposed deterministic edits for review."
            if proposal.get("edits") and source == "deterministic"
            else (
                "Proposed local-model edits for review."
                if proposal.get("edits")
                else (
                    "No deterministic edits; AI paused — continue editing locally."
                    if (model_note or {}).get("paused")
                    else "No safe edits proposed."
                )
            )
        ),
        "proposal": {
            "edits_n": len(proposal.get("edits") or []),
            "impossible": proposal.get("impossible"),
            "proposal_only": True,
            "source": source,
        },
        "model": {
            "used": bool(
                (model_note and model_note.get("ok") and not model_note.get("paused"))
                or source == "local_model"
            ),
            "paused": bool((model_note or {}).get("paused")),
            "fallback_used": False,
        },
    }
    session["messages"].append(assistant)
    sp.write_text(json.dumps(session, indent=2) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "session_id": session_id,
        "task_id": session["task_id"],
        "proposal": proposal,
        "staged_diffs": staged,
        "model": model_note,
        "assistant": assistant,
        "ai_state": probe.status,
    }


def apply_session_patch(
    session_id: str,
    *,
    accept: bool,
) -> dict[str, Any]:
    """Accept or reject the pending reviewable proposal. Never silent overwrite."""
    _ensure()
    sp, session = _load_session(session_id)
    if sp is None:
        return session
    store = EditorTaskStore()
    task = store.load(session["task_id"])
    if not task:
        return {"ok": False, "error": "task_not_found"}

    if not accept:
        task["proposal"] = None
        task["pending_patch"] = None
        task["state"] = "proposal_rejected"
        store.save(task)
        session["last_apply"] = {"applied": False, "rejected": True}
        sp.write_text(json.dumps(session, indent=2) + "\n", encoding="utf-8")
        return {"ok": True, "applied": False, "rejected": True}

    proposal = task.get("proposal")
    if not proposal or not proposal.get("edits"):
        return {"ok": False, "error": "no_pending_patch"}

    result = apply_verified_patch(session["task_id"], store=store)
    session["last_apply"] = {
        "applied": bool(result.get("ok")),
        "rejected": False,
        "operation_id": result.get("operation_id"),
    }
    sp.write_text(json.dumps(session, indent=2) + "\n", encoding="utf-8")
    return result


def cancel_session(session_id: str) -> dict[str, Any]:
    _ensure()
    sp, session = _load_session(session_id)
    if sp is None:
        return session
    session["cancelled"] = True
    sp.write_text(json.dumps(session, indent=2) + "\n", encoding="utf-8")
    return cancel_task(session["task_id"])


def resume_session(session_id: str) -> dict[str, Any]:
    _ensure()
    sp, session = _load_session(session_id)
    if sp is None:
        return session
    session["cancelled"] = False
    sp.write_text(json.dumps(session, indent=2) + "\n", encoding="utf-8")
    return resume_task(session["task_id"])
