"""Assemble the reviewer packet: contract, diff, context, results."""

from __future__ import annotations

from typing import Any


REVIEWER_PROMPT_REQUIREMENTS = (
    "You are a *reviewer*, not the patch author. Do not regenerate the patch. "
    "Given the task contract, unified diff, relevant context, and deterministic results: "
    "(1) list specific counterexamples that would break the change; "
    "(2) list unsupported assumptions; "
    "(3) cite reproducible evidence (file:line, failing check, or concrete input). "
    "If you share model/training lineage with the patch author, note shared blind-spot risk."
)


def build_review_packet(
    *,
    contract: dict[str, Any] | None,
    unified_diffs: list[str],
    relevant_context: dict[str, Any] | None,
    deterministic_results: dict[str, Any],
    human_requirements: list[str] | None = None,
    patch_author_model_id: str | None = None,
    reviewer_model_id: str | None = None,
) -> dict[str, Any]:
    same_lineage = bool(
        patch_author_model_id
        and reviewer_model_id
        and _lineage_key(patch_author_model_id) == _lineage_key(reviewer_model_id)
    )
    return {
        "role": "reviewer_not_patch_author",
        "separated_from_patch_generation": True,
        "instructions": REVIEWER_PROMPT_REQUIREMENTS,
        "task_contract": contract or {},
        "diff": {"unified": list(unified_diffs), "files_n": len(unified_diffs)},
        "relevant_context": relevant_context or {},
        "deterministic_results": deterministic_results,
        "human_requirements": list(human_requirements or []),
        "lineage": {
            "patch_author_model_id": patch_author_model_id,
            "reviewer_model_id": reviewer_model_id,
            "same_model_or_training_lineage": same_lineage,
            "shared_blind_spot_risk": same_lineage,
            "note": (
                "Same model or training lineage can share blind spots; "
                "prefer evaluator-owned checks over agreeing with the author."
                if same_lineage
                else "Distinct reviewer lineage when available."
            ),
        },
        "ask_for": ["specific_counterexamples", "unsupported_assumptions", "reproducible_evidence"],
    }


def _lineage_key(model_id: str) -> str:
    # Collapse version suffixes so fixture-author@1 and fixture-author@2 share lineage.
    base = model_id.strip().lower()
    if "@" in base:
        base = base.split("@", 1)[0]
    if "/" in base:
        base = base.rsplit("/", 1)[-1]
    # Strip trailing -reviewer / -author role tags for lineage comparison
    for suffix in ("-reviewer", "-author", "-patch", "-gen"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return base
