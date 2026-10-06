"""Interactive ahead of background; prevent background starvation."""

from __future__ import annotations

import threading
from typing import Any

from mainframe.quota.types import Priority

_LOCK = threading.Lock()
# Global fairness counters (process-local; ledger still enforces capacity).
_STATE = {
    "interactive_admitted": 0,
    "background_admitted": 0,
    "background_deferred": 0,
    "last_admitted": None,
}

# After this many consecutive interactive admits while background waited, prefer background.
STARVATION_INTERACTIVE_STREAK = 3


def record_admit(priority: Priority) -> None:
    with _LOCK:
        _STATE["last_admitted"] = priority
        if priority == "interactive":
            _STATE["interactive_admitted"] += 1
        else:
            _STATE["background_admitted"] += 1
            _STATE["background_ deferred"] = 0


def record_background_deferred() -> None:
    with _LOCK:
        _STATE["background_deferred"] += 1


def should_prefer_background(waiting_background: bool) -> bool:
    """True when interactive streak would starve background work."""
    with _LOCK:
        if not waiting_background:
            return False
        deferred = int(_STATE["background_deferred"])
        return deferred >= STARVATION_INTERACTIVE_STREAK


def rank_key(priority: Priority, *, waiting_background: bool = False) -> tuple[int, int]:
    """
    Lower sorts first.
    Interactive normally wins (0); when anti-starvation trips, background gets 0.
    """
    if priority == "background" and should_prefer_background(waiting_background):
        return (0, 0)  # boost
    if priority == "interactive":
        return (0, 1)
    return (1, 0)


def schedule_order(
    items: list[dict[str, Any]],
    *,
    waiting_background: bool | None = None,
) -> list[dict[str, Any]]:
    """Sort admit candidates: interactive first, unless background is starving."""
    bg_waiting = waiting_background
    if bg_waiting is None:
        bg_waiting = any(i.get("priority") == "background" for i in items) and any(
            i.get("priority") == "interactive" for i in items
        )
    # When background has been deferred enough, boost it for this batch.
    prefer_bg = should_prefer_background(True) if bg_waiting else False
    return sorted(
        items,
        key=lambda i: (
            # When background is starving, it sorts before interactive.
            (0 if i.get("priority") == "background" else 1)
            if prefer_bg
            else (0 if i.get("priority") == "interactive" else 1),
            str(i.get("id") or ""),
        ),
    )


def fairness_snapshot() -> dict[str, Any]:
    with _LOCK:
        return dict(_STATE)


def reset_fairness_for_tests() -> None:
    with _LOCK:
        _STATE["interactive_admitted"] = 0
        _STATE["background_admitted"] = 0
        _STATE["background_deferred"] = 0
        _STATE["last_admitted"] = None
