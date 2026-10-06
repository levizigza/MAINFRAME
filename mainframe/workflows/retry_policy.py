"""Retry policies — transient reads vs reconcile-before-retry writes."""

from __future__ import annotations

from typing import Any

TRANSIENT_READ_ERRORS = frozenset(
    {
        "TimeoutError",
        "ConnectionError",
        "BrokenPipeError",
        "TemporaryFailure",
        "OSError",
    }
)


def classify_step_io(step: dict[str, Any]) -> str:
    """Return 'read' | 'write' | 'external' | 'other'."""
    effects = list(step.get("effects") or [])
    if step.get("mutates") or any("write" in e or "create" in e for e in effects):
        if any("deliver" in e or "external" in e or "send" in e for e in effects):
            return "external"
        return "write"
    if step.get("kind") == "deterministic" and not step.get("mutates"):
        return "read"
    return "other"


def should_retry(
    step: dict[str, Any],
    *,
    attempt: int,
    error_name: str,
    prior_effect: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Retry transient reads safely.
    For writes/external: reconcile uncertain prior effect before retrying.
    """
    max_retries = int((step.get("retries") or {}).get("max") or 0)
    if attempt > max_retries:
        return {"retry": False, "reason": "max_retries_exhausted"}

    io = classify_step_io(step)
    if io == "read":
        transient = error_name in TRANSIENT_READ_ERRORS or error_name.endswith("TimeoutError")
        return {
            "retry": transient,
            "reason": "transient_read" if transient else "non_transient_read",
            "io": io,
        }

    # Write / external: never blind-retry if effect may have occurred
    if prior_effect:
        outcome = prior_effect.get("outcome") or prior_effect.get("execution_status")
        if outcome == "unknown":
            return {
                "retry": False,
                "reason": "reconcile_uncertain_write_before_retry",
                "io": io,
                "requires_reconcile": True,
                "prior_effect": prior_effect,
            }
        if outcome == "succeeded" or prior_effect.get("side_effect_occurred"):
            return {
                "retry": False,
                "reason": "effect_already_applied_skip_duplicate",
                "io": io,
                "duplicate_suppressed": True,
                "prior_effect": prior_effect,
            }
        if outcome == "failed":
            return {"retry": attempt <= max_retries, "reason": "failed_write_may_retry", "io": io}

    # No prior receipt — allow limited retry but flag reconcile on unknown
    return {
        "retry": True,
        "reason": "no_prior_effect_receipt",
        "io": io,
        "caution": "first_attempt_or_clean_failure",
    }


def reconcile_before_retry(prior_effect: dict[str, Any] | None) -> dict[str, Any]:
    if not prior_effect:
        return {"reconciled": True, "action": "none", "safe_to_retry": True}
    outcome = prior_effect.get("outcome") or prior_effect.get("execution_status")
    if outcome == "unknown":
        return {
            "reconciled": False,
            "action": "query_status_api_or_retain_unknown",
            "safe_to_retry": False,
            "report": "outcome_unknown",
            "effect": prior_effect,
        }
    if outcome == "succeeded":
        return {
            "reconciled": True,
            "action": "reuse_effect_receipt",
            "safe_to_retry": False,
            "duplicate_suppressed": True,
            "effect": prior_effect,
        }
    return {"reconciled": True, "action": "retry_allowed", "safe_to_retry": True}
