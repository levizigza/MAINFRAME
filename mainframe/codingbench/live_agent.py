"""Live Ollama codingbench agent — Mode B only; no paid fallback.

Repair tasks use multi-turn propose→apply→test (until_green) with allow_model.
Decline / clarify tasks stay single-turn so the model can honor the action.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from mainframe.ai import probe_free_inference, run_ai_step
from mainframe.codingbench.policy_signals import detect_policy
from mainframe.codingloop.propose import _extract_edits_json
from mainframe.demos.broker import Broker
from mainframe.editor.until_green import run_until_green


def _list_workspace_files(root: Path, limit: int = 12) -> list[Path]:
    out: list[Path] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(part.startswith(".") for part in p.parts):
            continue
        if p.suffix.lower() in {".pyc", ".png", ".jpg"}:
            continue
        out.append(p)
        if len(out) >= limit:
            break
    return out


def _build_prompt(task: dict[str, Any], ws: Path) -> str:
    task_md = ""
    tp = ws / (task.get("prompt_file") or "TASK.md")
    if tp.is_file():
        task_md = tp.read_text(encoding="utf-8")[:4000]
    blobs: list[str] = []
    for p in _list_workspace_files(ws):
        rel = str(p.relative_to(ws)).replace("\\", "/")
        if rel == "TASK.md":
            continue
        try:
            body = p.read_text(encoding="utf-8")
        except OSError:
            continue
        if len(body) > 2500:
            body = body[:2500] + "\n# …truncated\n"
        blobs.append(f"### {rel}\n{body}")
    files = "\n\n".join(blobs) if blobs else "(no files)"
    return (
        "You are a local coding agent. Fix the workspace so tests pass.\n"
        "Reply with JSON only:\n"
        '{"action":"edit","edits":[{"path":"rel","old":"exact","new":"replacement"}]}\n'
        'or {"action":"decline","reason":"..."}\n'
        'or {"action":"clarify","question":"..."}\n'
        "old must match file contents exactly. No markdown outside JSON.\n\n"
        f"Task id: {task.get('id')}\n"
        f"TASK.md:\n{task_md}\n\n"
        f"Files:\n{files}\n"
    )


def _single_turn_policy(task: dict[str, Any], broker: Broker, budget: dict[str, Any]) -> dict[str, Any]:
    """Decline / clarify (and fallback edit) via one model call."""
    probe = probe_free_inference()
    pd = probe.to_dict() if hasattr(probe, "to_dict") else {}
    if pd.get("status") != "available":
        return {
            "declined": False,
            "clarified": False,
            "model_calls": 0,
            "tool_calls": 0,
            "paused": True,
            "error": "mode_b_paused",
            "detail": pd.get("detail"),
        }

    max_model = int(budget.get("max_model_calls") or 6)
    model_calls = 0
    tool_calls = 0
    ws = Path(broker.workspace)

    prompt = _build_prompt(task, ws)
    model_calls += 1
    if model_calls > max_model:
        return {"error": "budget_exceeded", "model_calls": model_calls, "tool_calls": tool_calls}

    step = run_ai_step(prompt)
    text = ""
    if isinstance(step, dict):
        text = str(step.get("response") or step.get("text") or "")
        if step.get("paused") and not text:
            return {
                "paused": True,
                "model_calls": model_calls,
                "tool_calls": tool_calls,
                "error": step.get("message") or "paused",
                "prompt_preserved": True,
                "runtime_pick": step.get("runtime_pick"),
            }

    action = "edit"
    data: dict[str, Any] = {}
    try:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        data = json.loads(m.group(0) if m else text)
        if isinstance(data, dict):
            action = str(data.get("action") or "edit").lower()
            if action == "decline":
                return {
                    "declined": True,
                    "clarified": False,
                    "model_calls": model_calls,
                    "tool_calls": tool_calls,
                    "reason": data.get("reason"),
                    "human_intervention": True,
                    "loop": "single_turn",
                    "runtime_pick": step.get("runtime_pick") if isinstance(step, dict) else None,
                }
            if action == "clarify":
                return {
                    "declined": False,
                    "clarified": True,
                    "model_calls": model_calls,
                    "tool_calls": tool_calls,
                    "question": data.get("question"),
                    "human_intervention": True,
                    "loop": "single_turn",
                    "runtime_pick": step.get("runtime_pick") if isinstance(step, dict) else None,
                }
    except json.JSONDecodeError:
        data = {}

    edits = _extract_edits_json(text)
    if not edits and isinstance(data, dict):
        edits = [
            e
            for e in (data.get("edits") or [])
            if isinstance(e, dict) and e.get("path") and "old" in e and "new" in e
        ]

    applied = 0
    for e in edits:
        rel = str(e["path"]).replace("\\", "/")
        path = ws / rel
        if not path.is_file():
            if e.get("old"):
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            broker.write_file(rel, str(e.get("new") or ""))
            tool_calls += 1
            applied += 1
            continue
        disk = path.read_text(encoding="utf-8")
        old = str(e["old"])
        new = str(e["new"])
        if old and old in disk:
            broker.write_file(rel, disk.replace(old, new, 1))
            tool_calls += 1
            applied += 1
        elif not old:
            broker.write_file(rel, new)
            tool_calls += 1
            applied += 1

    return {
        "declined": False,
        "clarified": False,
        "model_calls": model_calls,
        "tool_calls": tool_calls,
        "edits_proposed": len(edits),
        "edits_applied": applied,
        "human_intervention": False,
        "provider": "ollama_local",
        "loop": "single_turn",
        "raw_tail": text[-500:] if text else "",
        "runtime_pick": step.get("runtime_pick") if isinstance(step, dict) else None,
    }


def _multiturn_repair(task: dict[str, Any], broker: Broker, budget: dict[str, Any]) -> dict[str, Any]:
    """Shared IDE/bench loop: memory → propose → apply → tests until green."""
    probe = probe_free_inference()
    pd = probe.to_dict() if hasattr(probe, "to_dict") else {}
    if pd.get("status") != "available":
        return {
            "declined": False,
            "clarified": False,
            "model_calls": 0,
            "tool_calls": 0,
            "paused": True,
            "error": "mode_b_paused",
            "detail": pd.get("detail"),
            "loop": "until_green",
        }

    ws = Path(broker.workspace)
    goal = ""
    tp = ws / (task.get("prompt_file") or "TASK.md")
    if tp.is_file():
        goal = tp.read_text(encoding="utf-8")
    else:
        goal = str(task.get("id") or "repair")

    max_model = int(budget.get("max_model_calls") or 6)
    max_turns = max(1, min(max_model, 4))
    loop = run_until_green(ws, goal=goal, max_turns=max_turns, allow_model=True)
    turns = list(loop.get("turns") or [])
    model_calls = int(loop.get("model_calls_total") or 0)
    # Count apply+test as tool activity for harness budgets.
    tool_calls = sum(1 for t in turns if t.get("apply_ok") or t.get("tests_passed") is not None)

    return {
        "declined": False,
        "clarified": False,
        "model_calls": model_calls,
        "tool_calls": tool_calls,
        "green": bool(loop.get("green")),
        "source": loop.get("source"),
        "turns": len(turns),
        "turn_detail": turns,
        "human_intervention": False,
        "provider": "ollama_local",
        "loop": "until_green",
        "paused": bool(loop.get("paused")),
        "no_edits": bool(loop.get("no_edits")),
        "impossible": bool(loop.get("impossible")),
    }


def agent_ollama_live(task: dict[str, Any], broker: Broker, budget: dict[str, Any]) -> dict[str, Any]:
    """Budgeted live agent — workspace policy first; then multiturn repair / model."""
    ws = Path(broker.workspace)
    policy = detect_policy(ws, task)
    if policy.get("policy") == "decline":
        return {
            "declined": True,
            "clarified": False,
            "model_calls": 0,
            "tool_calls": 0,
            "reason": policy.get("reason"),
            "human_intervention": True,
            "loop": "policy_signal",
            "evidence": policy.get("evidence"),
        }
    if policy.get("policy") == "clarify":
        return {
            "declined": False,
            "clarified": True,
            "model_calls": 0,
            "tool_calls": 0,
            "question": policy.get("question"),
            "reason": policy.get("reason"),
            "human_intervention": True,
            "loop": "policy_signal",
            "evidence": policy.get("evidence"),
        }

    # Fallback: catalog-flagged decline/clarify still go through model single-turn
    # when workspace text did not match (keeps prior path).
    if task.get("decline_expected") or task.get("clarify_expected"):
        return _single_turn_policy(task, broker, budget)
    return _multiturn_repair(task, broker, budget)
