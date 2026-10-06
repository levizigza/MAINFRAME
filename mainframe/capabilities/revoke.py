"""Revocation and emergency stop — cancel queued work."""

from __future__ import annotations

from typing import Any

from mainframe.capabilities.store import CapabilityStore


def revoke_grant(store: CapabilityStore, grant_id: str) -> dict[str, Any]:
    return store.revoke(grant_id)


def emergency_stop(
    store: CapabilityStore,
    *,
    reason: str = "user_emergency_stop",
    project_id: str | None = None,
) -> dict[str, Any]:
    store.set_emergency_stop(active=True, reason=reason)
    n = store.cancel_all_queue(project_id)
    return {
        "stopped": True,
        "reason": reason,
        "cancelled_n": n,
        "emergency_stop": True,
    }
