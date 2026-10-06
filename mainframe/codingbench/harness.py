"""Minimal vs FreeForge harness — same task inputs, tools, budgets."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.codingbench.agents import AgentFn
from mainframe.codingbench.catalog import budget_defaults
from mainframe.codingbench.verify import snapshot_protected, verify_task
from mainframe.codingbench.workspace import prepare_workspace
from mainframe.demos.broker import Broker
from mainframe.freeforge import load_pins, run_spike


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class HarnessConfig:
    harness_id: str  # minimal | freeforge
    agent_id: str
    model_provider: str
    max_tool_calls: int
    max_model_calls: int
    timeout_s: float


def _freeforge_preflight() -> dict[str, Any]:
    pins = load_pins()
    spike = run_spike()
    return {
        "pins_version": pins.get("version"),
        "selected_engine": spike.selected_engine,
        "nested_loops_allowed": spike.nested_loops_allowed,
        "playwright_probe": spike.playwright_probe,
    }


def run_task_attempt(
    task: dict[str, Any],
    workspace_root: Path,
    agent: AgentFn,
    cfg: HarnessConfig,
) -> dict[str, Any]:
    started = _utc()
    t0 = time.perf_counter()
    ws = workspace_root / task["id"]
    prep = prepare_workspace(task, ws)
    if not prep.get("ok"):
        return {
            "task_id": task["id"],
            "harness_id": cfg.harness_id,
            "status": "error",
            "error": prep.get("error"),
            "started_at": started,
        }

    preflight: dict[str, Any] = {}
    if cfg.harness_id == "freeforge":
        preflight = _freeforge_preflight()

    broker = Broker(ws)
    protected = snapshot_protected(ws, task["id"])
    budget = {
        "max_tool_calls": cfg.max_tool_calls,
        "max_model_calls": cfg.max_model_calls,
        "timeout_s": cfg.timeout_s,
    }

    timed_out = False
    unavailable_provider = False
    try:
        agent_out = agent(task, broker, budget)
    except Exception as exc:  # noqa: BLE001
        agent_out = {"error": str(exc), "model_calls": 0, "tool_calls": 0}

    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)
    if elapsed_ms > cfg.timeout_s * 1000:
        timed_out = True

    if cfg.model_provider not in ("fixture_local", "ollama_local", "llamacpp_local"):
        unavailable_provider = True

    model_calls = int(agent_out.get("model_calls") or 0)
    tool_calls = int(agent_out.get("tool_calls") or 0)
    if model_calls > cfg.max_model_calls or tool_calls > cfg.max_tool_calls:
        timed_out = True

    agent_meta = {
        **agent_out,
        "protected_snapshots": protected,
    }
    verified = verify_task(task["id"], ws, agent_meta=agent_meta)
    success = bool(verified.get("ok")) and not timed_out and not unavailable_provider

    human_intervention = bool(agent_out.get("human_intervention"))
    return {
        "task_id": task["id"],
        "category": task.get("category"),
        "split": task.get("split"),
        "harness_id": cfg.harness_id,
        "agent_id": cfg.agent_id,
        "model_provider": cfg.model_provider,
        "started_at": started,
        "latency_ms": elapsed_ms,
        "success": success,
        "regression": False,
        "human_intervention": human_intervention,
        "model_calls": model_calls,
        "model_calls_per_success": model_calls if success else None,
        "tool_calls": tool_calls,
        "timed_out": timed_out,
        "unavailable_provider": unavailable_provider,
        "verify": verified,
        "agent": {k: agent_out.get(k) for k in ("declined", "clarified", "error")},
        "freeforge_preflight": preflight or None,
        "workspace_digest": prep.get("workspace_digest"),
        "attempt": 1,
    }


def run_harness(
    tasks: list[dict[str, Any]],
    agent: AgentFn,
    *,
    harness_id: str,
    agent_id: str,
    model_provider: str = "fixture_local",
    work_dir: Path,
) -> list[dict[str, Any]]:
    defaults = budget_defaults()
    cfg = HarnessConfig(
        harness_id=harness_id,
        agent_id=agent_id,
        model_provider=model_provider,
        max_tool_calls=int(defaults.get("max_tool_calls") or 24),
        max_model_calls=int(defaults.get("max_model_calls") or 6),
        timeout_s=float(defaults.get("timeout_s") or 120),
    )
    return [run_task_attempt(task, work_dir, agent, cfg) for task in tasks]
