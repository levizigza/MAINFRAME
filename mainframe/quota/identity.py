"""Refuse account/identity rotation used to evade quota."""

from __future__ import annotations

from typing import Any


def refuse_identity_rotation(
    *,
    provider_id: str,
    requested_identity: str | None,
    active_identity: str | None,
    purpose: str | None = None,
) -> dict[str, Any]:
    """
    More credentials / accounts must never be used to multiply capacity.
    Separate legitimate entitlements are allowed only when explicitly distinct
    and terms-permitted — never as a rotation pair for the same logical seat.
    """
    purpose_l = (purpose or "").lower()
    evade = any(
        k in purpose_l
        for k in ("evade", "bypass", "rotate", "burner", "farm", "circumvent", "unlimited")
    )
    rotating = (
        requested_identity
        and active_identity
        and requested_identity != active_identity
        and (evade or purpose_l in {"", "quota", "rate_limit", "continue"})
    )
    if evade or rotating:
        return {
            "ok": False,
            "refused": True,
            "denied_code": "identity_rotation_refused",
            "provider_id": provider_id,
            "reason": (
                "Refusing account/identity rotation to evade provider restrictions. "
                "More providers or keys do not mean unlimited capacity."
            ),
            "paid_fallback_used": False,
            "billing_activated": False,
        }
    return {
        "ok": True,
        "refused": False,
        "provider_id": provider_id,
        "identity": requested_identity or active_identity,
        "note": "Single identity per logical entitlement; no rotation.",
    }


def capacity_not_multiplied(provider_count: int, global_token_cap: int, per_provider_caps: list[int]) -> dict[str, Any]:
    """Enforce that summing provider caps cannot exceed an explicit global ceiling."""
    naive_sum = sum(per_provider_caps)
    effective = min(naive_sum, global_token_cap)
    return {
        "provider_count": provider_count,
        "naive_sum_caps": naive_sum,
        "global_token_cap": global_token_cap,
        "effective_cap": effective,
        "unlimited": False,
        "note": "More providers do not mean unlimited capacity.",
    }
