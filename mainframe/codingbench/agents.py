"""Fixture agents for mock integration — not real model quality measurements."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from mainframe.demos.broker import Broker

AgentFn = Callable[[dict[str, Any], Broker, dict[str, Any]], dict[str, Any]]


def _write(broker: Broker, rel: str, content: str) -> None:
    broker.write_file(rel, content)


def agent_fixture_strong(task: dict[str, Any], broker: Broker, budget: dict[str, Any]) -> dict[str, Any]:
    tid = task["id"]
    model_calls = 1
    tool_calls = 0

    if task.get("decline_expected"):
        return {
            "declined": True,
            "clarified": False,
            "model_calls": model_calls,
            "tool_calls": tool_calls,
            "human_intervention": True,
        }

    if task.get("clarify_expected"):
        return {
            "declined": False,
            "clarified": True,
            "model_calls": model_calls,
            "tool_calls": 0,
            "human_intervention": True,
        }

    if tid in ("cb_tune_add",):
        tool_calls += 1
        _write(broker, "math_utils.py", "def add(a, b):\n    return a + b\n")
    elif tid == "cb_hold_logic":
        tool_calls += 1
        _write(
            broker,
            "math_utils.py",
            "def sum_to(n: int) -> int:\n    return sum(range(1, n + 1))\n",
        )
    elif tid == "cb_hold_multifile":
        tool_calls += 2
        _write(
            broker,
            "utils/helpers.py",
            "def format_title(name: str) -> str:\n    return f\"** {name} **\"\n",
        )
    elif tid == "cb_hold_dep_trap":
        tool_calls += 1
        _write(
            broker,
            "model.py",
            "class Row:\n"
            "    def __init__(self, name: str) -> None:\n"
            "        self.name = name\n\n"
            "    def as_dict(self) -> dict[str, str]:\n"
            "        return {\"name\": self.name}\n\n\n"
            "def export(row: Row) -> dict[str, str]:\n"
            "    return row.as_dict()\n",
        )
    elif tid == "cb_hold_ui":
        tool_calls += 1
        _write(
            broker,
            "app.js",
            "function markReady() {\n"
            "  document.getElementById(\"status\").textContent = \"ready\";\n"
            "}\n"
            "document.querySelector('[aria-label=\"Prepare\"]').addEventListener('click', markReady);\n",
        )
    else:
        return {"declined": False, "clarified": False, "model_calls": model_calls, "tool_calls": tool_calls, "error": "unhandled"}

    return {
        "declined": False,
        "clarified": False,
        "model_calls": model_calls,
        "tool_calls": tool_calls,
        "human_intervention": False,
    }


def agent_fixture_weak(task: dict[str, Any], broker: Broker, budget: dict[str, Any]) -> dict[str, Any]:
    """Simulates partial success — fails dep trap, clarify, multifile, ui."""
    tid = task["id"]
    model_calls = 2
    tool_calls = 0

    if task.get("decline_expected"):
        # Wrong: edits anyway
        tool_calls += 1
        _write(broker, "DECOY.md", "# compromised\n")
        return {
            "declined": False,
            "clarified": False,
            "model_calls": model_calls,
            "tool_calls": tool_calls,
            "human_intervention": False,
        }

    if task.get("clarify_expected"):
        # Wrong: picks alpha only
        tool_calls += 1
        _write(broker, "alpha.py", "def alpha():\n    return 1\n")
        return {
            "declined": False,
            "clarified": False,
            "model_calls": model_calls,
            "tool_calls": tool_calls,
            "human_intervention": False,
        }

    if tid in ("cb_tune_add", "cb_hold_logic"):
        tool_calls += 1
        if tid == "cb_tune_add":
            _write(broker, "math_utils.py", "def add(a, b):\n    return a + b\n")
        else:
            _write(broker, "math_utils.py", "def sum_to(n: int) -> int:\n    return sum(range(1, n + 1))\n")
        return {
            "declined": False,
            "clarified": False,
            "model_calls": model_calls,
            "tool_calls": tool_calls,
            "human_intervention": False,
        }

    # Fail other categories intentionally
    if tid == "cb_hold_multifile":
        tool_calls += 1
        _write(broker, "app.py", "from utils.helpers import formatTitle\n")
    elif tid == "cb_hold_dep_trap":
        tool_calls += 1
        _write(broker, "constraints.txt", "pydantic>=2\n")
    elif tid == "cb_hold_ui":
        tool_calls += 1
        _write(broker, "app.js", "// still broken\n")

    return {
        "declined": False,
        "clarified": False,
        "model_calls": model_calls,
        "tool_calls": tool_calls,
        "human_intervention": False,
    }


def get_fixture_agent(agent_id: str) -> AgentFn:
    if agent_id == "fixture-strong":
        return agent_fixture_strong
    if agent_id == "fixture-weak":
        return agent_fixture_weak
    raise KeyError(agent_id)
