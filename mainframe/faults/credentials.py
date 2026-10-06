"""Expired credential and unauthorized-action fault fixtures (local only)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from mainframe.cost_gate import authorize
from mainframe.providers.exhaust import pause_on_exhaustion
from mainframe.quota.identity import refuse_identity_rotation


def check_expired_credential(
    *,
    expires_at: datetime,
    now: datetime | None = None,
    secret_id: str = "fixture_token",
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    expired = now >= expires_at
    return {
        "ok": not expired,  # usable only when not expired
        "expired": expired,
        "secret_id": secret_id,
        "action_allowed": not expired,
        "unauthorized_if_used": expired,
        "recovery": "refuse_use_require_refresh_or_pause" if expired else "usable",
        "paid_fallback_used": False,
        "expires_at": expires_at.isoformat(),
        "observed_at": now.isoformat(),
    }


def check_unauthorized_action(*, tool: str = "remote.destroy", local: bool = False) -> dict[str, Any]:
    gate = authorize("tool", tool, local=local)
    return {
        "ok": gate.allowed is False or local,
        "allowed": gate.allowed,
        "tool": tool,
        "recovery": "deny_no_effect" if not gate.allowed else "allowed_local",
        "paid_fallback_used": False,
        "gate": gate.to_dict() if hasattr(gate, "to_dict") else {"allowed": gate.allowed},
    }


def check_exhausted_quota_no_paid_fallback() -> dict[str, Any]:
    result = pause_on_exhaustion("groq_cloud", status=429, body="free tier quota exhausted")
    rotate = refuse_identity_rotation(
        provider_id="groq_cloud",
        requested_identity="burner-2",
        active_identity="primary",
        purpose="evade quota",
    )
    return {
        "ok": (
            result.paused
            and result.exhausted_free_access
            and result.paid_fallback_used is False
            and result.billing_activated is False
            and rotate.get("refused") is True
            and rotate.get("paid_fallback_used") is False
        ),
        "paused": result.paused,
        "paid_fallback_used": result.paid_fallback_used,
        "billing_activated": result.billing_activated,
        "identity_rotation_refused": rotate.get("refused"),
        "recovery": "pause_no_paid_fallback",
        "detail": {"exhaust": result.to_dict(), "rotate": rotate},
    }


def expired_fixture_pair() -> tuple[datetime, datetime]:
    now = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)
    return now - timedelta(hours=1), now
