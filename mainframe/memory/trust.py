"""Trust / authority model for local project memory."""

from __future__ import annotations

from typing import Any, Literal

# What the entry claims to be
EntryKind = Literal[
    "build_command",
    "module_responsibility",
    "accepted_solution",
    "failure_pattern",
]

# Epistemic class — never collapse these
SourceClass = Literal[
    "user_instruction",
    "observation",
    "hypothesis",
    "external_text",
    "generated_summary",
]

VerificationStatus = Literal[
    "unverified",
    "verified",
    "rejected",
    "expired",
    "needs_revalidation",
]

# Authority ranks — higher may guide action; generated_summary never outranks user
AUTHORITY: dict[SourceClass, int] = {
    "user_instruction": 100,
    "observation": 50,  # only when verification_status == verified
    "hypothesis": 10,
    "external_text": 5,
    "generated_summary": 0,  # must not acquire authority over user
}


def is_trusted_guidance(
    source_class: str,
    verification_status: str,
    *,
    rejected: bool = False,
) -> bool:
    """Trusted guidance usable as directives — never rejected / summary / external alone."""
    if rejected or verification_status == "rejected":
        return False
    if verification_status in {"expired", "needs_revalidation"}:
        return False
    if source_class == "user_instruction":
        return True
    if source_class == "observation" and verification_status == "verified":
        return True
    # Hypotheses, external text, generated summaries: never trusted guidance
    return False


def authority_score(source_class: str, verification_status: str) -> int:
    if not is_trusted_guidance(source_class, verification_status):
        return 0
    return AUTHORITY.get(source_class, 0)  # type: ignore[arg-type]


def provenance_label(source_class: str) -> dict[str, Any]:
    return {
        "source_class": source_class,
        "may_override_user": False,
        "may_overwrite_evidence": False,
        "hosted_storage": False,
        "used_for_model_training": False,
    }
