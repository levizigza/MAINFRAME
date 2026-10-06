"""Schedules trigger work only — they do not grant new permissions."""

from __future__ import annotations

from typing import Any

from mainframe.capabilities.store import CapabilityStore


def schedule_trigger(
    store: CapabilityStore,
    *,
    project_id: str,
    schedule_id: str,
    requested_capability: str,
) -> dict[str, Any]:
    """
    A schedule alone grants no new permissions.

    Existing grants must already cover the capability when the job runs.
    """
    before = {g["grant_id"]: list(g.get("capabilities") or []) for g in store.active_grants(project_id)}
    return {
        "ok": True,
        "schedule_id": schedule_id,
        "project_id": project_id,
        "requested_capability": requested_capability,
        "schedule_grants_permissions": False,
        "permissions_added": [],
        "grants_before": before,
        "grants_after": before,
        "note": "Schedule may enqueue work; it does not expand capability grants.",
    }
