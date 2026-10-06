"""Review routes — disable quota-burning paths with no measured improvement."""

from __future__ import annotations

from typing import Any

# Routes measured against seeded fixtures. Disabled routes stay refused in code
# (not merely hidden) when extra quota produced no acceptance improvement.
REVIEW_ROUTES: dict[str, dict[str, Any]] = {
    "deterministic_first_gated": {
        "status": "eligible",
        "model_call": "gated",
        "swarm": False,
        "majority_vote": False,
        "measured_improvement": True,
        "note": "Deterministic checks first; model review only when gate says benefit justifies it.",
    },
    "always_model_review": {
        "status": "disabled",
        "model_call": "always",
        "swarm": False,
        "majority_vote": False,
        "measured_improvement": False,
        "disable_reason": (
            "Always spending an extra model call on every patch produced no measurable "
            "improvement on seeded fixtures vs deterministic-first gating; quota waste."
        ),
    },
    "swarm_review": {
        "status": "disabled",
        "model_call": "always",
        "swarm": True,
        "majority_vote": True,
        "measured_improvement": False,
        "disable_reason": (
            "Spawning a reviewer swarm for every task adds quota with no measured gain; "
            "majority vote is not an evaluator-owned ranking."
        ),
    },
    "majority_vote_rank": {
        "status": "disabled",
        "model_call": "gated",
        "swarm": False,
        "majority_vote": True,
        "measured_improvement": False,
        "disable_reason": (
            "Ranking by majority vote ignores evaluator-owned acceptance checks and "
            "human requirements."
        ),
    },
}

DEFAULT_ROUTE = "deterministic_first_gated"


def route_status(route_id: str) -> dict[str, Any]:
    meta = REVIEW_ROUTES.get(route_id)
    if not meta:
        return {
            "route_id": route_id,
            "status": "disabled",
            "allowed": False,
            "reason": "unknown_review_route",
        }
    allowed = meta["status"] == "eligible"
    return {
        "route_id": route_id,
        "status": meta["status"],
        "allowed": allowed,
        "reason": meta.get("disable_reason") if not allowed else "eligible",
        **{k: v for k, v in meta.items() if k != "disable_reason"},
    }


def select_route(requested: str | None = None) -> dict[str, Any]:
    rid = requested or DEFAULT_ROUTE
    st = route_status(rid)
    if not st["allowed"]:
        # Fail closed to eligible default — never fall through to a disabled swarm/always route.
        fallback = route_status(DEFAULT_ROUTE)
        return {
            "requested": rid,
            "selected": DEFAULT_ROUTE if fallback["allowed"] else None,
            "refused": rid,
            "refusal": st,
            "selected_meta": fallback,
        }
    return {
        "requested": rid,
        "selected": rid,
        "refused": None,
        "refusal": None,
        "selected_meta": st,
    }


def disabled_no_gain_routes() -> list[dict[str, Any]]:
    return [
        {"route_id": rid, **meta}
        for rid, meta in REVIEW_ROUTES.items()
        if meta["status"] == "disabled" and meta.get("measured_improvement") is False
    ]
