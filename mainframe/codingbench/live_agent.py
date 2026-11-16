"""Live Ollama codingbench agent — Mode B only; no paid fallback."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from mainframe.ai import probe_free_inference, run_ai_step
from mainframe.codingloop.propose import _extract_edits_json
from mainframe.demos.broker import Broker


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


def agent_ollama_live(task: dict[str, Any], broker: Broker, budget: dict[str, Any]) -> dict[str, Any]:
    """Single-turn (budgeted) live propose via eligible Ollama."""
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

    # Decline / clarify tasks: ask model once, honor action
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
            }

    # Parse action
    action = "edit"
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
                }
            if action == "clarify":
                return {
                    "declined": False,
                    "clarified": True,
                    "model_calls": model_calls,
                    "tool_calls": tool_calls,
                    "question": data.get("question"),
                    "human_intervention": True,
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
            # allow create if old empty
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
        "raw_tail": text[-500:] if text else "",
    }
