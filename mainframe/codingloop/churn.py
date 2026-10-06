"""Detect repeated patches, oscillation, and irrelevant file churn."""

from __future__ import annotations

import hashlib
from typing import Any


def patch_fingerprint(edits: list[dict[str, Any]]) -> str:
    parts = []
    for e in sorted(edits, key=lambda x: (x.get("path") or "", x.get("old") or "")):
        parts.append(f"{e.get('path')}|{e.get('old')}|{e.get('new')}")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]


def detect_repeated_patch(history: list[str], fingerprint: str) -> bool:
    return fingerprint in history


def detect_oscillation(history: list[str]) -> bool:
    """A→B→A style patch fingerprints."""
    if len(history) < 3:
        return False
    a, b, c = history[-3], history[-2], history[-1]
    return a == c and a != b


def detect_irrelevant_churn(
    touched_paths: list[str],
    *,
    relevant_paths: set[str],
) -> dict[str, Any]:
    touched = {p.replace("\\", "/") for p in touched_paths}
    relevant = {p.replace("\\", "/") for p in relevant_paths}
    if not relevant:
        return {"churn": False, "irrelevant": [], "reason": "no_relevance_scope"}
    irrelevant = sorted(touched - relevant)
    return {
        "churn": bool(irrelevant),
        "irrelevant": irrelevant,
        "touched": sorted(touched),
        "relevant": sorted(relevant),
    }
