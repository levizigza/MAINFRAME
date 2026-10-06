"""Targeted fault-injection scenarios — deterministic local fixtures only."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from mainframe.faults.clock import detect_clock_change
from mainframe.faults.credentials import (
    check_exhausted_quota_no_paid_fallback,
    check_expired_credential,
    check_unauthorized_action,
    expired_fixture_pair,
)
from mainframe.faults.files import recover_interrupted_file, simulate_interrupted_write
from mainframe.triggers.events import make_dedupe_key
from mainframe.triggers.store import TriggerStore
from mainframe.workflows.evidence import check_extract_evidence
from mainframe.workflows.load import load_fixture, materialize_fixture
from mainframe.workflows.receipts import WorkflowReceiptStore
from mainframe.workflows.retry_policy import reconcile_before_retry, should_retry
from mainframe.workflows.runner import run_workflow

OFFLINE_CAPS = {
    "local.read",
    "local.write",
    "local.artifact",
    "human.decide",
    "network.denied",
}


def scenario_duplicate_events(work: Path) -> dict[str, Any]:
    work.mkdir(parents=True, exist_ok=True)
    store = TriggerStore(work / "triggers.sqlite")
    key = make_dedupe_key(source="file_change", identity="ledger.csv", content_fingerprint="abc")
    event = {
        "event_id": "evt_dup_1",
        "source": "file_change",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dedupe_key": key,
        "permission_scope": "local.trigger.report",
        "binding_id": "b1",
    }
    c1 = store.claim_event(event, run_id="run_dup_1")
    c2 = store.claim_event(event, run_id="run_dup_2")
    expected = "one_run_duplicate_suppressed"
    ok = bool(
        c1.get("first")
        and c1.get("run_id") == "run_dup_1"
        and c2.get("duplicate")
        and c2.get("prior_run_id") == "run_dup_1"
        and c2.get("first") is False
    )
    actual = expected if ok else "FAILED"
    return {
        "id": "duplicate_events",
        "class": "integration_fixture",
        "live_service": False,
        "expected_recovery": expected,
        "actual_recovery": actual,
        "pass": ok,
        "detail": {"first": c1, "second": c2},
        "fixes_required_if_fail": ["data_loss", "duplicate_effects"],
    }


def scenario_clock_changes() -> dict[str, Any]:
    base = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)
    jumped = detect_clock_change(
        last_known_utc=base,
        observed_utc=base + timedelta(hours=5),
    )
    expected = "record_anomaly_defer_catchup_to_scheduler_owner"
    actual = jumped.get("recovery") if jumped.get("clock_change_detected") and jumped.get("blind_fire_forbidden") else "FAILED"
    return {
        "id": "clock_changes",
        "class": "integration_fixture",
        "live_service": False,
        "expected_recovery": expected,
        "actual_recovery": actual,
        "pass": actual == expected,
        "detail": jumped,
        "fixes_required_if_fail": ["duplicate_effects"],
    }


def scenario_interrupted_files(work: Path) -> dict[str, Any]:
    work.mkdir(parents=True, exist_ok=True)
    path = work / "report.json"
    # Prior good content
    path.write_text('{"ok": true, "v": 1}\n', encoding="utf-8")
    prior = path.read_text(encoding="utf-8")
    sim = simulate_interrupted_write(path, '{"ok": tru')  # truncated
    # Final must still be prior content (crash before replace)
    mid = path.read_text(encoding="utf-8")
    rec = recover_interrupted_file(path, complete_text='{"ok": true, "v": 2}\n')
    after = path.read_text(encoding="utf-8")
    expected = "discard_tmp_atomic_complete_no_corruption"
    ok = (
        mid == prior
        and sim.get("tmp_exists")
        and rec.get("discarded_tmp")
        and rec.get("final_written_atomic")
        and '"v": 2' in after
        and not path.with_suffix(".json.tmp").is_file()
    )
    actual = expected if ok else "FAILED_data_corruption_or_tmp_promoted"
    return {
        "id": "interrupted_files",
        "class": "integration_fixture",
        "live_service": False,
        "expected_recovery": expected,
        "actual_recovery": actual,
        "pass": ok,
        "detail": {"sim": sim, "recover": rec},
        "fixes_required_if_fail": ["data_loss"],
    }


def scenario_process_crash(work: Path) -> dict[str, Any]:
    """Crash after artifact write: resume must not duplicate the write effect."""
    run_dir = materialize_fixture("interrupt_resume_delivery", work / "crash")
    wf = load_fixture("interrupt_resume_delivery")
    store = WorkflowReceiptStore(run_dir / "receipts.sqlite")
    r1 = run_workflow(
        wf,
        inputs={"title": "Crash"},
        work_dir=run_dir,
        available_capabilities=OFFLINE_CAPS,
        store=store,
        interrupt_after="write_report",
    )
    report = run_dir / "report.json"
    sha1 = report.read_bytes() if report.is_file() else b""
    # Simulate process death: new store handle, resume
    store2 = WorkflowReceiptStore(run_dir / "receipts.sqlite")
    r2 = run_workflow(
        wf,
        inputs={"title": "Crash"},
        work_dir=run_dir,
        available_capabilities=OFFLINE_CAPS,
        store=store2,
        resume_run_id=r1.get("run_id"),
        delivery_mode="succeed",
    )
    sha2 = report.read_bytes() if report.is_file() else b""
    expected = "resume_suppress_duplicate_write_effect"
    ok = (
        r1.get("interrupted")
        and sha1 == sha2
        and "write_report" in (r2.get("duplicated_suppressed") or [])
        and report.is_file()
    )
    return {
        "id": "process_crashes",
        "class": "integration_fixture",
        "live_service": False,
        "expected_recovery": expected,
        "actual_recovery": expected if ok else "FAILED_duplicate_or_lost",
        "pass": ok,
        "detail": {
            "interrupted": r1.get("state"),
            "resume_state": r2.get("state"),
            "duplicated_suppressed": r2.get("duplicated_suppressed"),
        },
        "fixes_required_if_fail": ["data_loss", "duplicate_effects"],
    }


def scenario_service_timeouts() -> dict[str, Any]:
    step = {
        "id": "deliver",
        "kind": "deterministic",
        "mutates": True,
        "effects": ["deliver_external"],
        "retries": {"max": 2, "backoff_ms": 10},
    }
    decision = should_retry(step, attempt=1, error_name="TimeoutError", prior_effect=None)
    # After timeout with unknown prior effect
    prior = {
        "operation_id": "op_timeout",
        "outcome": "unknown",
        "execution_status": "unknown",
        "side_effect_occurred": None,
    }
    after = should_retry(step, attempt=1, error_name="TimeoutError", prior_effect=prior)
    recon = reconcile_before_retry(prior)
    expected = "no_blind_retry_reconcile_or_unknown"
    ok = (
        after.get("retry") is False
        and after.get("requires_reconcile") is True
        and recon.get("safe_to_retry") is False
        and recon.get("report") == "outcome_unknown"
    )
    return {
        "id": "service_timeouts",
        "class": "integration_fixture",
        "live_service": False,
        "expected_recovery": expected,
        "actual_recovery": expected if ok else "FAILED_blind_retry",
        "pass": ok,
        "detail": {"first": decision, "with_unknown": after, "reconcile": recon},
        "fixes_required_if_fail": ["duplicate_effects"],
    }


def scenario_malformed_model_output() -> dict[str, Any]:
    source = "Package MAINFRAME version 0.1.20 with local workflows."
    # Schema-valid JSON that invents a version not in source
    bad = {"fields": {"version": "9.9.9", "name": "MAINFRAME"}}
    ev = check_extract_evidence(source=source, extracted=bad, required_fields=["version", "name"])
    expected = "reject_unsupported_no_side_effect"
    ok = ev.get("ok") is False and ev.get("rejected") is True
    return {
        "id": "malformed_model_output",
        "class": "integration_fixture",
        "live_service": False,
        "expected_recovery": expected,
        "actual_recovery": expected if ok else "FAILED_accepted_hallucination",
        "pass": ok,
        "detail": ev,
        "fixes_required_if_fail": ["unauthorized_actions"],
    }


def scenario_expired_credentials() -> dict[str, Any]:
    expired_at, now = expired_fixture_pair()
    check = check_expired_credential(expires_at=expired_at, now=now)
    expected = "refuse_use_require_refresh_or_pause"
    ok = check.get("expired") and check.get("action_allowed") is False and check.get("paid_fallback_used") is False
    return {
        "id": "expired_credentials",
        "class": "integration_fixture",
        "live_service": False,
        "expected_recovery": expected,
        "actual_recovery": check.get("recovery") if ok else "FAILED",
        "pass": ok,
        "detail": check,
        "fixes_required_if_fail": ["unauthorized_actions", "paid_fallback"],
    }


def scenario_exhausted_free_quotas() -> dict[str, Any]:
    check = check_exhausted_quota_no_paid_fallback()
    expected = "pause_no_paid_fallback"
    ok = bool(check.get("ok"))
    return {
        "id": "exhausted_free_quotas",
        "class": "integration_fixture",
        "live_service": False,
        "expected_recovery": expected,
        "actual_recovery": check.get("recovery") if ok else "FAILED_paid_fallback",
        "pass": ok,
        "detail": check,
        "fixes_required_if_fail": ["paid_fallback"],
    }


def scenario_lost_acknowledgement(work: Path) -> dict[str, Any]:
    """External write succeeds but ack is lost → visible unknown; no blind retry."""
    run_dir = materialize_fixture("interrupt_resume_delivery", work / "lost_ack")
    wf = load_fixture("interrupt_resume_delivery")
    store = WorkflowReceiptStore(run_dir / "receipts.sqlite")
    r1 = run_workflow(
        wf,
        inputs={"title": "LostAck"},
        work_dir=run_dir,
        available_capabilities=OFFLINE_CAPS,
        store=store,
        delivery_mode="unknown",
    )
    prior = (r1.get("step_outputs") or {}).get("deliver", {}).get("effect_receipt")
    recon = reconcile_before_retry(prior)
    # Attempt resume must not blind-retry deliver
    r2 = run_workflow(
        wf,
        inputs={"title": "LostAck"},
        work_dir=run_dir,
        available_capabilities=OFFLINE_CAPS,
        store=store,
        resume_run_id=r1.get("run_id"),
        delivery_mode="succeed",  # would succeed if blindly retried
    )
    expected = "outcome_unknown_visible_no_blind_retry"
    ok = (
        r1.get("outcome_unknown") is True
        and r1.get("state") == "outcome_unknown"
        and recon.get("safe_to_retry") is False
        and (
            r2.get("outcome_unknown") is True
            or r2.get("blocked_reason") == "outcome_unknown"
            or "deliver" in (r2.get("duplicated_suppressed") or [])
        )
    )
    # Critical: must NOT have flipped to succeeded via blind retry of deliver
    not_blind = r2.get("state") != "succeeded" or r2.get("outcome_unknown")
    # Actually if deliver was suppressed as duplicate of unknown, state stays unknown
    ok = ok and (r2.get("state") in {"outcome_unknown", "blocked"} or r2.get("outcome_unknown"))
    return {
        "id": "lost_acknowledgement_external_write",
        "class": "integration_fixture",
        "live_service": False,
        "expected_recovery": expected,
        "actual_recovery": expected if ok else f"FAILED_state={r2.get('state')}",
        "pass": bool(ok),
        "detail": {
            "first_state": r1.get("state"),
            "resume_state": r2.get("state"),
            "reconcile": recon,
            "duplicated_suppressed": r2.get("duplicated_suppressed"),
            "not_blind_succeeded": not_blind,
        },
        "fixes_required_if_fail": ["duplicate_effects", "data_loss"],
    }


def scenario_cancellation_preserves_completed(work: Path) -> dict[str, Any]:
    run_dir = materialize_fixture("interrupt_resume_delivery", work / "cancel")
    wf = load_fixture("interrupt_resume_delivery")
    store = WorkflowReceiptStore(run_dir / "receipts.sqlite")
    mid = run_workflow(
        wf,
        inputs={"title": "CancelFx"},
        work_dir=run_dir,
        available_capabilities=OFFLINE_CAPS,
        store=store,
        interrupt_after="write_report",
    )
    report = run_dir / "report.json"
    completed_before = report.is_file()
    receipts_before = [
        r for r in store.list_step_receipts(mid["run_id"]) if r.get("state") == "succeeded"
    ]
    store.request_cancel(mid["run_id"])
    rc = run_workflow(
        wf,
        inputs={"title": "CancelFx"},
        work_dir=run_dir,
        available_capabilities=OFFLINE_CAPS,
        store=store,
        resume_run_id=mid["run_id"],
        delivery_mode="succeed",
    )
    receipts_after = store.list_step_receipts(mid["run_id"])
    still_have_write = any(
        r.get("step_id") == "write_report" and r.get("state") == "succeeded" for r in receipts_after
    )
    deliver_new = any(
        r.get("step_id") == "deliver" and r.get("state") == "succeeded" for r in receipts_after
    )
    expected = "cancel_blocks_new_effects_completed_remain"
    ok = (
        completed_before
        and (rc.get("state") == "cancelled" or rc.get("blocked_reason") == "cancelled")
        and still_have_write
        and not deliver_new
        and len(receipts_before) >= 1
    )
    return {
        "id": "cancellation_completed_effects_recorded",
        "class": "integration_fixture",
        "live_service": False,
        "expected_recovery": expected,
        "actual_recovery": expected if ok else "FAILED",
        "pass": ok,
        "detail": {
            "cancel_state": rc.get("state"),
            "write_receipt_kept": still_have_write,
            "deliver_succeeded_after_cancel": deliver_new,
            "completed_steps_before_cancel": [r.get("step_id") for r in receipts_before],
        },
        "fixes_required_if_fail": ["data_loss", "duplicate_effects"],
    }


def scenario_unauthorized_and_paid_fallback() -> dict[str, Any]:
    unauth = check_unauthorized_action(tool="remote.billing.activate", local=False)
    # remote non-local should be denied by cost gate
    expected = "deny_no_paid_fallback"
    ok = unauth.get("allowed") is False and unauth.get("paid_fallback_used") is False
    return {
        "id": "unauthorized_actions_and_paid_fallback",
        "class": "integration_fixture",
        "live_service": False,
        "expected_recovery": expected,
        "actual_recovery": expected if ok else "FAILED_allowed_or_paid",
        "pass": ok,
        "detail": unauth,
        "fixes_required_if_fail": ["unauthorized_actions", "paid_fallback"],
    }


def run_all_fault_scenarios(*, work: Path | None = None) -> list[dict[str, Any]]:
    root = work or Path(tempfile.mkdtemp(prefix="mf_faults_"))
    root.mkdir(parents=True, exist_ok=True)
    return [
        scenario_duplicate_events(root / "dup"),
        scenario_clock_changes(),
        scenario_interrupted_files(root / "files"),
        scenario_process_crash(root / "crash"),
        scenario_service_timeouts(),
        scenario_malformed_model_output(),
        scenario_expired_credentials(),
        scenario_exhausted_free_quotas(),
        scenario_lost_acknowledgement(root / "lost_ack"),
        scenario_cancellation_preserves_completed(root / "cancel"),
        scenario_unauthorized_and_paid_fallback(),
    ]
