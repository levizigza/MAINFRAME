"""Acceptance: mock integration separate; raw publish; prioritize largest failure."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mainframe.codingbench.catalog import holdout_ids, tune_ids, KEYS_ROOT
from mainframe.codingbench.run import run_codingbench
from mainframe.codingbench.workspace import prepare_workspace
from mainframe.codingbench.catalog import list_tasks


def run_codingbench_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    checks.append(
        {
            "id": "holdout_disjoint_from_tune",
            "ok": holdout_ids().isdisjoint(tune_ids()) and len(holdout_ids()) >= 6,
            "detail": {"holdout": sorted(holdout_ids()), "tune": sorted(tune_ids())},
        }
    )

    # Keys never copied into workspace
    task = list_tasks(split="holdout")[0]
    import tempfile

    ws = Path(tempfile.mkdtemp(prefix="mf-cb-keys-"))
    prep = prepare_workspace(task, ws)
    keys_in_ws = (ws / "keys").exists() or (KEYS_ROOT / "expectations.json").exists() and (
        ws / "expectations.json"
    ).exists()
    checks.append(
        {
            "id": "expected_outcomes_outside_workspace",
            "ok": prep.get("ok") and not keys_in_ws and (KEYS_ROOT / "expectations.json").is_file(),
            "detail": {"workspace": prep.get("workspace"), "keys_root": str(KEYS_ROOT)},
        }
    )

    report = run_codingbench(split="holdout", measurement_kind="mock_integration", publish=True)
    checks.append(
        {
            "id": "mock_integration_separate_from_live_quality",
            "ok": report.get("measurement_kind") == "mock_integration"
            and report.get("uncertainty", {}).get("mock_integration_separate") is True
            and report.get("uncertainty", {}).get("live_model_quality_measured") is False,
            "detail": report.get("uncertainty"),
        }
    )

    strong_rows = [
        r
        for r in report.get("attempts") or []
        if r.get("agent_id") == "fixture-strong" and r.get("split") == "holdout"
    ]
    strong_ok = all(r.get("success") for r in strong_rows)
    checks.append(
        {
            "id": "fixture_strong_holdout_passes",
            "ok": strong_ok and len(strong_rows) >= 12,
            "detail": {"n": len(strong_rows), "failed": [r["task_id"] for r in strong_rows if not r.get("success")]},
        }
    )

    weak_rows = [r for r in report.get("attempts") or [] if r.get("agent_id") == "fixture-weak" and r.get("split") == "holdout"]
    weak_fails = [r for r in weak_rows if not r.get("success")]
    checks.append(
        {
            "id": "fixture_weak_surfaces_failures",
            "ok": len(weak_fails) >= 4,
            "detail": {"failed_categories": sorted({r.get("category") for r in weak_fails})},
        }
    )

    published = report.get("published_path")
    pub_ok = False
    if published:
        p = Path(published)
        pub_ok = p.is_file() and json.loads(p.read_text(encoding="utf-8")).get("all_attempts_reported")
    checks.append(
        {
            "id": "raw_local_results_published",
            "ok": pub_ok,
            "detail": {"path": published, "attempts_n": len(report.get("attempts") or [])},
        }
    )

    priority = report.get("priority_fix") or {}
    failures = report.get("failure_analysis") or {}
    checks.append(
        {
            "id": "largest_failure_category_prioritized",
            "ok": (
                priority.get("largest_failure_category") == failures.get("largest_category")
                and bool(priority.get("recommendation"))
                and (
                    failures.get("largest_count", 0) == 0
                    or priority.get("priority") == "fix_largest_failure_category_first"
                )
            ),
            "detail": {"priority_fix": priority, "failure_analysis": failures},
        }
    )

    cmp = report.get("harness_comparison") or {}
    checks.append(
        {
            "id": "freeforge_minimal_harness_comparison",
            "ok": "minimal" in cmp and "freeforge" in cmp,
            "detail": cmp,
        }
    )

    metrics_ok = all(
        "latency_ms" in r and "model_calls" in r and "attempt" in r
        for r in (report.get("attempts") or [])[:5]
    )
    checks.append(
        {
            "id": "records_latency_and_model_calls",
            "ok": metrics_ok,
            "detail": "sample first attempts include latency_ms and model_calls",
        }
    )

    passed = sum(1 for c in checks if c["ok"])
    failed = len(checks) - passed
    return {
        "ok": failed == 0,
        "passed": passed,
        "failed": failed,
        "checks": checks,
        "report_path": published,
        "uncertainty": report.get("uncertainty"),
        "priority_fix": priority,
    }
