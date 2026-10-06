"""Run held/recurring actions with prompt accounting."""

from __future__ import annotations

from typing import Any

from mainframe.capabilities.authorize import authorize_action
from mainframe.capabilities.store import CapabilityStore


def run_recurring_report(
    store: CapabilityStore,
    *,
    project_id: str,
    destination: str,
    subject: str,
    body: str,
    prompts: int = 0,
) -> dict[str, Any]:
    decision = authorize_action(
        store,
        project_id=project_id,
        capability="sending_messages",
        operation="send_report",
        destination=destination,
        payload={"subject": subject, "body": body},
        prompts_so_far=prompts,
    )
    if not decision.get("allowed"):
        return {
            "ok": False,
            "ran_without_reprompt": False,
            "prompts": prompts + (1 if decision.get("prompt") else 0),
            "decision": decision,
        }
    return {
        "ok": True,
        "ran_without_reprompt": decision.get("prompt") is False,
        "prompts": prompts,
        "decision": decision,
        "sent_to": destination,
    }


def request_new_recipient_or_destructive(
    store: CapabilityStore,
    *,
    project_id: str,
    capability: str,
    operation: str,
    destination: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    decision = authorize_action(
        store,
        project_id=project_id,
        capability=capability,
        operation=operation,
        destination=destination,
        payload=payload,
    )
    return {
        "held": bool(decision.get("held")),
        "requires_specific_decision": bool(decision.get("requires_specific_decision")),
        "preview": decision.get("preview"),
        "decision": decision,
    }


def decide_held(
    store: CapabilityStore,
    item_id: str,
    *,
    choice: str,
) -> dict[str, Any]:
    item = store.get_queue_item(item_id)
    if not item:
        return {"ok": False, "error": "unknown_item"}
    if choice == "deny":
        updated = store.update_queue_item(item_id, state="denied")
        return {"ok": True, "choice": choice, "item": updated}
    if choice in {"allow_once", "allow_and_add_destination"}:
        updated = store.update_queue_item(item_id, state="approved")
        return {"ok": True, "choice": choice, "item": updated}
    return {"ok": False, "error": "invalid_choice", "item": item}
