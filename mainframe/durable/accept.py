"""Acceptance: crash before dispatch / during exec / after effect; recover safely."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from mainframe.durable.engine_status import clear_engine_status_for_tests, websocket_policy
from mainframe.durable.idempotency import EXACTLY_ONCE_LIMITS, destination_policy
from mainframe.durable.reconcile import reconcile_freeforge_records
from mainframe.durable.runner import (
    SimulatedCrash,
    on_timeout_after_mutation,
    plan_task,
    recover,
    run_until,
)
from mainframe.durable.states import ALL_STATES, can_transition
from mainframe.durable.store import DurableStore
from mainframe.freeforge import SELECTED_ENGINE


def run_durable_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    clear_engine_status_for_tests()
    tmp = Path(tempfile.mkdtemp(prefix="mf-durable-"))
    db = tmp / "durable.sqlite"
    store = DurableStore(db)

    # --- States are distinct ---
    checks.append(
        {
            "id": "states_separated",
            "ok": set(ALL_STATES)
            == {"planned", "started", "succeeded", "failed", "cancelled", "outcome_unknown"}
            and can_transition("planned", "started")
            and not can_transition("succeeded", "started")
            and can_transition("started", "outcome_unknown"),
            "detail": list(ALL_STATES),
        }
    )

    # --- WebSocket not assumed to replay ---
    ws = websocket_policy()
    checks.append(
        {
            "id": "websocket_not_assumed_to_replay",
            "ok": ws.get("assume_websocket_replays_missed_events") is False,
            "detail": ws,
        }
    )

    # --- Exactly-once limits documented ---
    pol = destination_policy("local_effect_sink")
    checks.append(
        {
            "id": "exactly_once_limits_documented",
            "ok": (
                pol.get("exactly_once_guaranteed") is False
                and pol.get("supports_idempotency_key") is True
                and "Exactly-once" in EXACTLY_ONCE_LIMITS
            ),
            "detail": {"policy": pol, "limits_prefix": EXACTLY_ONCE_LIMITS[:120]},
        }
    )

    # --- Crash before dispatch ---
    p1 = plan_task(store, goal="effect-before-dispatch")
    oid1 = p1["task"]["operation_id"]
    try:
        run_until(store, oid1, crash_at="before_dispatch")
        crashed1 = False
    except SimulatedCrash as exc:
        crashed1 = exc.where == "before_dispatch"
    t1 = store.get(oid1)
    rec1 = recover(store, oid1)
    checks.append(
        {
            "id": "crash_before_dispatch_recover",
            "ok": (
                crashed1
                and t1 is not None
                and t1["state"] == "planned"
                and rec1.get("ok")
                and (rec1.get("task") or {}).get("state") == "succeeded"
                and (rec1.get("task") or {}).get("effect_receipt", {}).get("side_effect_occurred")
                is True
                and rec1.get("duplicate_mutation_attempted") is not True
            ),
            "detail": {
                "state_after_crash": t1["state"] if t1 else None,
                "recover_action": rec1.get("action"),
                "final": (rec1.get("task") or {}).get("state"),
            },
        }
    )

    # --- Crash during execution ---
    clear_engine_status_for_tests()
    store2 = DurableStore(tmp / "durable2.sqlite")
    p2 = plan_task(store2, goal="effect-during-exec")
    oid2 = p2["task"]["operation_id"]
    try:
        run_until(store2, oid2, crash_at="during_execution")
        crashed2 = False
    except SimulatedCrash as exc:
        crashed2 = exc.where == "during_execution"
    t2 = store2.get(oid2)
    # No effect yet
    sink_before = store2.get_effect_by_key(t2["idempotency_key"]) if t2 else None
    rec2 = recover(store2, oid2)
    checks.append(
        {
            "id": "crash_during_execution_recover",
            "ok": (
                crashed2
                and t2 is not None
                and t2["state"] == "started"
                and sink_before is None
                and rec2.get("ok")
                and (rec2.get("task") or {}).get("state") == "succeeded"
                and rec2.get("falsely_claimed_effect_never_happened") is False
                and rec2.get("duplicate_mutation_attempted") is False
            ),
            "detail": {
                "after_crash": t2["state"] if t2 else None,
                "reconcile_actions": (rec2.get("reconcile") or {}).get("actions"),
                "final": (rec2.get("task") or {}).get("state"),
            },
        }
    )

    # --- Crash after effect before ack ---
    clear_engine_status_for_tests()
    store3 = DurableStore(tmp / "durable3.sqlite")
    p3 = plan_task(store3, goal="effect-after-effect")
    oid3 = p3["task"]["operation_id"]
    try:
        run_until(store3, oid3, crash_at="after_effect_before_ack")
        crashed3 = False
    except SimulatedCrash as exc:
        crashed3 = exc.where == "after_effect_before_ack"
    t3 = store3.get(oid3)
    sink3 = store3.get_effect_by_key(t3["idempotency_key"]) if t3 else None
    # Simulate timeout path instead of blind retry
    timeout = on_timeout_after_mutation(store3, oid3)
    rec3 = recover(store3, oid3)
    checks.append(
        {
            "id": "crash_after_effect_before_ack_recover",
            "ok": (
                crashed3
                and sink3 is not None
                and sink3.get("side_effect_occurred") is True
                and t3 is not None
                and t3["state"] == "started"  # ack never happened
                and timeout.get("duplicate_mutation_attempted") is False
                and (timeout.get("task") or {}).get("state") == "succeeded"
                and rec3.get("completed_work_preserved") is True
                and rec3.get("falsely_claimed_effect_never_happened") is False
                and (rec3.get("task") or {}).get("state") == "succeeded"
                # Must not lose the effect id
                and (rec3.get("task") or {}).get("effect_receipt", {}).get("effect_id")
                == sink3.get("effect_id")
            ),
            "detail": {
                "effect_id": sink3.get("effect_id") if sink3 else None,
                "timeout_state": (timeout.get("task") or {}).get("state"),
                "timeout_actions": timeout.get("actions"),
                "recover_action": rec3.get("action"),
            },
        }
    )

    # --- Idempotent replay does not duplicate ---
    clear_engine_status_for_tests()
    store4 = DurableStore(tmp / "durable4.sqlite")
    p4 = plan_task(store4, goal="idempotent-replay")
    oid4 = p4["task"]["operation_id"]
    r_a = run_until(store4, oid4)
    # Forced second apply attempt via record_effect
    key4 = store4.get(oid4)["idempotency_key"]
    r_b = store4.record_effect(
        operation_id=oid4,
        idempotency_key=key4,
        payload={"action": "mutate", "goal": "idempotent-replay"},
    )
    checks.append(
        {
            "id": "idempotency_suppresses_duplicate_effect",
            "ok": (
                r_a.get("ok")
                and r_b.get("applied_now") is False
                and r_b["receipt"].get("duplicate_suppressed") is True
                and r_b["receipt"]["effect_id"] == r_a["receipt"]["effect_id"]
            ),
            "detail": {
                "first_effect": r_a.get("receipt", {}).get("effect_id"),
                "second": r_b.get("receipt"),
            },
        }
    )

    # --- FreeForge reconcile batch uses selected engine ---
    batch = reconcile_freeforge_records(store3, states=["succeeded"])
    checks.append(
        {
            "id": "freeforge_reconcile_uses_selected_engine",
            "ok": SELECTED_ENGINE == "openclaw_embedded_agent_runtime"
            and batch.get("websocket_policy", {}).get("assume_websocket_replays_missed_events")
            is False,
            "detail": {"engine": SELECTED_ENGINE, "batch_ok": batch.get("ok")},
        }
    )

    # --- Lease blocks concurrent owner ---
    store5 = DurableStore(tmp / "durable5.sqlite")
    p5 = plan_task(store5, goal="lease-test")
    oid5 = p5["task"]["operation_id"]
    a = store5.acquire_lease(oid5, "owner-a", ttl_seconds=120)
    b = store5.acquire_lease(oid5, "owner-b", ttl_seconds=120)
    checks.append(
        {
            "id": "lease_blocks_other_owner",
            "ok": a.get("ok") is True and b.get("ok") is False and b.get("error") == "lease_held",
            "detail": {"a": a, "b": b},
        }
    )

    passed = sum(1 for c in checks if c["ok"])
    failed = len(checks) - passed
    return {"ok": failed == 0, "passed": passed, "failed": failed, "checks": checks}
