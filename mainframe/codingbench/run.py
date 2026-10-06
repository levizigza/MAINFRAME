"""Run coding benchmark — mock integration vs optional live model path."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from mainframe.codingbench.agents import get_fixture_agent
from mainframe.codingbench.catalog import holdout_ids, list_tasks, tune_ids
from mainframe.codingbench.harness import run_harness
from mainframe.codingbench.report import build_report, publish_report
from mainframe.modeleval.runners import discover_eligible_models


def _mark_regressions(rows: list[dict[str, Any]]) -> None:
    tune_ok = {
        (r["harness_id"], r["agent_id"], r["task_id"])
        for r in rows
        if r.get("split") == "tune" and r.get("success")
    }
    for r in rows:
        if r.get("split") != "holdout":
            continue
        key = (r["harness_id"], r["agent_id"], r["task_id"])
        if key in tune_ok and not r.get("success"):
            r["regression"] = True


def run_codingbench(
    *,
    split: str | None = "holdout",
    measurement_kind: str = "mock_integration",
    include_compare: bool = True,
    publish: bool = True,
) -> dict[str, Any]:
    tasks = list_tasks(split=split)
    if measurement_kind == "mock_integration":
        agents = [("fixture-strong", get_fixture_agent("fixture-strong"))]
        if include_compare:
            agents.append(("fixture-weak", get_fixture_agent("fixture-weak")))
    else:
        # Live path: no automatic model execution — report unavailable attempts only.
        eligible = [m for m in discover_eligible_models() if m.provider_id == "ollama_local" and m.available]
        if not eligible:
            report = build_report(
                measurement_kind="live_model_quality",
                rows=[],
                models=[],
            )
            report["uncertainty"]["notes"] = "No eligible available live model; quality unmeasured."
            if publish:
                publish_report(report)
            return report
        agents = []  # reserved — caller must not claim quality without harness wiring

    work = Path(tempfile.mkdtemp(prefix="mf-codingbench-"))
    rows: list[dict[str, Any]] = []
    for agent_id, agent_fn in agents:
        for harness_id in ("minimal", "freeforge"):
            rows.extend(
                run_harness(
                    tasks,
                    agent_fn,
                    harness_id=harness_id,
                    agent_id=agent_id,
                    model_provider="fixture_local",
                    work_dir=work,
                )
            )
    _mark_regressions(rows)
    models = [{"agent_id": a, "provider": "fixture_local"} for a, _ in agents]
    report = build_report(measurement_kind=measurement_kind, rows=rows, models=models)
    report["catalog"] = {
        "holdout_ids": sorted(holdout_ids()),
        "tune_ids": sorted(tune_ids()),
        "disjoint": holdout_ids().isdisjoint(tune_ids()),
    }
    if publish:
        publish_report(report)
    return report
