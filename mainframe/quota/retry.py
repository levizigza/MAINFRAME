"""Parse Retry-After / 429 / timeout into defensible retry estimates."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any


def parse_retry_after(value: str | None, *, now: datetime | None = None) -> dict[str, Any]:
    """
    Return retry_after_s and/or reset_unknown.

    Supports delta-seconds and HTTP-date. Empty/unparseable → reset_unknown.
    """
    now = now or datetime.now(timezone.utc)
    if value is None or str(value).strip() == "":
        return {
            "retry_after_s": None,
            "reset_unknown": True,
            "reason": "No Retry-After header; reset time is unknown.",
            "source": None,
        }
    raw = str(value).strip()
    # Delta seconds
    if re.fullmatch(r"\d+(\.\d+)?", raw):
        secs = float(raw)
        return {
            "retry_after_s": secs,
            "reset_unknown": False,
            "reason": f"Retry-After delta-seconds={secs}",
            "source": "retry-after-delta",
            "cooldown_until": (now + timedelta(seconds=secs)).isoformat(),
        }
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        secs = max(0.0, (dt - now).total_seconds())
        return {
            "retry_after_s": secs,
            "reset_unknown": False,
            "reason": f"Retry-After HTTP-date={dt.isoformat()}",
            "source": "retry-after-http-date",
            "cooldown_until": dt.isoformat(),
        }
    except (TypeError, ValueError, IndexError):
        return {
            "retry_after_s": None,
            "reset_unknown": True,
            "reason": f"Retry-After unparseable ({raw!r}); reset time is unknown.",
            "source": "unparseable",
        }


def from_provider_headers(
    status: int | None,
    headers: dict[str, str] | None,
    *,
    timeout: bool = False,
    cancelled: bool = False,
) -> dict[str, Any]:
    headers = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    if cancelled:
        return {
            "kind": "cancelled",
            "retry_after_s": 0.0,
            "reset_unknown": False,
            "reason": "Request cancelled; reservation should be released.",
            "apply_cooldown": False,
        }
    if timeout:
        return {
            "kind": "timeout",
            "retry_after_s": None,
            "reset_unknown": True,
            "reason": "Timeout with unknown remaining quota impact; treat conservatively.",
            "apply_cooldown": False,
            "conservative_unknown_usage": True,
        }
    if status == 429 or "retry-after" in headers:
        parsed = parse_retry_after(headers.get("retry-after"))
        return {
            "kind": "rate_limited",
            "retry_after_s": parsed["retry_after_s"],
            "reset_unknown": parsed["reset_unknown"],
            "reason": parsed["reason"],
            "cooldown_until": parsed.get("cooldown_until"),
            "apply_cooldown": True,
            "source": parsed.get("source"),
        }
    # Rate-limit reset headers (Groq-style) when present
    reset = headers.get("x-ratelimit-reset-tokens") or headers.get("x-ratelimit-reset-requests")
    if reset:
        # e.g. "7.66s" or "2m59.56s"
        m = re.fullmatch(r"(?:(\d+)m)?(\d+(?:\.\d+)?)s", reset.strip())
        if m:
            mins = int(m.group(1) or 0)
            secs = float(m.group(2))
            total = mins * 60 + secs
            now = datetime.now(timezone.utc)
            return {
                "kind": "rate_limit_reset_header",
                "retry_after_s": total,
                "reset_unknown": False,
                "reason": f"Parsed provider reset header {reset!r} → {total}s",
                "cooldown_until": (now + timedelta(seconds=total)).isoformat(),
                "apply_cooldown": True,
                "source": "x-ratelimit-reset",
            }
        return {
            "kind": "rate_limit_reset_header",
            "retry_after_s": None,
            "reset_unknown": True,
            "reason": f"Reset header present but unparseable ({reset!r}); reset time is unknown.",
            "apply_cooldown": True,
            "source": "x-ratelimit-reset-unparseable",
        }
    return {
        "kind": "ok",
        "retry_after_s": None,
        "reset_unknown": False,
        "reason": "No rate-limit signal",
        "apply_cooldown": False,
    }
