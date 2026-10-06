"""Deterministic request classification — no model required."""

from __future__ import annotations

import re
from typing import Any

from mainframe.contracts.types import RequestKind

# Ordered: first strong match wins (more specific before generic).
KIND_PATTERNS: list[tuple[RequestKind, re.Pattern[str], float]] = [
    (
        "refactor",
        re.compile(
            r"\b(refactor|restructure|rename|extract\s+(?:method|function|class)|"
            r"clean\s*up\s+code|reorganiz)\w*\b",
            re.I,
        ),
        0.9,
    ),
    (
        "repair",
        re.compile(
            r"\b(fix|bug|broken|error|failing|regression|crash|repair|hotfix)\w*\b",
            re.I,
        ),
        0.88,
    ),
    (
        "ui",
        re.compile(
            r"\b(ui|ux|css|layout|button|page|frontend|stylesheet|responsive|"
            r"dark\s*mode|navbar)\w*\b",
            re.I,
        ),
        0.85,
    ),
    (
        "automation",
        re.compile(
            r"\b(automat(?:e|ion)|script|cron|schedul|pipeline|workflow|"
            r"batch\s+job|cli\s+task)\w*\b",
            re.I,
        ),
        0.85,
    ),
    (
        "explanation",
        re.compile(
            r"\b(explain|what\s+does|how\s+does|why\s+(?:is|does)|document|"
            r"walk\s*me\s+through|describe)\b",
            re.I,
        ),
        0.8,
    ),
    (
        "feature",
        re.compile(
            r"\b(add|implement|create|new\s+feature|support|enable|introduce)\b",
            re.I,
        ),
        0.7,
    ),
]


def classify_request(text: str) -> dict[str, Any]:
    """Return kind + confidence + signals. Deterministic only."""
    t = text.strip()
    hits: list[dict[str, Any]] = []
    for kind, pat, weight in KIND_PATTERNS:
        m = pat.search(t)
        if m:
            hits.append({"kind": kind, "weight": weight, "match": m.group(0)})
    if not hits:
        return {
            "kind": "unknown",
            "confidence": 0.0,
            "method": "deterministic",
            "signals": [],
            "model_used": False,
        }
    hits.sort(key=lambda h: -h["weight"])
    best = hits[0]
    # Ambiguous if top two within 0.05 and different kinds
    ambiguous = len(hits) > 1 and abs(hits[0]["weight"] - hits[1]["weight"]) < 0.05
    return {
        "kind": best["kind"],
        "confidence": best["weight"],
        "method": "deterministic",
        "signals": hits[:4],
        "ambiguous_kinds": ambiguous,
        "model_used": False,
    }
