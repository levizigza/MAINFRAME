"""Effect receipts — execution vs delivery; compensation only with a real inverse."""

from __future__ import annotations

from typing import Any

# Operations with a true local inverse (not the same as retracting a received message).
COMPENSATABLE: dict[str, dict[str, Any]] = {
    "write_local_draft": {
        "inverse": "delete_local_draft",
        "capability": "local.draft",
        "note": "Deleting a local draft undoes a local write only.",
    },
    "create_local_artifact": {
        "inverse": "delete_local_artifact",
        "capability": "local.artifact",
        "note": "Local artifact removal; does not retract external delivery.",
    },
}

# Distinct capability — must not be treated as the inverse of local draft delete.
NON_INVERSE: dict[str, dict[str, Any]] = {
    "retract_received_message": {
        "capability": "messaging.retract",
        "note": (
            "Retracting an already-received message is a different capability from "
            "deleting a local draft. Compensation must not conflate them."
        ),
        "not_inverse_of": ["write_local_draft", "create_local_artifact", "delete_local_draft"],
    },
}


def compensation_for(operation: str) -> dict[str, Any]:
    if operation in COMPENSATABLE:
        meta = COMPENSATABLE[operation]
        return {
            "supported": True,
            "operation": operation,
            "inverse": meta["inverse"],
            "capability": meta["capability"],
            "note": meta["note"],
        }
    if operation in NON_INVERSE:
        meta = NON_INVERSE[operation]
        return {
            "supported": False,
            "operation": operation,
            "reason": "not_a_local_inverse",
            "capability": meta["capability"],
            "note": meta["note"],
        }
    return {
        "supported": False,
        "operation": operation,
        "reason": "no_declared_inverse",
        "note": "Only operations with a real inverse may be compensated.",
    }


def build_effect_receipt(
    *,
    operation_id: str,
    effect_kind: str,
    execution_status: str,
    delivery_status: str | None = None,
    outcome: str | None = None,
    duplicate_suppressed: bool = False,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Separate execution success from delivery success.

    outcome: succeeded | failed | unknown
    delivery_status: not_requested | delivered | failed | unknown | none
    """
    return {
        "operation_id": operation_id,
        "effect_kind": effect_kind,
        "execution_status": execution_status,
        "delivery_status": delivery_status if delivery_status is not None else "not_requested",
        "outcome": outcome or execution_status,
        "duplicate_suppressed": duplicate_suppressed,
        "side_effect_occurred": execution_status in {"succeeded", "unknown"},
        "detail": detail or {},
        "compensation": compensation_for(effect_kind),
    }
