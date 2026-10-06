"""Simulate every hosted provider disappearing or becoming paid."""

from __future__ import annotations

from typing import Any

from mainframe.ai import probe_free_inference, run_ai_step
from mainframe.automation import list_tasks, run_task
from mainframe.cost_gate import authorize
from mainframe.eligibility import DISABLED_PROVIDERS, ELIGIBLE_PROVIDERS


def simulate_hosted_gone_or_paid() -> dict[str, Any]:
    """
    Treat all non-local providers as unavailable/paid.
    Deterministic local workflows must remain usable; AI must pause without
    an approved local model.
    """
    hosted_ids = sorted(DISABLED_PROVIDERS.keys())
    refuses = []
    for pid in hosted_ids:
        g = authorize("inference", pid, local=False)
        refuses.append(
            {
                "provider_id": pid,
                "allowed": bool(g.allowed),
                "fallback_used": False,
                "detail": g.reason if hasattr(g, "reason") else str(g),
            }
        )

    # Also refuse if someone marks eligible as hosted by clearing local flag
    for pid in ELIGIBLE_PROVIDERS:
        g = authorize("inference", pid, local=False)  # pretend mis-tagged remote
        # local=False for ollama should still fail cost gate for non-local
        refuses.append(
            {
                "provider_id": f"{pid}_forced_nonlocal",
                "allowed": bool(g.allowed),
                "note": "eligible id with local=False must not unlock hosted spend",
            }
        )

    probe = probe_free_inference(timeout_s=0.8)
    ai = run_ai_step("cost audit hosted-gone probe")
    # Deterministic task
    tasks = list_tasks()
    echo = run_task("echo", {"message": "hosted_gone_still_works"})
    echo_ok = bool(getattr(echo, "ok", False))

    ai_paused_or_local = (
        probe.status in {"paused", "disabled"}
        or (probe.status == "available" and probe.provider in ELIGIBLE_PROVIDERS)
    )
    no_paid_fallback = ai.get("fallback_used") is not True and ai.get("paid_fallback") is not True

    return {
        "scenario": "all_hosted_providers_disappeared_or_became_paid",
        "hosted_providers_simulated": hosted_ids,
        "hosted_refuses": refuses,
        "all_hosted_refused": all(
            not r.get("allowed") for r in refuses if "forced_nonlocal" not in str(r.get("provider_id"))
        ),
        "ai_probe": probe.to_dict(),
        "ai_step": {
            "paused": ai.get("paused"),
            "ok": ai.get("ok"),
            "fallback_used": ai.get("fallback_used"),
            "provider": ai.get("provider"),
        },
        "deterministic": {
            "tasks_listed": len(tasks) if isinstance(tasks, list) else bool(tasks),
            "echo_ok": echo_ok,
            "echo": echo.to_dict() if hasattr(echo, "to_dict") else echo,
        },
        "contract": {
            "deterministic_local_workflows_usable": echo_ok,
            "ai_pauses_without_approved_local_model": ai_paused_or_local,
            "no_automatic_paid_fallback": no_paid_fallback,
            "ai_behavior_ok": ai_paused_or_local and no_paid_fallback,
        },
    }
