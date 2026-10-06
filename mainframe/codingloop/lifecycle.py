"""Selected coding-engine lifecycle — not a nested second supervisor."""

from __future__ import annotations

from typing import Any

from mainframe.freeforge import REJECTED_ENGINE, SELECTED_ENGINE

# Phases supported by the selected embedded engine lifecycle (MAINFRAME adapter).
# Retries advance this same lifecycle; we do not spawn an independent meta-supervisor
# that re-runs the same work under a different controller.
LIFECYCLE_PHASES: tuple[str, ...] = (
    "reproduce",
    "investigate",
    "propose",
    "apply",
    "check",
    "report",
)


def engine_binding() -> dict[str, Any]:
    return {
        "selected_engine": SELECTED_ENGINE,
        "rejected_engine": REJECTED_ENGINE,
        "nested_independent_supervisor": False,
        "lifecycle_phases": list(LIFECYCLE_PHASES),
        "note": (
            "Coding loop reuses openclaw_embedded_agent_runtime-supported phases. "
            "It does not create a second supervisor that independently retries the same work."
        ),
    }


def next_phase(current: str | None) -> str | None:
    if current is None:
        return LIFECYCLE_PHASES[0]
    try:
        i = LIFECYCLE_PHASES.index(current)
    except ValueError:
        return LIFECYCLE_PHASES[0]
    if i + 1 >= len(LIFECYCLE_PHASES):
        return None
    return LIFECYCLE_PHASES[i + 1]
