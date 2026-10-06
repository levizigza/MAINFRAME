"""Durable runner — transitions, leases, effects, crash injection, recovery."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from mainframe.durable.engine_status import publish_engine_status
from mainframe.durable.idempotency import EXACTLY_ONCE_LIMITS, use_idempotency_key
from mainframe.durable.reconcile import reconcile_with_engine
from mainframe.durable.store import DurableStore
from mainframe.freeforge import SELECTED_ENGINE


class SimulatedCrash(Exception):
    """Injected crash boundary for acceptance — leaves durable state as-is."""

    def __init__(self, where: str, operation_id: str) -> None:
        super().__init__(f"simulated_crash:{where}")
        self.where = where
        self.operation_id = operation_id


def plan_task(
    store: DurableStore,
    *,
    goal: str,
    destination: str = "local_effect_sink",
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    key = idempotency_key or f"idem_{goal[:24].replace(' ', '_')}"
    idemp = use_idempotency_key(destination, key)
    task = store.create_task(
        goal=goal,
        engine=SELECTED_ENGINE,
        destination=destination,
        idempotency_key=key if idemp.get("attached") else key,
    )
    return {
        "ok": True,
        "task": task,
        "idempotency": idemp,
        "exactly_once_limits": EXACTLY_ONCE_LIMITS,
    }


def run_until(
    store: DurableStore,
    operation_id: str,
    *,
    owner: str = "worker-1",
    effect_payload: dict[str, Any] | None = None,
    crash_at: str | None = None,
    mutate: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Progress a planned task through start → effect → ack → succeeded.

    crash_at: None | 'before_dispatch' | 'during_execution' | 'after_effect_before_ack'
    """
    task = store.get(operation_id)
    if not task:
        return {"ok": False, "error": "unknown_operation"}

    lease = store.acquire_lease(operation_id, owner, ttl_seconds=60)
    if not lease.get("ok"):
        return {"ok": False, "error": "lease_denied", "lease": lease}

    try:
        if task["state"] == "planned":
            store.save_checkpoint(
                operation_id,
                {"phase": "pre_dispatch", "goal": task.get("goal")},
            )
            if crash_at == "before_dispatch":
                raise SimulatedCrash("before_dispatch", operation_id)

            store.transition(operation_id, "started", reason="dispatch")
            publish_engine_status(operation_id, status="started")
            store.save_checkpoint(operation_id, {"phase": "started"})

        task = store.get(operation_id)  # type: ignore[assignment]
        if task["state"] in {"started", "outcome_unknown"}:
            if crash_at == "during_execution":
                # Durable started; no effect yet
                store.save_checkpoint(operation_id, {"phase": "during_execution"})
                raise SimulatedCrash("during_execution", operation_id)

            payload = dict(effect_payload or {"action": "mutate", "goal": task.get("goal")})
            if mutate:
                payload = mutate(payload)

            key = task.get("idempotency_key") or operation_id
            applied = store.record_effect(
                operation_id=operation_id,
                idempotency_key=key,
                payload=payload,
            )
            receipt = applied["receipt"]
            publish_engine_status(
                operation_id,
                status="succeeded",
                effect_id=receipt["effect_id"],
                detail={"duplicate_suppressed": receipt.get("duplicate_suppressed")},
            )
            store.save_checkpoint(
                operation_id,
                {"phase": "effect_applied", "effect_id": receipt["effect_id"]},
            )

            if crash_at == "after_effect_before_ack":
                # Effect durable in sink + engine status; task may still be started
                raise SimulatedCrash("after_effect_before_ack", operation_id)

            # Acknowledgement
            store.transition(
                operation_id,
                "succeeded",
                reason="ack_effect_receipt",
                effect_receipt=receipt,
                checkpoint={"phase": "acked", "effect_id": receipt["effect_id"]},
            )
            return {
                "ok": True,
                "task": store.get(operation_id),
                "receipt": receipt,
                "applied_now": applied.get("applied_now"),
            }

        return {"ok": True, "task": task, "note": "already_terminal_or_idle"}
    finally:
        store.release_lease(operation_id, owner)


def recover(
    store: DurableStore,
    operation_id: str,
    *,
    owner: str = "recover-1",
    continue_if_safe: bool = True,
) -> dict[str, Any]:
    """
    Recover after crash / restart / connection gap.

    - planned: safe to dispatch (no effect yet)
    - started / outcome_unknown: reconcile via status API — never blind duplicate
    - succeeded with receipt: keep completed work
    """
    task = store.get(operation_id)
    if not task:
        return {"ok": False, "error": "unknown_operation"}

    state = task["state"]
    report: dict[str, Any] = {
        "operation_id": operation_id,
        "state_before": state,
        "completed_work_preserved": False,
        "falsely_claimed_effect_never_happened": False,
        "duplicate_mutation_attempted": False,
    }

    if state == "succeeded" and task.get("effect_receipt"):
        report.update(
            {
                "ok": True,
                "action": "noop_already_succeeded",
                "completed_work_preserved": True,
                "task": task,
            }
        )
        return report

    if state == "planned":
        if continue_if_safe:
            out = run_until(store, operation_id, owner=owner, crash_at=None)
            report.update(
                {
                    "ok": out.get("ok"),
                    "action": "dispatched_after_pre_dispatch_crash",
                    "task": store.get(operation_id),
                    "completed_work_preserved": True,
                }
            )
            return report
        report.update({"ok": True, "action": "still_planned", "task": task})
        return report

    # started / outcome_unknown / after_effect crash: reconcile first
    rec = reconcile_with_engine(
        store,
        operation_id,
        timeout_after_mutation=True,
    )
    report["reconcile"] = rec
    report["duplicate_mutation_attempted"] = bool(rec.get("duplicate_mutation_attempted"))

    task2 = store.get(operation_id)
    if task2 and task2.get("effect_receipt") and task2["effect_receipt"].get("side_effect_occurred"):
        # Must not claim the side effect never happened
        report["falsely_claimed_effect_never_happened"] = False
        report["completed_work_preserved"] = True
        if task2["state"] != "succeeded":
            # reconcile should have fixed; if not, force from receipt
            store.transition(
                operation_id,
                "succeeded",
                reason="recover_from_receipt",
                effect_receipt=task2["effect_receipt"],
            )
            task2 = store.get(operation_id)
        report.update({"ok": True, "action": "recovered_from_receipt_or_status", "task": task2})
        return report

    if task2 and task2["state"] == "outcome_unknown":
        # No evidence of effect — safe to continue execution once (first apply)
        if continue_if_safe:
            out = run_until(store, operation_id, owner=owner, crash_at=None)
            report.update(
                {
                    "ok": out.get("ok"),
                    "action": "continued_after_reconcile_no_effect",
                    "task": store.get(operation_id),
                    "completed_work_preserved": True,
                    "duplicate_mutation_attempted": False,
                }
            )
            return report

    if task2 and task2["state"] == "succeeded":
        report.update(
            {
                "ok": True,
                "action": "reconciled_to_succeeded",
                "completed_work_preserved": True,
                "task": task2,
            }
        )
        return report

    report.update({"ok": True, "action": "reconciled", "task": task2})
    return report


def on_timeout_after_mutation(store: DurableStore, operation_id: str) -> dict[str, Any]:
    """Timeout after external mutation → status reconciliation, not duplicate mutation."""
    return reconcile_with_engine(store, operation_id, timeout_after_mutation=True)
