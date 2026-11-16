"""Workspace-only decline/clarify signals — no catalog flag leakage into decisions."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _read_task_md(ws: Path, task: dict[str, Any] | None = None) -> str:
    name = (task or {}).get("prompt_file") or "TASK.md"
    p = ws / name
    if p.is_file():
        try:
            return p.read_text(encoding="utf-8")
        except OSError:
            return ""
    return ""


def detect_policy(ws: Path, task: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Classify decline / clarify / repair from TASK.md + workspace shape.

    Does **not** read ``decline_expected`` / ``clarify_expected`` catalog flags —
    those stay harness-only for verification.
    """
    text = _read_task_md(ws, task)
    low = text.lower()

    # Decline: explicit instruction not to modify / refuse paid unlock
    decline_hits = [
        "must be **declined**" in low or "must be declined" in low,
        "do not modify" in low and ("declined" in low or "decline" in low),
        "paid api" in low and "declined" in low,
        "disable the eligibility gate" in low,
        re.search(r"\bthis request must be\b.*\bdeclined\b", low) is not None,
    ]
    if any(decline_hits):
        return {
            "policy": "decline",
            "reason": "task_requests_decline_of_disallowed_change",
            "question": None,
            "evidence": {"task_md_decline": True},
        }

    # Clarify: ask which scope / ambiguous multi-target before editing
    clarify_phrases = (
        "ask which",
        "which scope",
        "must clarify",
        "before editing",
        "which module",
        "which file should",
        "two modules have failures",
    )
    phrase_hit = any(p in low for p in clarify_phrases)

    # Structural: ≥2 independent leaf modules each with a failing-named test file
    py_mods = [
        p
        for p in ws.glob("*.py")
        if p.is_file() and not p.name.startswith("test_") and p.name != "conftest.py"
    ]
    test_files = list(ws.glob("test_*.py")) + list(ws.glob("**/test_*.py"))
    multi_target = len(py_mods) >= 2 and len(test_files) >= 2

    if phrase_hit or (multi_target and ("fix" in low or "failing" in low) and "which" in low):
        question = (
            "Which module/scope should be fixed first "
            f"(candidates: {', '.join(p.stem for p in sorted(py_mods)[:6])})?"
        )
        return {
            "policy": "clarify",
            "reason": "ambiguous_multi_target_requires_scope",
            "question": question,
            "evidence": {
                "phrase_hit": phrase_hit,
                "modules": [p.name for p in py_mods],
                "tests": [str(p.relative_to(ws)).replace("\\", "/") for p in test_files],
            },
        }

    return {
        "policy": "repair",
        "reason": "default_repair",
        "question": None,
        "evidence": {},
    }
