"""Acceptance demos: one verified coding task + one reusable automation."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from mainframe.codingbench.agents import get_fixture_agent
from mainframe.codingbench.catalog import budget_defaults, list_tasks
from mainframe.codingbench.harness import HarnessConfig, run_task_attempt
from mainframe.workload_eval.features import FeatureFlags
from mainframe.workload_eval.runners import run_w1
from mainframe.workflows.load import load_fixture, materialize_fixture
from mainframe.workflows.runner import run_workflow


def demo_coding_task() -> dict[str, Any]:
    """
    Verified coding task under strict contract (deterministic FreeForge harness).
    Uses held-out repository repair (W1) with the measured working feature set.

    Note: per-feature ablations can each tie full rate while the joint
    all-disabled combination fails (review compensates for missing retrieval).
    Recommended flags keep retrieval on for repair correctness without relying
    on review recovery.
    """
    flags = FeatureFlags(
        retrieval=True,
        workflow_reuse=False,  # ablation: no measured gain alone
        review=False,  # ablation: no measured gain alone when retrieval present
        caching=False,  # ablation: no measured gain alone
    )
    result = run_w1(system="freeforge", flags=flags, trial=0)
    ok = bool(result.get("correct"))
    # Fallback: full flags if simplified set unexpectedly fails
    used = "recommended_simplified"
    if not ok:
        result = run_w1(system="freeforge", flags=FeatureFlags(), trial=1)
        ok = bool(result.get("correct"))
        used = "full_fallback"
    return {
        "ok": ok,
        "kind": "coding_task",
        "task": "heldout_repository_repair_w1",
        "harness": "freeforge",
        "feature_flags_used": used,
        "model_calls": result.get("model_calls", 0),
        "correct": ok,
        "elapsed_s": result.get("elapsed_s"),
        "contract": "deterministic_offline — no paid/hosted inference",
        "blocker": None if ok else "w1_verify_failed",
        "detail": {
            k: result.get(k)
            for k in ("correct", "elapsed_s", "retries", "model_calls", "failure_recoveries")
        },
        "flags": (result.get("detail") or {}).get("flags"),
    }


def demo_codingbench_logic() -> dict[str, Any]:
    """Secondary coding proof: holdout logic task via FreeForge + fixture-strong."""
    tasks = [t for t in list_tasks(split="holdout") if t.get("id") == "cb_hold_logic"]
    if not tasks:
        return {"ok": False, "blocker": "cb_hold_logic_missing"}
    task = tasks[0]
    budgets = budget_defaults()
    cfg = HarnessConfig(
        harness_id="freeforge",
        agent_id="fixture-strong",
        model_provider="fixture_local",
        max_tool_calls=int(budgets.get("max_tool_calls") or 40),
        max_model_calls=int(budgets.get("max_model_calls") or 8),
        timeout_s=float(budgets.get("timeout_s") or 120),
    )
    work = Path(tempfile.mkdtemp(prefix="mf-rec-code-"))
    agent = get_fixture_agent("fixture-strong")
    attempt = run_task_attempt(task, work, agent, cfg)
    ok = bool(attempt.get("success"))
    return {
        "ok": ok,
        "kind": "coding_task_codingbench",
        "task_id": task.get("id"),
        "harness_id": "freeforge",
        "success": ok,
        "contract": "mock_integration_fixture_strong",
        "blocker": None if ok else attempt.get("error") or "verify_failed",
        "detail": {
            "success": attempt.get("success"),
            "status": attempt.get("status"),
            "model_calls": attempt.get("model_calls"),
        },
    }


def demo_reusable_automation() -> dict[str, Any]:
    """Reusable offline workflow: input_to_report fixture."""
    raw = load_fixture("input_to_report")
    work = Path(tempfile.mkdtemp(prefix="mf-rec-wf-"))
    materialize_fixture("input_to_report", work)
    out = run_workflow(
        raw,
        inputs={"title": "recommend-automation"},
        work_dir=work,
    )
    ok = bool(out.get("ok"))
    return {
        "ok": ok,
        "kind": "reusable_automation",
        "workflow_id": raw.get("id"),
        "fixture": "input_to_report",
        "contract": "deterministic_offline",
        "blocker": None if ok else (out.get("error") or "workflow_failed"),
        "outputs": out.get("outputs"),
        "state": out.get("state"),
    }
