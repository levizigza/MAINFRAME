"""Connector / workflow changes must not silently expand authority."""

from __future__ import annotations

from typing import Any

from mainframe.capabilities.store import CapabilityStore


def apply_connector_or_workflow_change(
    store: CapabilityStore,
    *,
    project_id: str,
    change_kind: str,
    previous_authority: dict[str, Any],
    proposed_authority: dict[str, Any],
) -> dict[str, Any]:
    """
    Changing an API connector or workflow must not silently expand its authority.

    New capabilities/destinations/operations require an explicit new grant — they are not
    inherited from the edit alone.
    """
    prev_caps = set(previous_authority.get("capabilities") or [])
    prop_caps = set(proposed_authority.get("capabilities") or [])
    prev_dest = set(previous_authority.get("destinations") or [])
    prop_dest = set(proposed_authority.get("destinations") or [])
    prev_ops = set(previous_authority.get("operations") or [])
    prop_ops = set(proposed_authority.get("operations") or [])

    expanded_caps = sorted(prop_caps - prev_caps)
    expanded_dest = sorted(prop_dest - prev_dest)
    expanded_ops = sorted(prop_ops - prev_ops)
    expands = bool(expanded_caps or expanded_dest or expanded_ops)

    # Freeze to previous authority for runtime
    frozen = {
        "capabilities": sorted(prev_caps),
        "destinations": sorted(prev_dest),
        "operations": sorted(prev_ops),
    }
    return {
        "ok": True,
        "change_kind": change_kind,
        "project_id": project_id,
        "silently_expanded": False,
        "expansion_detected": expands,
        "expanded_capabilities": expanded_caps,
        "expanded_destinations": expanded_dest,
        "expanded_operations": expanded_ops,
        "authority_applied": frozen,
        "proposed_held_for_explicit_grant": proposed_authority if expands else None,
        "note": (
            "Connector/workflow change applied without expanding authority. "
            "New scopes require an explicit user grant."
            if expands
            else "No authority expansion in proposed change."
        ),
        "active_grants_unchanged": [g["grant_id"] for g in store.active_grants(project_id)],
    }
