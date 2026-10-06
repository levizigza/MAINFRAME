"""Decide whether a model review call's measured benefit justifies the quota spend."""

from __future__ import annotations

from typing import Any


def review_gate(
    *,
    deterministic: dict[str, Any],
    impact: str = "normal",
    unresolved_high_value: bool = False,
    prior_review_helped: bool | None = None,
    force_skip_model: bool = False,
) -> dict[str, Any]:
    """
    Gate a *second* model call for review.

    Deterministic checks always run first (caller responsibility). This gate only
    answers whether spending quota on a model reviewer is justified.
    """
    if force_skip_model:
        return {
            "invoke_model_review": False,
            "reason": "force_skip_model",
            "quota_justified": False,
        }

    det_ok = bool(deterministic.get("ok"))
    det_findings = list(deterministic.get("findings") or [])
    high = impact in {"high", "critical"} or unresolved_high_value

    # Deterministic failures already give actionable evidence — no extra model call needed
    # unless high-value and we need counterexample framing beyond compile/test.
    if not det_ok and not high:
        return {
            "invoke_model_review": False,
            "reason": "deterministic_findings_sufficient",
            "quota_justified": False,
            "deterministic_ok": False,
            "findings_n": len(det_findings),
        }

    # Measured history says review helped this class
    if prior_review_helped is True and (high or not det_ok):
        return {
            "invoke_model_review": True,
            "reason": "prior_measured_benefit",
            "quota_justified": True,
            "deterministic_ok": det_ok,
        }

    # High-impact / unresolved high-value: justify review even if tests are green
    if high:
        return {
            "invoke_model_review": True,
            "reason": "high_value_or_impact",
            "quota_justified": True,
            "deterministic_ok": det_ok,
        }

    # Green deterministic + normal impact → do not spend quota on review
    if det_ok:
        return {
            "invoke_model_review": False,
            "reason": "no_measured_benefit_for_green_normal",
            "quota_justified": False,
            "deterministic_ok": True,
        }

    return {
        "invoke_model_review": True,
        "reason": "deterministic_failed_needs_counterexamples",
        "quota_justified": True,
        "deterministic_ok": False,
    }
