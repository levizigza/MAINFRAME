"""Durable task states and legal transitions."""

from __future__ import annotations

from typing import Any, Literal

TaskState = Literal[
    "planned",
    "started",
    "succeeded",
    "failed",
    "cancelled",
    "outcome_unknown",
]

ALL_STATES: tuple[str, ...] = (
    "planned",
    "started",
    "succeeded",
    "failed",
    "cancelled",
    "outcome_unknown",
)

# Explicit terminal vs non-terminal
TERMINAL: frozenset[str] = frozenset({"succeeded", "failed", "cancelled"})

# Legal transitions (from → allowed next)
TRANSITIONS: dict[str, frozenset[str]] = {
    "planned": frozenset({"started", "cancelled"}),
    "started": frozenset({"succeeded", "failed", "cancelled", "outcome_unknown"}),
    "outcome_unknown": frozenset({"succeeded", "failed", "cancelled", "outcome_unknown"}),
    "succeeded": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}


def can_transition(current: str, nxt: str) -> bool:
    return nxt in TRANSITIONS.get(current, frozenset())


def transition(current: str, nxt: str) -> dict[str, Any]:
    if current not in ALL_STATES or nxt not in ALL_STATES:
        return {"ok": False, "error": "unknown_state", "from": current, "to": nxt}
    if not can_transition(current, nxt):
        return {
            "ok": False,
            "error": "illegal_transition",
            "from": current,
            "to": nxt,
            "allowed": sorted(TRANSITIONS.get(current, frozenset())),
        }
    return {"ok": True, "from": current, "to": nxt, "terminal": nxt in TERMINAL}
