"""Authorize actions against scoped grants — carry forward user authorization."""

from __future__ import annotations

from typing import Any

from mainframe.capabilities.preview import build_preview
from mainframe.capabilities.store import CapabilityStore
from mainframe.capabilities.types import (
    DESTRUCTIVE_OPS,
    LOCAL_REVERSIBLE_OPS,
)


def _grant_covers(
    grants: list[dict[str, Any]],
    *,
    capability: str,
    operation: str,
    destination: str | None,
) -> dict[str, Any]:
    dest = (destination or "local").strip()
    for g in grants:
        caps = set(g.get("capabilities") or [])
        ops = set(g.get("operations") or [])
        dests = set(g.get("destinations") or [])
        if capability not in caps:
            continue
        if operation not in ops:
            continue
        if dest == "local":
            if "local" not in dests:
                continue
        elif dest not in dests:
            continue
        return {"covered": True, "grant_id": g["grant_id"], "grant": g}
    return {"covered": False}


def authorize_action(
    store: CapabilityStore,
    *,
    project_id: str,
    capability: str,
    operation: str,
    destination: str | None = None,
    payload: dict[str, Any] | None = None,
    prompts_so_far: int = 0,
) -> dict[str, Any]:
    estop = store.emergency_stop_active()
    if estop.get("active"):
        return {
            "allowed": False,
            "prompt": False,
            "status": "emergency_stopped",
            "reason": estop.get("reason") or "emergency_stop",
        }

    grants = store.active_grants(project_id)
    if not grants:
        return {
            "allowed": False,
            "prompt": True,
            "status": "no_active_grant",
            "preview": build_preview(
                hold_reason="no_grant",
                capability=capability,
                operation=operation,
                destination=destination,
                payload=payload,
            ),
        }

    dest = destination or "local"
    cover = _grant_covers(
        grants,
        capability=capability,
        operation=operation,
        destination=dest,
    )

    # Destructive always held unless explicitly in grant AND we still preview for first time
    if operation in DESTRUCTIVE_OPS or capability == "deletion":
        if not cover.get("covered"):
            return _held(
                store,
                project_id=project_id,
                capability=capability,
                operation=operation,
                destination=dest,
                payload=payload,
                hold_reason="destructive_deletion",
            )
        return _held(
            store,
            project_id=project_id,
            capability=capability,
            operation=operation,
            destination=dest,
            payload=payload,
            hold_reason="destructive_deletion",
        )

    # New destination not in any grant
    known_dests: set[str] = set()
    for g in grants:
        known_dests.update(g.get("destinations") or [])
    if dest not in known_dests and dest != "local":
        return _held(
            store,
            project_id=project_id,
            capability=capability,
            operation=operation,
            destination=dest,
            payload=payload,
            hold_reason="new_recipient",
        )

    if not cover.get("covered"):
        return _held(
            store,
            project_id=project_id,
            capability=capability,
            operation=operation,
            destination=dest,
            payload=payload,
            hold_reason="outside_scope",
        )

    # Reversible local in scope — no re-prompt
    if dest == "local" and operation in LOCAL_REVERSIBLE_OPS:
        return {
            "allowed": True,
            "prompt": False,
            "status": "allowed_in_scope",
            "grant_id": cover.get("grant_id"),
            "reversible_local": True,
        }

    # Known external destination in grant — allow without re-prompt (recurring)
    if operation in {"send_report", "send_message"} and dest in known_dests:
        return {
            "allowed": True,
            "prompt": False,
            "status": "allowed_recurring",
            "grant_id": cover.get("grant_id"),
            "prompts": prompts_so_far,
        }

    # Other external / irreversible outside narrow allow — preview first
    if dest != "local":
        prev = build_preview(
            hold_reason="external_action",
            capability=capability,
            operation=operation,
            destination=dest,
            payload=payload,
        )
        return {
            "allowed": False,
            "prompt": True,
            "status": "preview_required",
            "preview": prev,
        }

    return {
        "allowed": True,
        "prompt": False,
        "status": "allowed_in_scope",
        "grant_id": cover.get("grant_id"),
    }


def _held(
    store: CapabilityStore,
    *,
    project_id: str,
    capability: str,
    operation: str,
    destination: str,
    payload: dict[str, Any] | None,
    hold_reason: str,
) -> dict[str, Any]:
    preview = build_preview(
        hold_reason=hold_reason,
        capability=capability,
        operation=operation,
        destination=destination,
        payload=payload,
    )
    item = store.enqueue(
        project_id=project_id,
        capability=capability,
        operation=operation,
        destination=destination,
        payload=payload,
        state="held",
        hold_reason=hold_reason,
        preview=preview,
    )
    return {
        "allowed": False,
        "prompt": True,
        "held": True,
        "requires_specific_decision": True,
        "status": "held_for_decision",
        "preview": preview,
        "queue_item": item,
    }
