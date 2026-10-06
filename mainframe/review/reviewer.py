"""Reviewer adapters — separate from patch generation; fixture reviewer for accept."""

from __future__ import annotations

import re
from typing import Any

from mainframe.review.packet import build_review_packet


# Seeded defect markers the fixture reviewer is trained to catch (accept harness).
SEEDED_DEFECT_PATTERNS: list[dict[str, Any]] = [
    {
        "id": "off_by_one_upper_bound",
        "regex": r"range\(\s*len\([^)]+\)\s*-\s*1\s*\)",
        "counterexample": "Last element is never visited; input of length 1 yields empty result.",
        "assumption": "Assumes skipping the final index is equivalent to full iteration.",
    },
    {
        "id": "silent_except_pass",
        "regex": r"except\s+Exception\s*:\s*(pass|\.\.\.)",
        "counterexample": "Any exception is swallowed; callers cannot observe failure.",
        "assumption": "Assumes all exceptions are non-actionable.",
    },
    {
        "id": "div_zero_unguarded",
        "regex": r"/\s*len\(\s*[^)]+\s*\)(?!\s*or\b)",
        "counterexample": "Empty collection → ZeroDivisionError.",
        "assumption": "Assumes collection is always non-empty.",
    },
    {
        "id": "todo_seeded_defect",
        "regex": r"SEEDED_DEFECT|FIXME_REVIEW_SEED",
        "counterexample": "Explicit seed marker left in production path.",
        "assumption": "Assumes placeholder code is acceptable for merge.",
    },
]


def fixture_review(packet: dict[str, Any]) -> dict[str, Any]:
    """
    Deterministic reviewer used in accept + offline mode.
    Detects seeded defects in the unified diff with reproducible evidence.
    Does not generate patches.
    """
    diffs = "\n".join((packet.get("diff") or {}).get("unified") or [])
    # Prefer added lines
    added = "\n".join(
        line[1:] for line in diffs.splitlines() if line.startswith("+") and not line.startswith("+++")
    )
    haystack = added or diffs

    defects: list[dict[str, Any]] = []
    for pat in SEEDED_DEFECT_PATTERNS:
        m = re.search(pat["regex"], haystack)
        if m:
            # Locate approximate file from diff headers
            file_hint = _file_near_match(diffs, m.group(0))
            defects.append(
                {
                    "id": pat["id"],
                    "matched": m.group(0),
                    "path": file_hint,
                    "counterexample": pat["counterexample"],
                    "unsupported_assumption": pat["assumption"],
                    "evidence": {
                        "kind": "diff_regex_match",
                        "pattern": pat["regex"],
                        "span": [m.start(), m.end()],
                        "reproducible": True,
                    },
                }
            )

    lineage = packet.get("lineage") or {}
    return {
        "role": "reviewer",
        "adapter": "fixture_review",
        "patch_generated": False,
        "separated_from_patch_generation": True,
        "defects_found": defects,
        "ok": len(defects) == 0,
        "counterexamples": [d["counterexample"] for d in defects],
        "unsupported_assumptions": [d["unsupported_assumption"] for d in defects],
        "reproducible_evidence": [d["evidence"] for d in defects],
        "shared_blind_spot_risk": bool(lineage.get("shared_blind_spot_risk")),
        "lineage_note": lineage.get("note"),
        "model_used": False,
        "quota_tokens": 0,
    }


def run_review(
    *,
    contract: dict[str, Any] | None,
    unified_diffs: list[str],
    relevant_context: dict[str, Any] | None,
    deterministic_results: dict[str, Any],
    human_requirements: list[str] | None = None,
    patch_author_model_id: str | None = None,
    reviewer_model_id: str | None = None,
    invoke_model: bool = False,
) -> dict[str, Any]:
    """
    Build packet and run reviewer. Model path is paused when free inference is
    unavailable; fixture reviewer always available for gated/offline acceptance.
    """
    packet = build_review_packet(
        contract=contract,
        unified_diffs=unified_diffs,
        relevant_context=relevant_context,
        deterministic_results=deterministic_results,
        human_requirements=human_requirements,
        patch_author_model_id=patch_author_model_id,
        reviewer_model_id=reviewer_model_id or "fixture_local/fixture-reviewer@1.0.0",
    )
    # Even when invoke_model is True, we use the fixture reviewer offline so
    # acceptance stays free and reproducible. Live model review would go through
    # cost_gate + eligibility; absent entitlement we stay on fixture.
    result = fixture_review(packet)
    result["packet"] = {
        "ask_for": packet["ask_for"],
        "separated_from_patch_generation": packet["separated_from_patch_generation"],
        "lineage": packet["lineage"],
        "instructions_present": bool(packet["instructions"]),
    }
    result["model_invoked"] = bool(invoke_model)
    if invoke_model:
        result["model_path"] = "fixture_offline_standin"
        result["note"] = (
            "Model review requested; using fixture reviewer stand-in until eligible "
            "free inference is available. Packet still asks for counterexamples and assumptions."
        )
    return result


def _file_near_match(diffs: str, matched: str) -> str | None:
    current = None
    for line in diffs.splitlines():
        if line.startswith("+++ ") or line.startswith("--- "):
            part = line[4:].strip()
            if part.startswith("b/") or part.startswith("a/"):
                part = part[2:]
            if part != "/dev/null":
                current = part
        if matched in line:
            return current
    return current
