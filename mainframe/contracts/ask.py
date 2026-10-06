"""Ask vs assume — only ask when missing info changes correctness or authorization."""

from __future__ import annotations

import re
from typing import Any

from mainframe.contracts.types import RequestKind

# Vague phrases that need a focused question for correctness
VAGUE_RE = re.compile(
    r"(?i)\b(make\s+it\s+better|improve\s+(?:it|this|things)|fix\s+(?:stuff|things)|"
    r"do\s+something|handle\s+it|clean\s+(?:it\s+)?up\s*$|optimize\s+(?:it|this)?|"
    r"update\s+the\s+code|refactor\s+(?:it|this)\s*$)\b"
)

# Authorization-sensitive — ask before proceeding
AUTHZ_RE = re.compile(
    r"(?i)\b(delete\s+all|drop\s+(?:table|database)|force\s+push|rm\s+-rf|"
    r"production|prod\s+deploy|exfiltrat|credential|secret\s+key|wipe)\b"
)


def decide_questions_and_assumptions(
    text: str,
    *,
    kind: RequestKind,
    workflow_id: str | None,
    classification: dict[str, Any],
) -> dict[str, Any]:
    """
    Return unresolved_questions (max focused), assumptions, and whether to block.

    Ask only when missing information changes correctness or authorization.
    Otherwise record a reasonable assumption and continue.
    """
    questions: list[dict[str, Any]] = []
    assumptions: list[dict[str, Any]] = []

    if workflow_id:
        # Routine known workflow — start without clarification
        assumptions.append(
            {
                "id": "known_workflow",
                "text": f"Matched known workflow '{workflow_id}'; proceeding with its schema defaults.",
                "reason": "repeated_workflow_start_without_clarification",
            }
        )
        return {
            "unresolved_questions": [],
            "assumptions": assumptions,
            "status": "ready",
            "ask_count": 0,
        }

    if AUTHZ_RE.search(text):
        questions.append(
            {
                "id": "authorization_confirm",
                "text": "This request may require elevated authorization. Which exact target and approval scope should apply?",
                "changes": "authorization",
                "focused": True,
            }
        )
        return {
            "unresolved_questions": questions[:1],
            "assumptions": assumptions,
            "status": "needs_clarification",
            "ask_count": 1,
        }

    # Ambiguous / vague without actionable noun
    vague = bool(VAGUE_RE.search(text)) or (
        kind == "unknown" and len(text.split()) < 8
    )
    # "refactor it" without target
    refactor_no_target = kind == "refactor" and not re.search(
        r"(?i)\b(module|file|class|function|package|api|interface|[\w./\\]+\.py)\b",
        text,
    )
    feature_no_what = kind == "feature" and not re.search(
        r"(?i)\b(add|implement|create)\s+\w+",
        text,
    ) and vague

    if vague or refactor_no_target or feature_no_what or (
        classification.get("kind") == "unknown" and vague
    ):
        q = _one_focused_question(kind, text)
        questions.append(q)
        return {
            "unresolved_questions": questions[:1],  # exactly one focused question
            "assumptions": assumptions,
            "status": "needs_clarification",
            "ask_count": 1,
        }

    # Sufficient info — record assumptions and continue
    if kind == "refactor":
        assumptions.append(
            {
                "id": "preserve_public_interface",
                "text": "Public function/class names and signatures in scope remain unchanged unless the request names a rename.",
                "reason": "correctness_default_for_refactor",
            }
        )
    elif kind == "repair":
        assumptions.append(
            {
                "id": "minimal_fix",
                "text": "Change only what is required to fix the stated failure; no opportunistic refactors.",
                "reason": "correctness_default_for_repair",
            }
        )
    elif kind == "explanation":
        assumptions.append(
            {
                "id": "read_only",
                "text": "Explanation is read-only; no code edits.",
                "reason": "side_effect_default",
            }
        )
    else:
        assumptions.append(
            {
                "id": "local_free_only",
                "text": "Work stays local and free-only; no paid or hosted services.",
                "reason": "authorization_default",
            }
        )

    return {
        "unresolved_questions": [],
        "assumptions": assumptions,
        "status": "ready",
        "ask_count": 0,
    }


def _one_focused_question(kind: RequestKind, text: str) -> dict[str, Any]:
    if kind == "refactor":
        return {
            "id": "refactor_target",
            "text": "Which module or interface should the refactor target, and which public names must stay stable?",
            "changes": "correctness",
            "focused": True,
        }
    if kind == "repair":
        return {
            "id": "failure_signal",
            "text": "What is the failing test, error message, or observed incorrect behavior to fix?",
            "changes": "correctness",
            "focused": True,
        }
    if kind == "ui":
        return {
            "id": "ui_surface",
            "text": "Which screen or component should change, and what is the intended visual/behavioral outcome?",
            "changes": "correctness",
            "focused": True,
        }
    if kind == "feature":
        return {
            "id": "feature_outcome",
            "text": "What user-visible outcome should exist when the feature is done?",
            "changes": "correctness",
            "focused": True,
        }
    return {
        "id": "concrete_goal",
        "text": "What concrete outcome should be true when this task is done?",
        "changes": "correctness",
        "focused": True,
    }
