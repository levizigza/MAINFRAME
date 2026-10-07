"""Workbench agent turn — streaming-capable bridge to editor/codingloop/tools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from mainframe.ai import probe_free_inference, run_ai_step
from mainframe.cache import cached_retrieve
from mainframe.config import ensure_state
from mainframe.editor.bridge import (
    apply_verified_patch,
    attach_selection,
    cancel_task,
    chat_to_task,
    propose_reviewable_diffs,
    resume_task,
    set_diagnostics,
)
from mainframe.editor.completion import completion_gate
from mainframe.editor.state import EditorTaskStore
from mainframe.quota import AdmissionController, UsageEstimate


def _ai_paused() -> dict[str, Any]:
    probe = probe_free_inference()
    pd = probe.to_dict() if hasattr(probe, "to_dict") else {}
    available = pd.get("status") in ("available", "ok")
    return {
        "available": available,
        "status": "available" if available else "paused",
        "probe": pd,
    }


def context_chips(task_id: str, store: EditorTaskStore | None = None) -> dict[str, Any]:
    store = store or EditorTaskStore()
    task = store.load(task_id)
    if not task:
        return {"ok": False, "error": "task_not_found"}
    ctx = task.get("context") or {}
    chips = []
    sel = ctx.get("selection")
    if sel:
        chips.append(
            {
                "kind": "selection",
                "path": sel.get("path"),
                "start_line": sel.get("start_line"),
                "end_line": sel.get("end_line"),
                "chars": len(sel.get("text") or ""),
            }
        )
    for d in ctx.get("diagnostics") or []:
        chips.append(
            {
                "kind": "diagnostic",
                "path": d.get("path"),
                "severity": d.get("severity") or d.get("level"),
                "message": (d.get("message") or "")[:200],
            }
        )
    for p in (ctx.get("open_files") or [])[:12]:
        chips.append({"kind": "open_file", "path": p})
    active = ctx.get("active_file")
    if active:
        chips.append({"kind": "active_file", "path": active})
    return {"ok": True, "task_id": task_id, "chips": chips}


def attach_open_files(
    task_id: str,
    *,
    paths: list[str],
    active_file: str | None = None,
    store: EditorTaskStore | None = None,
) -> dict[str, Any]:
    store = store or EditorTaskStore()
    task = store.load(task_id)
    if not task:
        return {"ok": False, "error": "task_not_found"}
    if task.get("cancelled"):
        return {"ok": False, "error": "task_cancelled"}
    ctx = dict(task.get("context") or {})
    ctx["open_files"] = [p.replace("\\", "/") for p in paths]
    if active_file:
        ctx["active_file"] = active_file.replace("\\", "/")
    task["context"] = ctx
    store.save(task)
    return {
        "ok": True,
        "task_id": task_id,
        "open_files": ctx["open_files"],
        "active_file": ctx.get("active_file"),
    }


def tool_read(path: Path, *, max_bytes: int = 100_000) -> dict[str, Any]:
    if not path.is_file():
        return {"ok": False, "error": "not_found", "path": str(path)}
    data = path.read_bytes()[:max_bytes]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return {"ok": False, "error": "binary_or_non_utf8", "path": str(path)}
    return {
        "ok": True,
        "path": str(path).replace("\\", "/"),
        "text": text,
        "truncated": len(data) >= max_bytes,
    }


def tool_retrieve(workspace: Path, query: str) -> dict[str, Any]:
    try:
        hits = cached_retrieve(
            workspace,
            issue_text=query,
            goal=query,
            top_k=8,
        )
        return {"ok": True, "hits": hits}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def propose_from_workspace(
    task_id: str,
    *,
    workspace: Path,
    store: EditorTaskStore | None = None,
    prefer_model: bool = True,
) -> dict[str, Any]:
    """Deterministic-first propose; optional model proposer when Mode B available."""
    from mainframe.codingloop.propose import propose_edits

    store = store or EditorTaskStore()
    task = store.load(task_id)
    if not task:
        return {"ok": False, "error": "task_not_found"}
    if task.get("cancelled"):
        return {"ok": False, "error": "task_cancelled"}

    hypothesis = (task.get("chat") or "")[:500]
    result = propose_edits(
        workspace,
        hypothesis=hypothesis,
        prefer_model=prefer_model,
        task_context=task.get("context") or {},
    )
    edits = list(result.get("edits") or [])
    if edits:
        prop = propose_reviewable_diffs(task_id, edits, store=store)
        result["reviewable"] = prop
    result["task_id"] = task_id
    result["ok"] = True
    return result


def apply_or_reject(
    task_id: str,
    *,
    accept: bool,
    store: EditorTaskStore | None = None,
) -> dict[str, Any]:
    store = store or EditorTaskStore()
    task = store.load(task_id)
    if not task:
        return {"ok": False, "error": "task_not_found"}
    if not accept:
        task["proposed_edits"] = []
        task["proposal"] = None
        task["diff_rejected"] = True
        task["state"] = "rejected"
        store.save(task)
        return {"ok": True, "applied": False, "rejected": True, "task_id": task_id}
    return apply_verified_patch(task_id, store=store)


def agent_turn(
    *,
    message: str,
    workspace: Path,
    task_id: str | None = None,
    selection: dict[str, Any] | None = None,
    diagnostics: list[dict[str, Any]] | None = None,
    open_files: list[str] | None = None,
    active_file: str | None = None,
    auto_propose: bool = True,
) -> dict[str, Any]:
    """
    One workbench agent turn: create/resume task, attach context, optional propose.
    AI generation pauses when Mode B unavailable — deterministic propose may still run.
    """
    ensure_state()
    store = EditorTaskStore()
    ai = _ai_paused()
    events: list[dict[str, Any]] = []

    if task_id:
        task = store.load(task_id)
        if not task:
            return {"ok": False, "error": "task_not_found", "ai": ai}
        if task.get("cancelled"):
            return {"ok": False, "error": "task_cancelled", "ai": ai}
        hist = list(task.get("messages") or [])
        hist.append({"role": "user", "content": message})
        task["messages"] = hist
        task["chat"] = message
        store.save(task)
    else:
        created = chat_to_task(message, workspace=workspace, store=store, source="workbench")
        task = created["task"]
        task_id = task["task_id"]
        task["messages"] = [{"role": "user", "content": message}]
        store.save(task)
        events.append({"type": "task_created", "task_id": task_id})

    if selection:
        attach_selection(
            task_id,
            path=str(selection.get("path") or ""),
            text=str(selection.get("text") or ""),
            start_line=selection.get("start_line"),
            end_line=selection.get("end_line"),
            store=store,
        )
        events.append({"type": "context_selection"})
    if diagnostics is not None:
        set_diagnostics(task_id, diagnostics, store=store)
        events.append({"type": "context_diagnostics", "count": len(diagnostics)})
    if open_files is not None:
        attach_open_files(task_id, paths=open_files, active_file=active_file, store=store)
        events.append({"type": "context_open_files"})

    chips = context_chips(task_id, store=store)
    events.append({"type": "chips", "chips": chips.get("chips")})

    assistant_text = ""
    proposal: dict[str, Any] | None = None

    if not ai["available"]:
        assistant_text = (
            "AI paused — no eligible local model at loopback Ollama. "
            "Deterministic tools still available. Run: python -m mainframe workbench fitness"
        )
        events.append({"type": "ai_paused", "detail": ai["probe"].get("detail")})
        if auto_propose:
            proposal = propose_from_workspace(
                task_id, workspace=workspace, store=store, prefer_model=False
            )
            events.append(
                {"type": "propose", "mode": "deterministic", "ok": proposal.get("ok", True)}
            )
    else:
        ctl = AdmissionController()
        estimate = UsageEstimate(requests=1, tokens=512, context_tokens=4096)
        admit = ctl.admit(
            provider_id="ollama_local",
            estimate=estimate,
            priority="interactive",
            require_cost_gate=True,
        )
        if not admit.allowed:
            assistant_text = "Quota admission denied — try later. Deterministic propose may continue."
            events.append({"type": "quota_denied", "admit": admit.to_dict()})
        else:
            try:
                step = run_ai_step(
                    "You are FreeForge Workbench on local Ollama. Be concise. "
                    f"User: {message}\n"
                    f"Context chips: {json.dumps(chips.get('chips') or [])[:2000]}"
                )
                assistant_text = str(
                    (step.get("text") if isinstance(step, dict) else None)
                    or (step.get("output") if isinstance(step, dict) else None)
                    or (step.get("message") if isinstance(step, dict) else None)
                    or step
                )[:4000]
                events.append({"type": "model_chat", "ok": bool(step.get("ok", True))})
            except Exception as exc:  # noqa: BLE001
                assistant_text = f"Model call failed ({exc}); falling back to deterministic tools."
                events.append({"type": "model_chat", "ok": False, "error": str(exc)})
        if auto_propose:
            proposal = propose_from_workspace(
                task_id, workspace=workspace, store=store, prefer_model=True
            )
            events.append(
                {
                    "type": "propose",
                    "mode": proposal.get("proposer") or "mixed",
                    "edits": len(proposal.get("edits") or []),
                }
            )

    task = store.load(task_id) or task
    hist = list(task.get("messages") or [])
    hist.append({"role": "assistant", "content": assistant_text})
    task["messages"] = hist
    store.save(task)

    return {
        "ok": True,
        "task_id": task_id,
        "ai": ai,
        "assistant": assistant_text,
        "chips": chips.get("chips"),
        "proposal": proposal,
        "events": events,
        "completion_gate": completion_gate(requested=False),
        "cancel": "python -m mainframe editor cancel --task " + str(task_id),
    }


def iter_agent_events(result: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield NDJSON-friendly events for streaming UI."""
    yield {"type": "start", "task_id": result.get("task_id"), "ai": result.get("ai")}
    for ev in result.get("events") or []:
        yield ev
    if result.get("assistant"):
        text = str(result["assistant"])
        chunk_size = 48
        for i in range(0, len(text), chunk_size):
            yield {"type": "assistant_delta", "text": text[i : i + chunk_size]}
    yield {"type": "done", "proposal": result.get("proposal"), "ok": result.get("ok")}


def cancel(task_id: str) -> dict[str, Any]:
    return cancel_task(task_id)


def resume(task_id: str) -> dict[str, Any]:
    return resume_task(task_id)
