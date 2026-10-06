"""Run all local offline demonstrations and return a single report."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from mainframe.config import ROOT, RUNS_DIR, ensure_state
from mainframe.demos.deterministic import (
    demo_browser_local_fixture,
    demo_records_to_report,
    demo_repo_inspect_and_test,
)
from mainframe.demos.mock_repair import (
    run_ai_dependent_pause,
    run_cancellation_path,
    run_failure_path,
    run_mock_issue_to_patch,
)
from mainframe.demos.network import offline_network


def run_all_demos() -> dict[str, Any]:
    ensure_state()
    with offline_network() as net:
        results = {
            "deterministic_repo_inspect_test": demo_repo_inspect_and_test(),
            "deterministic_records_report": demo_records_to_report(),
            "deterministic_browser_local": demo_browser_local_fixture(),
            "mock_issue_to_patch": run_mock_issue_to_patch(),
            "failure_path": run_failure_path(),
            "cancellation_path": run_cancellation_path(),
            "ai_dependent_pause": run_ai_dependent_pause(),
        }

    # Acceptance predicates
    d1 = results["deterministic_repo_inspect_test"]
    d2 = results["deterministic_records_report"]
    d3 = results["deterministic_browser_local"]
    mock = results["mock_issue_to_patch"]
    fail = results["failure_path"]
    cancel = results["cancellation_path"]
    ai = results["ai_dependent_pause"]

    checks = [
        {
            "id": "deterministic_offline_repo",
            "ok": bool(d1.get("ok")) and d1.get("automation_kind") == "non_ai_deterministic",
        },
        {
            "id": "deterministic_offline_report",
            "ok": bool(d2.get("ok")) and d2.get("automation_kind") == "non_ai_deterministic",
        },
        {
            "id": "deterministic_offline_browser",
            "ok": bool(d3.get("ok")) and d3.get("automation_kind") == "non_ai_deterministic",
        },
        {
            "id": "mock_repair_failing_to_passing",
            "ok": bool(mock.get("ok"))
            and mock.get("before_tests_passed") is False
            and mock.get("after_tests_passed") is True,
        },
        {"id": "failure_path", "ok": bool(fail.get("ok"))},
        {
            "id": "cancellation_path",
            "ok": bool(cancel.get("ok")) and cancel.get("file_created") is False,
        },
        {
            "id": "ai_pause_honest",
            "ok": bool(ai.get("ok"))
            and (
                ai.get("paused") is True
                or ai.get("ai_result", {}).get("fallback_used") is False
            )
            and bool(ai.get("progress", {}).get("inputs_preserved", {}).get("prompt")),
        },
        {
            "id": "external_network_disabled",
            "ok": net.get("mode") == "offline_external_blocked",
        },
    ]
    passed = sum(1 for c in checks if c["ok"])
    payload = {
        "suite": "mainframe-demos",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "network": net,
        "results": results,
        "checks": checks,
        "passed": passed,
        "failed": len(checks) - passed,
        "ok": passed == len(checks),
        "labels": {
            "deterministic_workflows": "non_ai_deterministic",
            "mock_repair": "mock_scripted_inference_real_tools",
        },
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = RUNS_DIR / f"demos-{stamp}.json"
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    payload["report_path"] = str(out.relative_to(ROOT)).replace("\\", "/")
    return payload
