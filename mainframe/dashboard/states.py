"""Normalize FreeForge task states for the local dashboard."""

from __future__ import annotations

from typing import Any

# User-facing states — not decorative agent activity labels
DASHBOARD_STATES = (
    "proposed",
    "running",
    "verified",
    "blocked",
    "outcome_unknown",
    "cancelled",
)


def normalize_state(raw: str | None, *, cancelled: bool = False, outcome_unknown: bool = False) -> str:
    if cancelled or raw in {"cancelled"}:
        return "cancelled"
    if outcome_unknown or raw in {"outcome_unknown"}:
        return "outcome_unknown"
    s = (raw or "").lower()
    if s in {"proposed", "proposal", "awaiting_apply", "open"}:
        return "proposed"
    if s in {"running", "interrupted", "started", "in_progress", "checkpointed"}:
        return "running"
    if s in {"verified", "succeeded", "completed", "applied", "ok"}:
        return "verified"
    if s in {
        "blocked",
        "blocked_concurrency",
        "failed",
        "apply_failed",
        "proposal_invalid",
        "delivery_failed",
        "held",
        "held_for_decision",
    }:
        return "blocked"
    if s in DASHBOARD_STATES:
        return s
    return "running" if s else "proposed"


def recovery_hint(state: str, *, reason: str | None = None, checks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Plain-language recovery without requiring log reading."""
    reason = reason or ""
    failed_checks = [c for c in (checks or []) if c.get("ok") is False]
    if state == "outcome_unknown":
        return {
            "headline": "External action may have happened — do not retry blindly",
            "steps": [
                "Review the effect receipt and operation ID below.",
                "Reconcile status before any retry (dashboard Stop keeps completed work).",
                "Do not re-send to a new destination to 'fix' a notification failure.",
            ],
            "primary_action": "reconcile",
            "reason": reason,
            "failed_checks": failed_checks,
        }
    if state == "blocked":
        return {
            "headline": "Task is blocked — fix the listed check, then Resume",
            "steps": [
                "Read the failed check and evidence below (not the raw log).",
                "Resolve pending decisions or capability holds if shown.",
                "Press Resume only after the blocker is cleared; Stop cancels new effects.",
            ],
            "primary_action": "resume_after_fix",
            "reason": reason,
            "failed_checks": failed_checks,
        }
    if state == "proposed":
        return {
            "headline": "Proposal awaiting review",
            "steps": ["Inspect reviewable diffs.", "Apply only if checks pass.", "Cancel to discard without side effects."],
            "primary_action": "review",
            "reason": reason,
            "failed_checks": failed_checks,
        }
    if state == "cancelled":
        return {
            "headline": "Cancelled — completed effects remain recorded",
            "steps": ["No new effects will run.", "Prior artifacts and receipts stay available."],
            "primary_action": "none",
            "reason": reason,
            "failed_checks": failed_checks,
        }
    if state == "verified":
        return {
            "headline": "Verified — checks passed",
            "steps": ["Open artifacts if needed.", "No further action required."],
            "primary_action": "none",
            "reason": reason,
            "failed_checks": [],
        }
    return {
        "headline": "Running",
        "steps": ["Wait for completion, or Stop to cancel new effects."],
        "primary_action": "wait_or_stop",
        "reason": reason,
        "failed_checks": failed_checks,
    }
