"""Cache policy — exact reuse only; refuse stale auth / mutations / time-sensitive."""

from __future__ import annotations

from typing import Any, Literal

CacheKind = Literal[
    "repo_scan",
    "retrieval",
    "tool_output",
    "workflow_artifact",
    "model_response",
]

# Approximate similarity is tracked separately and MUST NOT serve as current truth.
APPROXIMATE_SIMILARITY_ENABLED = False

# Kinds that may use exact reuse when policy allows
EXACT_ELIGIBLE_KINDS: frozenset[str] = frozenset(
    {
        "repo_scan",
        "retrieval",
        "tool_output",
        "workflow_artifact",
        "model_response",
    }
)

# Never cache these as if current
REFUSE_REASONS = {
    "authorization": "Never reuse a stale authorization decision as current.",
    "external_mutation": "Never reuse results that imply external mutation occurred.",
    "time_sensitive": "Never reuse a time-sensitive answer as if it were current.",
    "approximate": "Approximate similarity is not exact reuse and cannot satisfy current truth.",
    "side_effects": "Mutating / side-effecting operations are not exact-cache eligible.",
}


def may_exact_cache(
    kind: str,
    *,
    read_only: bool = True,
    side_effects: bool = False,
    is_authorization: bool = False,
    is_external_mutation: bool = False,
    is_time_sensitive: bool = False,
    freshness_required: bool = False,
) -> dict[str, Any]:
    if kind not in EXACT_ELIGIBLE_KINDS:
        return {"allowed": False, "reason": f"unknown_kind:{kind}", "exact": True}
    if is_authorization:
        return {"allowed": False, "reason": REFUSE_REASONS["authorization"], "code": "authorization"}
    if is_external_mutation:
        return {
            "allowed": False,
            "reason": REFUSE_REASONS["external_mutation"],
            "code": "external_mutation",
        }
    if is_time_sensitive or freshness_required:
        return {
            "allowed": False,
            "reason": REFUSE_REASONS["time_sensitive"],
            "code": "time_sensitive",
        }
    if side_effects or not read_only:
        return {"allowed": False, "reason": REFUSE_REASONS["side_effects"], "code": "side_effects"}
    return {"allowed": True, "reason": "exact_reuse_valid", "exact": True, "approximate": False}


def approximate_lookup_refused() -> dict[str, Any]:
    return {
        "allowed": False,
        "exact": False,
        "approximate": True,
        "enabled": APPROXIMATE_SIMILARITY_ENABLED,
        "reason": REFUSE_REASONS["approximate"],
        "note": "Similarity indexes may exist for ranking research only; they never replace exact keys.",
    }
