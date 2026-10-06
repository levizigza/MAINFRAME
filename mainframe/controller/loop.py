"""Adaptive task controller loop."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.automation import run_task
from mainframe.config import RUNS_DIR, ensure_state
from mainframe.controller.classify import classify_mode, mode_name
from mainframe.controller.escalate import escalate, progress_signature, should_stop_no_progress
from mainframe.controller.types import Budgets, ControllerResult, EvidenceItem, Journal, Mode


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_checkpoint(payload: dict[str, Any]) -> Path:
    ensure_state()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = RUNS_DIR / f"controller-checkpoint-{stamp}.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _run_deterministic(task: dict[str, Any]) -> dict[str, Any]:
    op = str(task.get("deterministic_op") or task.get("kind") or "echo")
    params = dict(task.get("params") or {})
    # Map aliases
    if op == "checksum":
        op = "workspace-checksum"
    if op == "status":
        return {"ok": True, "status": "deterministic_status", "message": "ready"}
    result = run_task(op, params)
    return {
        "ok": result.ok,
        "task": result.task,
        "output": result.output,
        "error": result.error,
        "digest": (result.output or {}).get("sha256"),
    }


def _run_direct_bounded(task: dict[str, Any], journal: Journal, turn: int) -> dict[str, Any]:
    """Bounded direct execution — fixture/mock when no model; no full agent ceremony."""
    journal.add_hypothesis("Bounded task can complete with a single direct step.")
    goal = str(task.get("goal") or "")
    # Deterministic stand-in for direct model on local fixtures
    if task.get("simulate_model_fail"):
        return {
            "ok": False,
            "status": "model_step_failed",
            "error": "simulated_verification_failure",
            "digest": "fail",
        }
    if "extract" in goal.lower() and "json" in goal.lower():
        return {"ok": True, "status": "direct_ok", "output": {"json": {"ok": True}}, "digest": "extract"}
    if task.get("acceptance") == "pass":
        return {"ok": True, "status": "direct_ok", "output": {"done": True}, "digest": "ok"}
    # Default bounded success for accept fixtures
    return {
        "ok": True,
        "status": "direct_ok",
        "output": {"goal": goal[:200], "mode": "direct_model"},
        "digest": "direct",
    }


def _run_plan_review(task: dict[str, Any], journal: Journal, turn: int) -> dict[str, Any]:
    """Extra planning + review for ambiguous / high-impact / escalated work."""
    journal.add_hypothesis("Task needs an explicit plan and review before mutation.")
    plan = {
        "steps": [
            "clarify_conflicts_or_impact",
            "targeted_analysis",
            "minimal_change",
            "verify",
        ],
        "goal": str(task.get("goal") or "")[:300],
    }
    journal.decide("plan", "authored concise plan (not CoT transcript)", "plan_review")
    review = {
        "approved": not bool(task.get("block_review")),
        "notes": "Review based on observable constraints, not confidence scores.",
    }
    journal.decide(
        "review",
        "approved" if review["approved"] else "blocked",
        "plan_review",
    )
    if not review["approved"]:
        return {
            "ok": False,
            "status": "review_blocked",
            "error": "review_not_approved",
            "plan": plan,
            "digest": "blocked",
        }
    if task.get("unresolved_deps"):
        return {
            "ok": False,
            "status": "unresolved_dependencies",
            "error": "missing_deps",
            "deps": list(task["unresolved_deps"]),
            "plan": plan,
            "digest": "deps:" + ",".join(task["unresolved_deps"]),
        }
    if task.get("no_progress_loop"):
        # Same failure each turn — controller detects no-progress
        return {
            "ok": False,
            "status": "stuck",
            "error": "same_blocker",
            "digest": "stuck_same",
            "plan": plan,
        }
    # Targeted analysis artifact
    analysis = {
        "impact": task.get("impact") or "high",
        "signals": task.get("signals") or [],
        "conflicts": task.get("conflicting_requirements") or [],
    }
    journal.note(
        EvidenceItem(
            kind="observation",
            detail=f"targeted_analysis:{json.dumps(analysis)[:200]}",
            turn=turn,
            observable=True,
        )
    )
    if task.get("acceptance") == "fail_until_analysis":
        # Pass after plan/review path produces analysis
        return {
            "ok": True,
            "status": "plan_review_ok",
            "output": {"plan": plan, "analysis": analysis},
            "digest": "analyzed",
        }
    return {
        "ok": True,
        "status": "plan_review_ok",
        "output": {"plan": plan, "analysis": analysis, "reviewed": True},
        "digest": "plan_ok",
    }


def _accept_ok(task: dict[str, Any], result: dict[str, Any]) -> bool:
    if task.get("acceptance") == "fail_until_analysis":
        return bool(result.get("ok") and (result.get("output") or {}).get("analysis"))
    if task.get("acceptance") == "pass":
        return bool(result.get("ok"))
    if task.get("deterministic_op") or task.get("kind") in {
        "echo",
        "list-tree",
        "workspace-checksum",
        "checksum",
    }:
        return bool(result.get("ok"))
    return bool(result.get("ok")) and result.get("status") not in {
        "stuck",
        "review_blocked",
        "unresolved_dependencies",
        "model_step_failed",
    }


def run_controller(
    task: dict[str, Any],
    *,
    budgets: Budgets | None = None,
    no_progress_threshold: int = 3,
) -> ControllerResult:
    budgets = budgets or Budgets()
    journal = Journal()
    started = time.perf_counter()
    classification = classify_mode(task)
    mode: Mode = mode_name(classification)
    journal.decide("initial_mode", classification["reason"], mode)

    ceremony: list[str] = []
    turns = 0
    tokens = 0
    tools = 0
    progress_hist: list[str] = []
    last_result: dict[str, Any] = {}
    stop: str = "accepted"
    checkpoint: dict[str, Any] | None = None

    # Capacity / information gates
    if task.get("unavailable_capacity"):
        stop = "unavailable_capacity"
        journal.note(
            EvidenceItem(
                kind="observation",
                detail="capacity_unavailable",
                turn=0,
                observable=True,
            )
        )
        return ControllerResult(
            ok=False,
            mode_final=mode,
            stop_reason=stop,  # type: ignore[arg-type]
            turns_used=0,
            tokens_used=0,
            tool_calls_used=0,
            elapsed_ms=0,
            ceremony=[],
            journal=journal.to_dict(),
            checkpoint=_checkpoint_dict(task, journal, mode, stop, last_result, budgets),
            output={"stopped": stop},
            budgets=budgets.to_dict(),
        )
    if task.get("unavailable_information"):
        stop = "unavailable_information"
        path = _write_checkpoint(
            _checkpoint_dict(task, journal, mode, stop, {"need": task.get("unavailable_information")}, budgets)
        )
        return ControllerResult(
            ok=False,
            mode_final=mode,
            stop_reason=stop,  # type: ignore[arg-type]
            turns_used=0,
            tokens_used=0,
            tool_calls_used=0,
            elapsed_ms=0,
            ceremony=[],
            journal=journal.to_dict(),
            checkpoint={"path": str(path), **_checkpoint_dict(task, journal, mode, stop, {}, budgets)},
            output={"stopped": stop, "need": task.get("unavailable_information")},
            budgets=budgets.to_dict(),
        )

    while True:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if turns >= budgets.max_turns:
            stop = "budget_turns"
            break
        if tokens >= budgets.max_tokens:
            stop = "budget_tokens"
            break
        if tools >= budgets.max_tool_calls:
            stop = "budget_tools"
            break
        if elapsed_ms >= budgets.max_elapsed_ms:
            stop = "budget_elapsed"
            break

        turns += 1
        # Token accounting: planning costs more than deterministic
        turn_tokens = {"deterministic_tools": 0, "direct_model": 120, "plan_review": 400}[mode]
        tokens += turn_tokens

        if mode == "deterministic_tools":
            if "deterministic" not in ceremony:
                ceremony.append("deterministic")
            last_result = _run_deterministic(task)
            tools += 1
        elif mode == "direct_model":
            if "direct_execute" not in ceremony:
                ceremony.append("direct_execute")
            last_result = _run_direct_bounded(task, journal, turns)
            tools += 1
        else:
            for step in ("plan", "review", "targeted_analysis"):
                if step not in ceremony:
                    ceremony.append(step)
            last_result = _run_plan_review(task, journal, turns)
            tools += 2  # plan + review count as toolish steps

        sig = progress_signature(last_result, last_result.get("error"))
        progress_hist.append(sig)

        if _accept_ok(task, last_result):
            journal.note(
                EvidenceItem(kind="accept_pass", detail="acceptance checks passed", turn=turns, observable=True)
            )
            stop = "accepted"
            break

        # Observable escalation evidence
        esc = escalate(
            current=mode,
            journal=journal,
            turn=turns,
            verification_failed=last_result.get("status") in {"model_step_failed", "stuck"}
            or (last_result.get("ok") is False and mode != "plan_review"),
            unresolved_dependencies=list(last_result.get("deps") or task.get("unresolved_deps") or []),
            conflicting_requirements=list(task.get("conflicting_requirements") or []),
            invalid_action=last_result.get("error") if "invalid" in str(last_result.get("error") or "") else None,
            model_confidence=task.get("model_confidence"),  # may be present; never sole escalator
        )
        if esc.get("escalate"):
            mode = esc["mode"]  # type: ignore[assignment]

        if should_stop_no_progress(progress_hist, threshold=no_progress_threshold):
            stop = "no_progress"
            break

        # Confidence-alone must not force infinite plan loops
        if task.get("only_low_confidence") and not esc.get("reasons"):
            # Stay on current path; if accept not met and no evidence, stop as unavailable info
            if turns >= 2:
                stop = "unavailable_information"
                journal.note(
                    EvidenceItem(
                        kind="observation",
                        detail="low_confidence_without_observable_evidence_stop",
                        turn=turns,
                        observable=True,
                    )
                )
                break

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    ok = stop == "accepted" and bool(last_result.get("ok"))
    cp = None
    if stop in {"no_progress", "unavailable_information", "unavailable_capacity"} or not ok:
        payload = _checkpoint_dict(task, journal, mode, stop, last_result, budgets)
        path = _write_checkpoint(payload)
        cp = {"path": str(path), **payload}

    return ControllerResult(
        ok=ok,
        mode_final=mode,
        stop_reason=stop,  # type: ignore[arg-type]
        turns_used=turns,
        tokens_used=tokens,
        tool_calls_used=tools,
        elapsed_ms=elapsed_ms,
        ceremony=ceremony,
        journal=journal.to_dict(),
        checkpoint=cp,
        output=last_result,
        budgets=budgets.to_dict(),
    )


def _checkpoint_dict(
    task: dict[str, Any],
    journal: Journal,
    mode: Mode,
    stop: str,
    last_result: dict[str, Any],
    budgets: Budgets,
) -> dict[str, Any]:
    return {
        "at": _utc(),
        "stop_reason": stop,
        "mode": mode,
        "task_goal": str(task.get("goal") or task.get("kind") or "")[:300],
        "last_result": {
            "ok": last_result.get("ok"),
            "status": last_result.get("status"),
            "error": last_result.get("error"),
            "digest": last_result.get("digest"),
        },
        "journal": journal.to_dict(),
        "budgets": budgets.to_dict(),
        "useful": True,
        "note": "Checkpoint for resume — concise evidence retained; no CoT transcript required.",
    }
