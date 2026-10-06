"""Select initial mode from task shape — not model confidence."""

from __future__ import annotations

import re
from typing import Any

from mainframe.controller.types import Mode

# Known deterministic operations (no model / no planning ceremony).
KNOWN_DETERMINISTIC = frozenset(
    {
        "echo",
        "list-tree",
        "workspace-checksum",
        "write-run-report",
        "status",
        "checksum",
    }
)

_HIGH_IMPACT = re.compile(
    r"\b(migrat\w*|delet\w*\s+prod|drop\s+table|auth|security|permission|"
    r"public\s+api|breaking\s+change|schema\s+change|payment|credential)\b",
    re.I,
)
_AMBIGUOUS = re.compile(
    r"\b(maybe|somehow|improve|cleanup|make\s+it\s+better|refactor\s+everything|"
    r"fix\s+if\s+needed|as\s+appropriate|whatever\s+works)\b",
    re.I,
)
_BOUNDED = re.compile(
    r"\b(rename|add\s+type\s+hint|fix\s+typo|extract\s+json|one\s+function|"
    r"single\s+file|bounded)\b",
    re.I,
)
_CONFLICT = re.compile(
    r"\b(both\s+must|mutually\s+exclusive|conflict|contradict|cannot\s+and\s+must)\b",
    re.I,
)


def classify_mode(task: dict[str, Any]) -> dict[str, Any]:
    """
    Return initial mode + observable signals.
    Confidence scores are never the sole escalator.
    """
    kind = str(task.get("kind") or "").strip().lower()
    text = str(task.get("goal") or task.get("prompt") or "")
    known_op = str(task.get("deterministic_op") or kind)
    impact = str(task.get("impact") or "normal").lower()
    signals: list[str] = []

    if known_op in KNOWN_DETERMINISTIC or task.get("force_deterministic"):
        signals.append(f"known_deterministic_op:{known_op}")
        return {
            "mode": "deterministic_tools",
            "signals": signals,
            "ceremony_expected": [],
            "reason": "Known deterministic operation — skip agent planning/review.",
        }

    if task.get("conflicting_requirements") or _CONFLICT.search(text):
        signals.append("conflicting_requirements")
        return {
            "mode": "plan_review",
            "signals": signals,
            "ceremony_expected": ["plan", "review"],
            "reason": "Conflicting requirements observed — plan and review required.",
        }

    if impact in {"high", "critical"} or _HIGH_IMPACT.search(text):
        signals.append("high_impact")
        return {
            "mode": "plan_review",
            "signals": signals,
            "ceremony_expected": ["plan", "review"],
            "reason": "High-impact change — extra planning/review before edits.",
        }

    if _AMBIGUOUS.search(text) or task.get("ambiguous"):
        signals.append("ambiguous_goal")
        return {
            "mode": "plan_review",
            "signals": signals,
            "ceremony_expected": ["plan", "review"],
            "reason": "Ambiguous goal — plan before execution.",
        }

    if _BOUNDED.search(text) or task.get("bounded"):
        signals.append("bounded_task")
        return {
            "mode": "direct_model",
            "signals": signals,
            "ceremony_expected": ["direct_execute"],
            "reason": "Bounded task — direct execution without full agent loop.",
        }

    # Default: bounded direct unless marked difficult fixture
    if task.get("difficult"):
        signals.append("difficult_fixture")
        return {
            "mode": "plan_review",
            "signals": signals,
            "ceremony_expected": ["plan", "review", "targeted_analysis"],
            "reason": "Difficult fixture — targeted additional analysis.",
        }

    signals.append("default_bounded")
    return {
        "mode": "direct_model",
        "signals": signals,
        "ceremony_expected": ["direct_execute"],
        "reason": "Default bounded path — no unnecessary ceremonies.",
    }


def mode_name(raw: dict[str, Any]) -> Mode:
    m = raw.get("mode") or "direct_model"
    if m not in {"deterministic_tools", "direct_model", "plan_review"}:
        return "direct_model"
    return m  # type: ignore[return-value]
