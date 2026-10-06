"""Where idempotency keys help — and where exactly-once cannot be guaranteed."""

from __future__ import annotations

from typing import Any

# Destinations that accept a client idempotency key for mutating calls.
IDEMPOTENCY_SUPPORT: dict[str, dict[str, Any]] = {
    "local_effect_sink": {
        "supports_idempotency_key": True,
        "exactly_once_guaranteed": False,
        "note": (
            "Local sink dedupes by idempotency key within the durable store window. "
            "Exactly-once across process crash + concurrent writers is not guaranteed."
        ),
    },
    "openclaw_embedded_agent_runtime": {
        "supports_idempotency_key": True,
        "exactly_once_guaranteed": False,
        "note": (
            "Selected engine may accept operation/idempotency IDs on supported status APIs. "
            "MAINFRAME still reconciles via status after gaps; WebSocket streams are not "
            "assumed to replay missed events."
        ),
    },
    "generic_http_no_key": {
        "supports_idempotency_key": False,
        "exactly_once_guaranteed": False,
        "note": "Without destination idempotency, at-least-once retry can duplicate side effects.",
    },
}

# Explicit documentation of non-guarantees (also mirrored in docs/durable/EXACTLY_ONCE.md).
EXACTLY_ONCE_LIMITS = (
    "Exactly-once execution cannot be guaranteed across: "
    "(1) destinations without idempotency keys, "
    "(2) crashes after an external mutation is applied but before a durable receipt is written "
    "when the destination also lacks queryable status, "
    "(3) concurrent lease holders if lease fencing is bypassed, "
    "(4) relying on WebSocket event streams to replay missed events (they are not assumed to)."
)


def destination_policy(destination: str) -> dict[str, Any]:
    meta = IDEMPOTENCY_SUPPORT.get(destination)
    if not meta:
        return {
            "destination": destination,
            "supports_idempotency_key": False,
            "exactly_once_guaranteed": False,
            "note": "Unknown destination — treat as at-least-once; reconcile before retry.",
        }
    return {"destination": destination, **meta}


def use_idempotency_key(destination: str, key: str | None) -> dict[str, Any]:
    pol = destination_policy(destination)
    if not pol["supports_idempotency_key"]:
        return {
            "ok": False,
            "attached": False,
            "policy": pol,
            "reason": "destination_does_not_support_idempotency_key",
        }
    if not key:
        return {
            "ok": False,
            "attached": False,
            "policy": pol,
            "reason": "idempotency_key_required_when_supported",
        }
    return {"ok": True, "attached": True, "idempotency_key": key, "policy": pol}
