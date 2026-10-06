"""Escalate only on observable evidence — never confidence alone."""

from __future__ import annotations

from typing import Any

from mainframe.controller.types import EvidenceItem, Journal, Mode


def escalate(
    *,
    current: Mode,
    journal: Journal,
    turn: int,
    verification_failed: bool = False,
    unresolved_dependencies: list[str] | None = None,
    conflicting_requirements: list[str] | None = None,
    invalid_action: str | None = None,
    model_confidence: float | None = None,
) -> dict[str, Any]:
    """
    Decide whether to escalate mode. ``model_confidence`` may be recorded but
    cannot be the sole reason to escalate.
    """
    reasons: list[str] = []
    if verification_failed:
        journal.note(
            EvidenceItem(
                kind="verification_failure",
                detail="Acceptance/verification check failed",
                turn=turn,
                observable=True,
            )
        )
        reasons.append("failed_verification")
    for dep in unresolved_dependencies or []:
        journal.note(
            EvidenceItem(kind="unresolved_dependency", detail=dep, turn=turn, observable=True)
        )
        reasons.append(f"unresolved_dependency:{dep}")
    for c in conflicting_requirements or []:
        journal.note(
            EvidenceItem(kind="conflicting_requirement", detail=c, turn=turn, observable=True)
        )
        reasons.append(f"conflicting_requirement:{c}")
    if invalid_action:
        journal.note(
            EvidenceItem(kind="invalid_action", detail=invalid_action, turn=turn, observable=True)
        )
        reasons.append(f"invalid_action:{invalid_action}")

    confidence_only = bool(model_confidence is not None and model_confidence < 0.5 and not reasons)
    if confidence_only:
        return {
            "escalate": False,
            "mode": current,
            "reasons": [],
            "rejected_reason": "model_confidence_alone_insufficient",
            "model_confidence_seen": model_confidence,
        }

    if not reasons:
        return {"escalate": False, "mode": current, "reasons": [], "model_confidence_seen": model_confidence}

    # Escalation ladder
    nxt: Mode = current
    if current == "deterministic_tools":
        nxt = "direct_model"
    elif current == "direct_model":
        nxt = "plan_review"
    else:
        nxt = "plan_review"

    journal.decide(
        "escalate",
        "; ".join(reasons),
        nxt,
    )
    return {
        "escalate": nxt != current or current == "plan_review",
        "mode": nxt,
        "reasons": reasons,
        "model_confidence_seen": model_confidence,
        "confidence_alone": False,
    }


def progress_signature(output: dict[str, Any] | None, error: str | None) -> str:
    """Stable signature for no-progress detection."""
    parts = [
        str((output or {}).get("status") or ""),
        str((output or {}).get("error") or error or ""),
        str((output or {}).get("digest") or (output or {}).get("sha256") or ""),
    ]
    return "|".join(parts)


def should_stop_no_progress(history: list[str], *, threshold: int = 3) -> bool:
    if len(history) < threshold:
        return False
    last = history[-threshold:]
    return len(set(last)) == 1 and last[0] != ""
