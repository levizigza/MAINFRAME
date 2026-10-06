"""Acceptance: simple = no ceremony; difficult = analysis; no-progress = checkpoint."""

from __future__ import annotations

from typing import Any

from mainframe.controller.classify import classify_mode
from mainframe.controller.escalate import escalate
from mainframe.controller.loop import run_controller
from mainframe.controller.types import Budgets, Journal


def run_controller_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    # --- Simple deterministic: no plan/review ceremony ---
    simple = run_controller(
        {
            "kind": "echo",
            "deterministic_op": "echo",
            "params": {"message": "simple"},
            "acceptance": "pass",
        },
        budgets=Budgets(max_turns=3, max_tokens=500, max_tool_calls=3, max_elapsed_ms=10_000),
    )
    checks.append(
        {
            "id": "simple_avoids_agent_ceremony",
            "ok": (
                simple.ok
                and simple.mode_final == "deterministic_tools"
                and simple.ceremony == ["deterministic"]
                and "plan" not in simple.ceremony
                and "review" not in simple.ceremony
                and simple.stop_reason == "accepted"
            ),
            "detail": {
                "mode": simple.mode_final,
                "ceremony": simple.ceremony,
                "turns": simple.turns_used,
            },
        }
    )

    # --- Bounded direct: no full plan/review ---
    bounded = run_controller(
        {
            "goal": "extract json from one line (bounded)",
            "bounded": True,
            "acceptance": "pass",
        },
        budgets=Budgets(max_turns=3, max_tokens=2000, max_tool_calls=4, max_elapsed_ms=10_000),
    )
    checks.append(
        {
            "id": "bounded_direct_no_full_ceremony",
            "ok": (
                bounded.ok
                and bounded.mode_final == "direct_model"
                and bounded.ceremony == ["direct_execute"]
                and "plan" not in bounded.ceremony
            ),
            "detail": {"mode": bounded.mode_final, "ceremony": bounded.ceremony},
        }
    )

    # --- Difficult / high-impact: targeted plan+review+analysis ---
    difficult = run_controller(
        {
            "goal": "migrate auth schema — breaking change",
            "impact": "high",
            "difficult": True,
            "acceptance": "fail_until_analysis",
        },
        budgets=Budgets(max_turns=5, max_tokens=5000, max_tool_calls=10, max_elapsed_ms=15_000),
    )
    checks.append(
        {
            "id": "difficult_gets_targeted_analysis",
            "ok": (
                difficult.ok
                and difficult.mode_final == "plan_review"
                and "plan" in difficult.ceremony
                and "review" in difficult.ceremony
                and "targeted_analysis" in difficult.ceremony
                and (difficult.output.get("output") or {}).get("analysis") is not None
            ),
            "detail": {
                "ceremony": difficult.ceremony,
                "analysis": (difficult.output.get("output") or {}).get("analysis"),
            },
        }
    )

    # --- Confidence alone does not escalate ---
    journal = Journal()
    esc = escalate(
        current="direct_model",
        journal=journal,
        turn=1,
        model_confidence=0.1,
    )
    checks.append(
        {
            "id": "confidence_alone_does_not_escalate",
            "ok": esc.get("escalate") is False and esc.get("rejected_reason") == "model_confidence_alone_insufficient",
            "detail": esc,
        }
    )

    # --- Observable verification failure does escalate ---
    esc2 = escalate(
        current="direct_model",
        journal=Journal(),
        turn=1,
        verification_failed=True,
        model_confidence=0.99,
    )
    checks.append(
        {
            "id": "verification_failure_escalates",
            "ok": esc2.get("escalate") is True and esc2["mode"] == "plan_review" and "failed_verification" in esc2["reasons"],
            "detail": esc2,
        }
    )

    # --- No-progress terminates with useful checkpoint ---
    stuck = run_controller(
        {
            "goal": "ambiguous cleanup somehow",
            "ambiguous": True,
            "no_progress_loop": True,
            "acceptance": "never",
        },
        budgets=Budgets(max_turns=10, max_tokens=8000, max_tool_calls=20, max_elapsed_ms=20_000),
        no_progress_threshold=3,
    )
    checks.append(
        {
            "id": "no_progress_stops_with_checkpoint",
            "ok": (
                stuck.ok is False
                and stuck.stop_reason == "no_progress"
                and stuck.checkpoint is not None
                and stuck.checkpoint.get("useful") is True
                and stuck.checkpoint.get("path")
                and stuck.journal.get("chain_of_thought_required") is False
            ),
            "detail": {
                "stop": stuck.stop_reason,
                "turns": stuck.turns_used,
                "checkpoint_keys": list((stuck.checkpoint or {}).keys()),
            },
        }
    )

    # --- Explicit budgets present ---
    checks.append(
        {
            "id": "explicit_budgets_enforced_fields",
            "ok": all(
                k in simple.budgets
                for k in ("max_turns", "max_tokens", "max_tool_calls", "max_elapsed_ms")
            ),
            "detail": simple.budgets,
        }
    )

    # --- Classify signals documented ---
    high = classify_mode({"goal": "drop table users in prod", "impact": "high"})
    checks.append(
        {
            "id": "high_impact_classifies_plan_review",
            "ok": high["mode"] == "plan_review" and "high_impact" in high["signals"],
            "detail": high,
        }
    )

    # --- Unavailable information stops cleanly ---
    missing = run_controller(
        {
            "goal": "fix bug",
            "unavailable_information": "repro_steps",
        },
        budgets=Budgets(max_turns=2, max_tokens=100, max_tool_calls=2, max_elapsed_ms=5000),
    )
    checks.append(
        {
            "id": "unavailable_information_stops",
            "ok": missing.stop_reason == "unavailable_information" and missing.checkpoint is not None,
            "detail": {"stop": missing.stop_reason, "need": missing.output.get("need")},
        }
    )

    passed = sum(1 for c in checks if c["ok"])
    failed = len(checks) - passed
    return {
        "ok": failed == 0,
        "passed": passed,
        "failed": failed,
        "checks": checks,
    }
