"""Reconcile FreeForge durable records with selected-engine status APIs."""

from __future__ import annotations

from typing import Any

from mainframe.durable.engine_status import query_engine_status, websocket_policy
from mainframe.durable.store import DurableStore
from mainframe.freeforge import SELECTED_ENGINE


def reconcile_with_engine(
    store: DurableStore,
    operation_id: str,
    *,
    timeout_after_mutation: bool = False,
) -> dict[str, Any]:
    """
    After restart, connection gap, or timeout following an external mutation:
    poll the supported status API. Never automatically duplicate the mutation.
    """
    task = store.get(operation_id)
    if not task:
        return {"ok": False, "error": "unknown_operation"}

    status = query_engine_status(operation_id)
    actions: list[str] = []
    duplicate_mutation_attempted = False

    # Map engine status → durable state
    eng = status.get("status")
    if status.get("found") and eng in {"succeeded", "completed", "ok"}:
        receipt = task.get("effect_receipt") or {
            "effect_id": status.get("effect_id"),
            "operation_id": operation_id,
            "side_effect_occurred": True,
            "source": "engine_status_api",
        }
        if task["state"] not in {"succeeded"}:
            store.transition(
                operation_id,
                "succeeded",
                reason="reconcile_engine_status_succeeded",
                effect_receipt=receipt,
                engine_status=status,
            )
            actions.append("mark_succeeded_from_status_api")
        else:
            actions.append("already_succeeded")
    elif status.get("found") and eng in {"failed", "error"}:
        if task["state"] not in {"failed", "succeeded", "cancelled"}:
            store.transition(
                operation_id,
                "failed",
                reason="reconcile_engine_status_failed",
                error=str((status.get("detail") or {}).get("error") or "engine_failed"),
                engine_status=status,
            )
            actions.append("mark_failed_from_status_api")
    elif task.get("effect_receipt") and task["effect_receipt"].get("side_effect_occurred"):
        # Local receipt proves effect — do not claim it never happened
        if task["state"] != "succeeded":
            store.transition(
                operation_id,
                "succeeded",
                reason="reconcile_local_effect_receipt",
                effect_receipt=task["effect_receipt"],
                engine_status=status,
            )
            actions.append("mark_succeeded_from_local_receipt")
        else:
            actions.append("receipt_confirms_succeeded")
    else:
        # Sink lookup by idempotency key
        key = task.get("idempotency_key")
        sink = store.get_effect_by_key(key) if key else None
        if sink and sink.get("side_effect_occurred"):
            store.transition(
                operation_id,
                "succeeded",
                reason="reconcile_effect_sink",
                effect_receipt=sink,
                engine_status=status,
            )
            actions.append("mark_succeeded_from_effect_sink")
        else:
            if task["state"] == "started" or timeout_after_mutation:
                store.transition(
                    operation_id,
                    "outcome_unknown",
                    reason="reconcile_no_status_yet",
                    engine_status=status,
                )
                actions.append("mark_outcome_unknown_await_status")
            else:
                actions.append("no_change")
            # Critical: do NOT re-dispatch mutation here
            duplicate_mutation_attempted = False
            actions.append("refused_automatic_duplicate_mutation")

    refreshed = store.get(operation_id)
    return {
        "ok": True,
        "operation_id": operation_id,
        "freeforge_record_id": task.get("freeforge_record_id"),
        "engine": SELECTED_ENGINE,
        "engine_status": status,
        "task": refreshed,
        "actions": actions,
        "duplicate_mutation_attempted": duplicate_mutation_attempted,
        "timeout_after_mutation": timeout_after_mutation,
        "websocket_policy": websocket_policy(),
        "note": (
            "Reconciliation uses supported status APIs / durable receipts. "
            "A timeout after an external mutation triggers status reconciliation, "
            "not an automatic duplicate mutation."
        ),
    }


def reconcile_freeforge_records(
    store: DurableStore,
    *,
    states: list[str] | None = None,
) -> dict[str, Any]:
    """Reconcile FreeForge-tracked ops that are non-terminal or outcome_unknown."""
    targets = states or ["started", "outcome_unknown"]
    results = []
    for st in targets:
        for task in store.list_by_state(st):
            results.append(reconcile_with_engine(store, task["operation_id"]))
    return {
        "ok": True,
        "reconciled_n": len(results),
        "results": results,
        "websocket_policy": websocket_policy(),
    }
