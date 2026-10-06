"""Acceptance: interrupt after output, resume without duplicate, failed delivery, unknown outcome."""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from typing import Any

from mainframe.workflows.effects import compensation_for
from mainframe.workflows.load import load_fixture, materialize_fixture
from mainframe.workflows.receipts import WorkflowReceiptStore
from mainframe.workflows.runner import run_workflow

OFFLINE_CAPS = {
    "local.read",
    "local.write",
    "local.artifact",
    "human.decide",
    "network.denied",
}


def run_workflow_resilience_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    tmp = Path(tempfile.mkdtemp(prefix="mf-wf-res-"))
    work = materialize_fixture("interrupt_resume_delivery", tmp / "run")
    wf = load_fixture("interrupt_resume_delivery")
    store = WorkflowReceiptStore(work / "receipts.sqlite")

    # 1) Interrupt after write_report creates output
    r1 = run_workflow(
        wf,
        inputs={"title": "Resilience"},
        work_dir=work,
        available_capabilities=OFFLINE_CAPS,
        store=store,
        interrupt_after="write_report",
    )
    report = work / "report.json"
    sha1 = hashlib.sha256(report.read_bytes()).hexdigest() if report.is_file() else None
    checks.append(
        {
            "id": "interrupt_after_output_created",
            "ok": (
                r1.get("interrupted") is True
                and r1.get("state") == "interrupted"
                and report.is_file()
                and "write_report" in (r1.get("step_outputs") or {})
                and "deliver" not in (r1.get("step_outputs") or {})
            ),
            "detail": {
                "state": r1.get("state"),
                "sha256": sha1,
                "run_id": r1.get("run_id"),
            },
        }
    )

    # 2) Resume without duplicating the write
    r2 = run_workflow(
        wf,
        inputs={"title": "Resilience"},
        work_dir=work,
        available_capabilities=OFFLINE_CAPS,
        store=store,
        resume_run_id=r1.get("run_id"),
        delivery_mode="fail",
    )
    sha2 = hashlib.sha256(report.read_bytes()).hexdigest() if report.is_file() else None
    checks.append(
        {
            "id": "resume_without_duplicating_output",
            "ok": (
                sha1 == sha2
                and "write_report" in (r2.get("duplicated_suppressed") or [])
                and report.is_file()
            ),
            "detail": {
                "sha_before": sha1,
                "sha_after": sha2,
                "duplicated_suppressed": r2.get("duplicated_suppressed"),
                "state": r2.get("state"),
            },
        }
    )

    # 3) Failed delivery retained for review
    failed = r2.get("failed_deliveries") or store.failed_deliveries(r1["run_id"])
    checks.append(
        {
            "id": "failed_delivery_retained_for_review",
            "ok": (
                r2.get("blocked_reason") == "delivery_failed"
                and len(failed) >= 1
                and (failed[0].get("delivery_status") == "failed"
                     or (failed[0].get("effect_receipt") or {}).get("delivery_status") == "failed")
                and (failed[0].get("effect_receipt") or {}).get("execution_status") == "succeeded"
            ),
            "detail": {
                "failed_n": len(failed),
                "sample": failed[0] if failed else None,
                "execution_vs_delivery_separated": True,
            },
        }
    )

    # 4) External action with unknown final outcome
    work2 = materialize_fixture("interrupt_resume_delivery", tmp / "unknown")
    store2 = WorkflowReceiptStore(work2 / "receipts.sqlite")
    ru = run_workflow(
        wf,
        inputs={"title": "Unknown"},
        work_dir=work2,
        available_capabilities=OFFLINE_CAPS,
        store=store2,
        delivery_mode="unknown",
    )
    checks.append(
        {
            "id": "external_outcome_unknown_reported",
            "ok": (
                ru.get("outcome_unknown") is True
                and ru.get("blocked_reason") == "outcome_unknown"
                and ru.get("state") == "outcome_unknown"
                and (ru.get("step_outputs") or {}).get("deliver", {}).get("outcome_unknown") is True
            ),
            "detail": {
                "state": ru.get("state"),
                "deliver": (ru.get("step_outputs") or {}).get("deliver"),
            },
        }
    )

    # Compensation: local draft delete ≠ retract received message
    draft = compensation_for("write_local_draft")
    retract = compensation_for("retract_received_message")
    checks.append(
        {
            "id": "compensation_requires_real_inverse",
            "ok": (
                draft.get("supported") is True
                and draft.get("inverse") == "delete_local_draft"
                and retract.get("supported") is False
                and "local draft" in (retract.get("note") or "").lower()
            ),
            "detail": {"draft": draft, "retract": retract},
        }
    )

    # Stable operation IDs across resume
    ops = {
        r.get("step_id"): r.get("operation_id")
        for r in store.list_step_receipts(r1["run_id"])
        if r.get("operation_id") and r.get("step_id") == "write_report"
    }
    checks.append(
        {
            "id": "stable_operation_ids_through_connectors",
            "ok": bool(ops.get("write_report")) and ops["write_report"].startswith("op_"),
            "detail": ops,
        }
    )

    # Cancellation
    work3 = materialize_fixture("interrupt_resume_delivery", tmp / "cancel")
    store3 = WorkflowReceiptStore(work3 / "receipts.sqlite")
    # Start then cancel mid-flight via pre-set flag after start — use interrupt + cancel API
    mid = run_workflow(
        wf,
        inputs={"title": "Cancel"},
        work_dir=work3,
        available_capabilities=OFFLINE_CAPS,
        store=store3,
        interrupt_after="load",
    )
    store3.request_cancel(mid["run_id"])
    rc = run_workflow(
        wf,
        inputs={"title": "Cancel"},
        work_dir=work3,
        available_capabilities=OFFLINE_CAPS,
        store=store3,
        resume_run_id=mid["run_id"],
    )
    checks.append(
        {
            "id": "cancellation_honored_on_resume",
            "ok": rc.get("state") == "cancelled" or rc.get("blocked_reason") == "cancelled",
            "detail": {"state": rc.get("state"), "reason": rc.get("blocked_reason")},
        }
    )

    # Concurrency limit
    work4 = materialize_fixture("interrupt_resume_delivery", tmp / "conc")
    store4 = WorkflowReceiptStore(work4 / "receipts.sqlite")
    a = run_workflow(
        wf,
        inputs={"title": "A"},
        work_dir=work4,
        available_capabilities=OFFLINE_CAPS,
        store=store4,
        interrupt_after="load",
        max_concurrent=1,
    )
    # Hold slot by not finishing — interrupted run should release slot in finish_run
    # After interrupt, slot released. Force hold: acquire manually
    store4.acquire_slot(max_concurrent=1, run_id="holder_manual")
    blocked = run_workflow(
        wf,
        inputs={"title": "B"},
        work_dir=work4 / "b",
        available_capabilities=OFFLINE_CAPS,
        store=store4,
        max_concurrent=1,
    )
    store4.release_slot("holder_manual")
    checks.append(
        {
            "id": "concurrency_limit_blocks",
            "ok": blocked.get("state") == "blocked_concurrency" and a.get("interrupted"),
            "detail": {"blocked_state": blocked.get("state"), "a": a.get("state")},
        }
    )

    # Diagnostics redacted
    from mainframe.workflows.redact_diag import redact_diag

    leaked = redact_diag({"api_token": "sk-SECRETVALUE", "ok": True})
    checks.append(
        {
            "id": "diagnostics_without_secrets",
            "ok": leaked.get("api_token") == "[REDACTED]" and leaked.get("ok") is True,
            "detail": leaked,
        }
    )

    passed = sum(1 for c in checks if c["ok"])
    failed = len(checks) - passed
    return {"ok": failed == 0, "passed": passed, "failed": failed, "checks": checks}
