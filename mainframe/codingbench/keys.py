"""Expected outcomes — never copied into agent workspaces."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mainframe.codingbench.catalog import KEYS_ROOT


def load_expectations() -> dict[str, Any]:
    path = KEYS_ROOT / "expectations.json"
    return json.loads(path.read_text(encoding="utf-8"))


def expectation_for(task_id: str) -> dict[str, Any]:
    data = load_expectations()
    tasks = data.get("tasks") or {}
    if task_id not in tasks:
        raise KeyError(f"no expectation for task {task_id}")
    return dict(tasks[task_id])
