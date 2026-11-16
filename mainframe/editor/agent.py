"""Phase 2 agent UX — streaming events, context chips, tool loop, reviewable apply/reject.

UI (extension / workbench overlay) consumes NDJSON events. Patch/verify stay in Python.
When Mode B inference is paused, deterministic retrieve→propose still runs; agent chat
reports paused honestly and never falls back to paid APIs.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, TextIO

from mainframe.ai import probe_free_inference
from mainframe.cache import cached_tool_output
from mainframe.codingloop.propose import propose_fixes
from mainframe.editor.bridge import (
    apply_verified_patch,
    cancel_task,
    chat_to_task,
    propose_reviewable_diffs,
    reject_proposal,
    resume_task,
)
from mainframe.editor.completion import completion_gate
from mainframe.editor.state import EditorTaskStore
from mainframe.tools.invoke import invoke, reset_audit

EventSink = Callable[[dict[str, Any]], None]


def _emit(sink: EventSink | None, event: dict[str, Any]) -> dict[str, Any]:
    ev = {"ts": time.time(), **event}
    if "id" not in ev:
        ev["id"] = f"ev_{uuid.uuid4().hex[:10]}"
    if sink:
        sink(ev)
    return ev


def context_chips(task: dict[str, Any]) -> list[dict[str, Any]]:
    """Selection / active file / diagnostics chips for the agent panel."""
    ctx = task.get("context") or {}
    chips: list[dict[str, Any]] = []
    sel = ctx.get("selection")
    if sel and sel.get("path"):
        chips.append(
            {
                "kind": "selection",
                "path": sel["path"],
                "start_line": sel.get("start_line"),
                "end_line": sel.get("end_line"),
                "preview": (sel.get("text") or "")[:120],
            }
        )
    active = ctx.get("active_file")
    if active and active.get("path"):
        chips.append({"kind": "active_file", "path": active["path"]})
    buffers = ctx.get("buffers") or {}
    for path, buf in buffers.items():
        if buf.get("dirty"):
            chips.append({"kind": "dirty_buffer", "path": path, "version": buf.get("version")})
    for d in (ctx.get("diagnostics") or [])[:8]:
        chips.append(
            {
                "kind": "diagnostic",
                "path": d.get("path"),
                "severity": d.get("severity"),
                "message": (d.get("message") or "")[:160],
            }
        )
    if task.get("workspace"):
        chips.append({"kind": "workspace", "path": str(task["workspace"]).replace("\\", "/")})
    return chips


def _chunk_text(text: str, size: int = 48) -> Iterator[str]:
    if not text:
        return
    for i in range(0, len(text), size):
        yield text[i : i + size]


def _ai_status() -> dict[str, Any]:
    probe = probe_free_inference()
    d = probe.to_dict() if hasattr(probe, "to_dict") else dict(probe or {})
    status = str(d.get("status") or "paused").lower()
    if status in {"available", "ok"}:
        state = "available"
    elif status == "disabled":
        state = "disabled"
    else:
        state = "paused"
    return {
        "state": state,
        "provider": d.get("provider"),
        "detail": d.get("detail") or d.get("message"),
        "free_only": True,
        "probe": d,
    }


def run_agent_turn(
    task_id: str,
    *,
    message: str | None = None,
    store: EditorTaskStore | None = None,
    sink: EventSink | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """
    One agent turn: stream events, run read tools, propose reviewable diffs.

    Does **not** apply patches — UI/CLI must call apply or reject explicitly.
    """
    store = store or EditorTaskStore()
    reset_audit()
    events: list[dict[str, Any]] = []

    def out(ev: dict[str, Any]) -> None:
        events.append(_emit(sink, ev))

    task = store.load(task_id)
    if not task:
        out({"type": "error", "error": "task_not_found"})
        return {"ok": False, "error": "task_not_found", "events": events}
    if task.get("cancelled"):
        out({"type": "error", "error": "task_cancelled"})
        return {"ok": False, "error": "task_cancelled", "events": events}

    def cancelled() -> bool:
        if cancel_check and cancel_check():
            return True
        fresh = store.load(task_id)
        return bool(fresh and fresh.get("cancelled"))

    user_msg = (message if message is not None else task.get("chat") or "").strip()
    if message is not None and message.strip():
        task["chat"] = message.strip()
        hist = list(task.get("chat_history") or [])
        hist.append({"role": "user", "content": message.strip(), "at": time.time()})
        task["chat_history"] = hist[-40:]
        store.save(task)

    out({"type": "status", "phase": "start", "task_id": task_id})
    ai = _ai_status()
    out({"type": "ai_status", **ai})
    # Phase 3: budgeted completion only when Mode B eligible — surface gate, do not invent completions
    gate = completion_gate(requested=True)
    out({
        "type": "completion_gate",
        "enabled": bool(gate.get("enabled")),
        "reason": gate.get("reason"),
        "budgeted": True,
        "eligible_model": bool(gate.get("eligible_model")),
    })

    chips = context_chips(task)
    out({"type": "context_chips", "chips": chips})

    if cancelled():
        out({"type": "cancelled", "side_effects": False})
        return {"ok": False, "cancelled": True, "events": events, "ai": ai}

    workspace = Path(task["workspace"])
    if ai["state"] != "available":
        intro = (
            "Local inference paused (Mode B). "
            "Running deterministic retrieve → tests → propose. "
            "Install Ollama + fitted model for live model turns — no paid fallback."
        )
    else:
        intro = (
            "Mode B available. Running retrieve → tests → propose "
            "(deterministic-first); review before apply."
        )
    for chunk in _chunk_text(intro):
        if cancelled():
            out({"type": "cancelled", "side_effects": False})
            return {"ok": False, "cancelled": True, "events": events, "ai": ai}
        out({"type": "message_delta", "role": "assistant", "delta": chunk})
    out({"type": "message_done", "role": "assistant", "text": intro})

    # --- tool: search (exact-cached read) ---
    call_search = f"call_{uuid.uuid4().hex[:10]}"
    search_args = {"query": user_msg or "bug fix", "goal": user_msg or "repair", "top_k": 5}
    out({"type": "tool_call", "call_id": call_search, "tool": "search", "arguments": search_args})
    search_res = cached_tool_output(
        "search", search_args, root=workspace, call_id=call_search
    )
    search_body = search_res.get("result") if isinstance(search_res.get("result"), dict) else {}
    hits = list(search_body.get("hits") or [])
    out({
        "type": "tool_result",
        "call_id": call_search,
        "tool": "search",
        "result": {
            "ok": search_res.get("ok"),
            "error": search_res.get("error"),
            "hits": hits,
            "exact_cache": search_res.get("exact_cache"),
        },
    })
    # Second identical search proves exact-cache hit (Phase 3)
    call_search2 = f"call_{uuid.uuid4().hex[:10]}"
    search_res2 = cached_tool_output(
        "search", search_args, root=workspace, call_id=call_search2
    )
    out({
        "type": "tool_result",
        "call_id": call_search2,
        "tool": "search",
        "result": {
            "ok": search_res2.get("ok"),
            "exact_cache": search_res2.get("exact_cache"),
            "cache_probe": True,
        },
    })

    if cancelled():
        out({"type": "cancelled", "side_effects": False})
        return {"ok": False, "cancelled": True, "events": events, "ai": ai}

    # Peek at first hit path via file_range when present
    if hits and isinstance(hits[0], dict) and hits[0].get("path"):
        rel = str(hits[0]["path"]).replace("\\", "/")
        call_fr = f"call_{uuid.uuid4().hex[:10]}"
        args = {"path": rel, "start": 1, "end": 40}
        out({"type": "tool_call", "call_id": call_fr, "tool": "file_range", "arguments": args})
        fr = cached_tool_output("file_range", args, root=workspace, call_id=call_fr)
        out({
            "type": "tool_result",
            "call_id": call_fr,
            "tool": "file_range",
            "result": {
                "ok": fr.get("ok"),
                "error": fr.get("error"),
                "path": rel,
                "exact_cache": fr.get("exact_cache"),
            },
        })

    if cancelled():
        out({"type": "cancelled", "side_effects": False})
        return {"ok": False, "cancelled": True, "events": events, "ai": ai}

    # --- tool: tests (reproduce; side-effecting — never exact-cached as success shortcut) ---
    tests_dir = workspace / "tests"
    if tests_dir.is_dir():
        call_tests = f"call_{uuid.uuid4().hex[:10]}"
        test_args = {"target": "tests"}
        out({"type": "tool_call", "call_id": call_tests, "tool": "tests", "arguments": test_args})
        test_res = invoke("tests", test_args, call_id=call_tests, root=workspace)
        test_body = test_res.get("result") if isinstance(test_res.get("result"), dict) else {}
        exit_code = test_body.get("exit_code")
        if exit_code is None:
            exit_code = test_body.get("returncode")
        reproduced = bool(test_res.get("ok")) and test_body.get("passed") is False
        out({
            "type": "tool_result",
            "call_id": call_tests,
            "tool": "tests",
            "result": {
                "ok": test_res.get("ok"),
                "error": test_res.get("error"),
                "exit_code": exit_code,
                "passed": test_body.get("passed"),
                "reproduced_failure": reproduced,
            },
        })

    if cancelled():
        out({"type": "cancelled", "side_effects": False})
        return {"ok": False, "cancelled": True, "events": events, "ai": ai}

    # --- propose: verified memory → deterministic → eligibility-gated local model ---
    hypothesis = user_msg or "Localize and repair failing behavior"
    out({"type": "status", "phase": "propose"})
    from mainframe.memory.verified_patches import lookup_verified

    mem = lookup_verified(goal=hypothesis)
    if mem.get("hit") and mem.get("edits"):
        raw_prop = {
            "proposal_only": True,
            "applied": False,
            "verified": True,
            "edits": list(mem["edits"]),
            "impossible": False,
            "hypothesis": hypothesis,
            "source": "verified_patch_memory",
            "memory_hit": True,
            "fingerprint": mem.get("fingerprint"),
        }
    else:
        raw_prop = propose_fixes(workspace, hypothesis, allow_model=True)
    edits = list(raw_prop.get("edits") or [])
    out({
        "type": "propose_source",
        "source": raw_prop.get("source"),
        "paused": raw_prop.get("paused"),
        "cache_hit": raw_prop.get("cache_hit"),
        "memory_hit": bool(raw_prop.get("memory_hit") or mem.get("hit")),
    })

    if raw_prop.get("impossible"):
        note = raw_prop.get("reason") or "Cannot propose a verified fix."
        for chunk in _chunk_text(note):
            out({"type": "message_delta", "role": "assistant", "delta": chunk})
        out({"type": "message_done", "role": "assistant", "text": note})
        out({
            "type": "done",
            "awaiting_apply": False,
            "impossible": True,
            "proposal": None,
            "ai": ai,
        })
        task["state"] = "blocked"
        task["agent_last"] = {"impossible": True, "reason": note}
        store.save(task)
        return {
            "ok": True,
            "awaiting_apply": False,
            "impossible": True,
            "events": events,
            "ai": ai,
            "task_id": task_id,
        }

    if not edits:
        note = raw_prop.get("reason") or (
            "No proposal from deterministic fixtures or local model. "
            "Mode B paused or model returned no valid edits — no paid fallback."
        )
        for chunk in _chunk_text(note):
            out({"type": "message_delta", "role": "assistant", "delta": chunk})
        out({"type": "message_done", "role": "assistant", "text": note})
        out({
            "type": "done",
            "awaiting_apply": False,
            "proposal": None,
            "ai": ai,
            "propose_paused": bool(raw_prop.get("paused")),
        })
        task["state"] = "open"
        task["agent_last"] = {"no_edits": True, "propose": raw_prop.get("source")}
        store.save(task)
        return {
            "ok": True,
            "awaiting_apply": False,
            "events": events,
            "ai": ai,
            "task_id": task_id,
            "note": note,
            "propose": raw_prop,
        }

    prop = propose_reviewable_diffs(task_id, edits, store=store)
    proposal = prop.get("proposal") or {}
    diffs = proposal.get("reviewable_diffs") or []
    summary = f"Proposed {len(edits)} edit(s). Review unified diff, then Apply or Reject."
    for chunk in _chunk_text(summary):
        out({"type": "message_delta", "role": "assistant", "delta": chunk})
    out({"type": "message_done", "role": "assistant", "text": summary})
    out({
        "type": "proposal",
        "ok": bool(prop.get("ok")),
        "operation_id": proposal.get("operation_id"),
        "edits": edits,
        "reviewable_diffs": diffs,
        "validation_ok": bool(prop.get("ok")),
    })
    out({
        "type": "done",
        "awaiting_apply": bool(prop.get("ok")),
        "operation_id": proposal.get("operation_id"),
        "ai": ai,
    })
    task = store.load(task_id) or task
    task["agent_last"] = {
        "awaiting_apply": bool(prop.get("ok")),
        "operation_id": proposal.get("operation_id"),
        "ai_state": ai["state"],
    }
    store.save(task)
    return {
        "ok": bool(prop.get("ok")),
        "awaiting_apply": bool(prop.get("ok")),
        "proposal": proposal if prop.get("ok") else None,
        "events": events,
        "ai": ai,
        "task_id": task_id,
        "propose": prop,
    }


def stream_agent_turn_ndjson(
    task_id: str,
    *,
    message: str | None = None,
    store: EditorTaskStore | None = None,
    fp: TextIO,
) -> dict[str, Any]:
    """Write one NDJSON object per line to ``fp`` (extension async consumer)."""

    def sink(ev: dict[str, Any]) -> None:
        fp.write(json.dumps(ev, ensure_ascii=True) + "\n")
        fp.flush()

    return run_agent_turn(task_id, message=message, store=store, sink=sink)


def agent_session_from_chat(
    chat: str,
    *,
    workspace: Path,
    store: EditorTaskStore | None = None,
    source: str = "agent",
) -> dict[str, Any]:
    """Create shared task then run one agent turn (non-streaming summary)."""
    store = store or EditorTaskStore()
    created = chat_to_task(chat, workspace=workspace, store=store, source=source)
    if not created.get("ok"):
        return created
    task_id = created["task"]["task_id"]
    turn = run_agent_turn(task_id, message=chat, store=store)
    return {"ok": turn.get("ok"), "task_id": task_id, "created": created, "turn": turn}


# Re-export apply/cancel/resume for UI symmetry
apply_proposal = apply_verified_patch
cancel_agent = cancel_task
resume_agent = resume_task
