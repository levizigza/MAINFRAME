"""Nonqualifying provider adapters — present and refuse (not merely hidden)."""

from __future__ import annotations

from typing import Any

from mainframe.eligibility import DISABLED_PROVIDERS, refuse_disabled


def invoke_disabled(provider_id: str, **_: Any) -> dict[str, Any]:
    if provider_id not in DISABLED_PROVIDERS:
        return refuse_disabled(provider_id)
    return refuse_disabled(provider_id)


def list_disabled_routes() -> list[dict[str, str]]:
    return [
        {
            "provider_id": pid,
            "route_status": "disabled",
            "auto_fallback": "none",
            **meta,
        }
        for pid, meta in DISABLED_PROVIDERS.items()
    ]
