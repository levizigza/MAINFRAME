"""Free-access exhaustion → pause; never activate billing or paid fallback."""

from __future__ import annotations

import re
from typing import Any

from mainframe.providers.types import ChatResult, Message

_EXHAUST_PATTERNS = (
    re.compile(r"429"),
    re.compile(r"rate[\s_-]?limit", re.I),
    re.compile(r"quota", re.I),
    re.compile(r"resource[\s_-]?exhausted", re.I),
    re.compile(r"insufficient[\s_-]?quota", re.I),
    re.compile(r"free[\s_-]?tier", re.I),
    re.compile(r"usage[\s_-]?limit", re.I),
    re.compile(r"tokens?\s+per\s+(minute|day)", re.I),
)


def looks_like_exhaustion(status: int | None, body: str | None, headers: dict[str, str] | None = None) -> bool:
    if status == 429:
        return True
    text = body or ""
    for pat in _EXHAUST_PATTERNS:
        if pat.search(text):
            return True
    if headers:
        # Remaining tokens/requests at zero is soft signal only with 429 preferred
        rem = headers.get("x-ratelimit-remaining-tokens") or headers.get("x-ratelimit-remaining-requests")
        if rem is not None and str(rem).strip() == "0" and status in {429, 403}:
            return True
    return False


def pause_on_exhaustion(provider_id: str, *, status: int | None, body: str | None) -> ChatResult:
    return ChatResult(
        ok=False,
        provider_id=provider_id,
        message=None,
        paused=True,
        refused=False,
        exhausted_free_access=True,
        billing_activated=False,
        paid_fallback_used=False,
        live_verified=False,
        fixture_only=False,
        detail={
            "http_status": status,
            "body_excerpt": (body or "")[:500],
            "action": "pause_work",
            "billing_activation_attempted": False,
            "paid_endpoint_switched": False,
            "message": (
                "Free access exhausted or rate-limited. "
                "Work paused — no billing activation and no paid endpoint fallback."
            ),
        },
    )


def refuse_disabled(provider_id: str, reason: str) -> ChatResult:
    return ChatResult(
        ok=False,
        provider_id=provider_id,
        paused=True,
        refused=True,
        exhausted_free_access=False,
        billing_activated=False,
        paid_fallback_used=False,
        live_verified=False,
        fixture_only=False,
        detail={"message": reason, "paid_fallback_used": False},
    )


def fixture_result(provider_id: str, message: Message, usage_raw: dict[str, Any] | None = None) -> ChatResult:
    from mainframe.providers.types import UsageReport

    return ChatResult(
        ok=True,
        provider_id=provider_id,
        message=message,
        usage=UsageReport(raw=usage_raw or {"fixture": True}),
        paused=False,
        live_verified=False,
        fixture_only=True,
        billing_activated=False,
        paid_fallback_used=False,
        detail={"label": "unverified_live", "fixture_only": True},
    )
