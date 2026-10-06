"""Acceptance: offline input→report; unavailable AI blocks without corrupting outputs."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from mainframe.workflows.load import load_fixture, materialize_fixture
from mainframe.workflows.plan import dry_run_plan
from mainframe.workflows.runner import run_workflow
from mainframe.workflows.schema import FORMAT_VERSION, STEP_KINDS
from mainframe.workflows.validate import validate_workflow


OFFLINE_CAPS = {
    "local.read",
    "local.write",
    "local.artifact",
    "local.exec_test",
    "human.decide",
    "network.denied",
}


def run_workflows_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    tmp = Path(tempfile.mkdtemp(prefix="mf-wf-"))

    wf = load_fixture("input_to_report")
    checks.append(
        {
            "id": "versioned_format_and_step_kinds",
            "ok": (
                wf.get("format_version") == FORMAT_VERSION
                and {s["kind"] for s in wf["steps"]} <= set(STEP_KINDS)
                and "deterministic" in {s["kind"] for s in wf["steps"]}
                and "human" in {s["kind"] for s in wf["steps"]}
            ),
            "detail": {
                "format_version": wf.get("format_version"),
                "kinds": sorted({s["kind"] for s in wf["steps"]}),
            },
        }
    )

    # Invalid dependency rejected
    bad = json.loads(json.dumps(wf))
    bad["steps"][1]["depends_on"] = ["no_such_step"]
    v_bad = validate_workflow(bad, available_capabilities=OFFLINE_CAPS)
    checks.append(
        {
            "id": "reject_invalid_references",
            "ok": not v_bad["ok"]
            and any(e.get("code") == "invalid_dependency_ref" for e in v_bad["errors"]),
            "detail": v_bad["errors"],
        }
    )

    # Unbounded cycle rejected
    cyclic = json.loads(json.dumps(wf))
    cyclic["steps"][0]["depends_on"] = ["transform"]
    v_cyc = validate_workflow(cyclic, available_capabilities=OFFLINE_CAPS)
    checks.append(
        {
            "id": "reject_unbounded_cycles",
            "ok": not v_cyc["ok"] and any(e.get("code") == "unbounded_cycle" for e in v_cyc["errors"]),
            "detail": v_cyc["errors"],
        }
    )

    # Undeclared effects
    undecl = json.loads(json.dumps(wf))
    for s in undecl["steps"]:
        if s["id"] == "write_report":
            s["effects"] = []
            s["mutates"] = True
    v_eff = validate_workflow(undecl, available_capabilities=OFFLINE_CAPS)
    checks.append(
        {
            "id": "reject_undeclared_effects",
            "ok": not v_eff["ok"]
            and any(e.get("code") == "undeclared_effects" for e in v_eff["errors"]),
            "detail": v_eff["errors"],
        }
    )

    # Unavailable capability (strict)
    ai_wf = load_fixture("input_to_report_with_ai")
    v_ai_strict = validate_workflow(ai_wf, available_capabilities=OFFLINE_CAPS, strict_capabilities=True)
    checks.append(
        {
            "id": "reject_unavailable_ai_capability_strict",
            "ok": not v_ai_strict["ok"]
            and any(e.get("code") == "unavailable_capability" for e in v_ai_strict["errors"]),
            "detail": [e for e in v_ai_strict["errors"] if e.get("code") == "unavailable_capability"],
        }
    )

    # Dry-run plan for offline workflow
    plan = dry_run_plan(wf, inputs={"title": "Offline Report"}, available_capabilities=OFFLINE_CAPS)
    checks.append(
        {
            "id": "dry_run_plan",
            "ok": plan.get("ok") and plan.get("step_order") == ["load", "transform", "approve", "write_report"],
            "detail": {"order": plan.get("step_order"), "ownership": plan.get("ownership_note")},
        }
    )

    # Offline run succeeds
    work = materialize_fixture("input_to_report", tmp / "offline")
    result = run_workflow(
        load_fixture("input_to_report"),
        inputs={"title": "Offline Report"},
        work_dir=work,
        available_capabilities=OFFLINE_CAPS,
        human_decision="approve",
    )
    report_path = work / "report.json"
    report_ok = report_path.is_file()
    report_data = json.loads(report_path.read_text(encoding="utf-8")) if report_ok else {}
    prior_sha = (result.get("outputs") or {}).get("sha256")
    checks.append(
        {
            "id": "offline_input_to_report",
            "ok": (
                result.get("ok") is True
                and result.get("blocked") is False
                and report_ok
                and report_data.get("row_count") == 2
                and bool(prior_sha)
            ),
            "detail": {
                "state": result.get("state"),
                "artifact": result.get("outputs"),
                "receipts_n": len(result.get("receipts") or []),
            },
        }
    )

    # Add unavailable AI step — block precisely; prior report.json unchanged
    prior_text = report_path.read_text(encoding="utf-8") if report_ok else ""
    seeded = tmp / "seeded_block"
    seeded.mkdir(parents=True, exist_ok=True)
    (seeded / "records.json").write_text(
        (work / "records.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (seeded / "report.json").write_text(prior_text, encoding="utf-8")

    blocked = run_workflow(
        ai_wf,
        inputs={"title": "Should Block"},
        work_dir=seeded,
        available_capabilities=OFFLINE_CAPS,
        strict_capabilities=False,
    )
    after_text = (seeded / "report.json").read_text(encoding="utf-8")
    checks.append(
        {
            "id": "unavailable_ai_blocked_preserves_prior_outputs",
            "ok": (
                blocked.get("blocked") is True
                and blocked.get("blocked_step") == "ai_summary"
                and "ai.infer" in (blocked.get("blocked_reason") or "")
                and after_text == prior_text
                and blocked.get("prior_outputs_preserved") is True
                and "load" in (blocked.get("step_outputs") or {})
                and "transform" in (blocked.get("step_outputs") or {})
                and "write_report" not in (blocked.get("step_outputs") or {})
            ),
            "detail": {
                "blocked_step": blocked.get("blocked_step"),
                "blocked_reason": blocked.get("blocked_reason"),
                "prior_unchanged": after_text == prior_text,
                "step_outputs_keys": sorted((blocked.get("step_outputs") or {}).keys()),
            },
        }
    )

    # Bounded loop accepted; missing max_iterations rejected
    loop_ok = json.loads(json.dumps(wf))
    loop_ok["steps"][0]["loop"] = {"max_iterations": 2, "until_field": "done"}
    v_loop = validate_workflow(loop_ok, available_capabilities=OFFLINE_CAPS)
    loop_bad = json.loads(json.dumps(wf))
    loop_bad["steps"][0]["loop"] = {"until_field": "done"}
    v_loop_bad = validate_workflow(loop_bad, available_capabilities=OFFLINE_CAPS)
    checks.append(
        {
            "id": "bounded_loops_validated",
            "ok": v_loop.get("ok")
            and not v_loop_bad.get("ok")
            and any(e.get("code") == "unbounded_loop" for e in v_loop_bad["errors"]),
            "detail": {"ok_loop": v_loop.get("ok"), "bad_errors": v_loop_bad.get("errors")},
        }
    )

    checks.append(
        {
            "id": "freeforge_owns_semantics_not_openclaw_scheduling",
            "ok": (
                "freeforge" in str((result.get("ownership") or {}).get("workflow_semantics"))
                and "openclaw_not_duplicated"
                in str((result.get("ownership") or {}).get("scheduling_sessions"))
            ),
            "detail": result.get("ownership"),
        }
    )

    passed = sum(1 for c in checks if c["ok"])
    failed = len(checks) - passed
    return {"ok": failed == 0, "passed": passed, "failed": failed, "checks": checks}
