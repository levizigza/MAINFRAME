"""Scoring helpers for eval tasks."""

from __future__ import annotations

import json
import re
from typing import Any


def _extract_json(text: str) -> dict[str, Any] | list[Any] | None:
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def score_task(task: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    """Return correctness and invalid_tool_calls for one response."""
    expect = task.get("expect") or {}
    cls = task.get("class")
    text = str(response.get("text") or "")
    tool = response.get("tool")
    invalid_tools = int(response.get("invalid_tool_calls") or 0)
    retries = int(response.get("retries") or 0)

    correct = False
    detail: dict[str, Any] = {}

    if cls == "code_repair":
        if "contains" in expect:
            correct = all(s in text for s in expect["contains"])
            detail["contains_ok"] = correct
        if "sum_to_5" in expect:
            # Execute repaired snippet if present
            try:
                ns: dict[str, Any] = {}
                exec(compile(text, "<repair>", "exec"), ns, ns)
                correct = ns.get("sum_to", lambda n: None)(5) == expect["sum_to_5"]
                detail["sum_to_5"] = correct
            except Exception as exc:  # noqa: BLE001
                correct = False
                detail["exec_error"] = f"{type(exc).__name__}: {exc}"
    elif cls == "tool_selection":
        correct = tool == expect.get("tool")
        if tool and tool not in (task.get("tools") or []):
            invalid_tools += 1
            correct = False
        detail["expected_tool"] = expect.get("tool")
        detail["got_tool"] = tool
    elif cls == "structured_extraction":
        obj = _extract_json(text) or {}
        if isinstance(obj, dict):
            correct = all(str(obj.get(k)) == str(v) for k, v in expect.items())
            detail["parsed"] = obj
        else:
            correct = False
    elif cls == "planning":
        obj = _extract_json(text)
        if isinstance(obj, dict) and "steps_include" in expect:
            steps = [str(s).lower() for s in (obj.get("steps") or [])]
            correct = all(any(req in s for s in steps) for req in expect["steps_include"])
            detail["steps"] = steps
        elif isinstance(obj, dict) and "order" in expect:
            steps = [str(s).lower() for s in (obj.get("steps") or obj.get("order") or [])]
            want = [str(s).lower() for s in expect["order"]]
            correct = steps[: len(want)] == want
            detail["steps"] = steps
        else:
            correct = False
    elif cls == "vision":
        if response.get("vision_unsupported"):
            correct = False
            detail["status"] = "vision_unavailable"
        else:
            correct = bool(response.get("vision_ok"))
            detail["vision_ok"] = correct
    else:
        detail["error"] = f"unknown_class:{cls}"

    return {
        "correct": bool(correct),
        "invalid_tool_calls": invalid_tools,
        "retries": retries,
        "detail": detail,
    }
