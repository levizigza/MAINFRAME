"""Uncertainty tags for incomplete dependency observations."""

from __future__ import annotations

from typing import Any, Literal

UncertaintyKind = Literal[
    "dynamic_import",
    "reflection",
    "generated_code",
    "external_service",
    "unresolved_edge",
    "map_incomplete",
]


def uncertainty(
    kind: UncertaintyKind,
    *,
    path: str | None = None,
    detail: str,
    widens_plan: bool = True,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "path": path,
        "detail": detail,
        "widens_plan": widens_plan,
        "resolved": False,
        # Incomplete maps must not imply missing edges do not exist
        "absence_not_proven": True,
    }
