"""Task-specific evidence checks — valid JSON alone is not factual correctness."""

from __future__ import annotations

import re
from typing import Any

AI_STEP_TYPES = ("extract", "classify", "summarize", "propose_code")


def _norm(s: Any) -> str:
    return str(s if s is not None else "").strip()


def _source_contains(source: str, value: str) -> bool:
    if not value:
        return False
    return value in source


def check_extract_evidence(
    *,
    source: str,
    extracted: dict[str, Any],
    required_fields: list[str] | None = None,
) -> dict[str, Any]:
    """
    Each non-uncertain claimed field value must appear in the source text.
    Plausible invented values are rejected even when schema-valid.
    """
    if extracted.get("uncertain") is True:
        return {
            "ok": True,
            "uncertain": True,
            "reason": extracted.get("reason") or "explicit_uncertain",
            "factual_correctness": "not_claimed",
        }

    fields = dict(extracted.get("fields") or extracted)
    fields.pop("uncertain", None)
    fields.pop("reason", None)
    fields.pop("evidence", None)
    req = list(required_fields or fields.keys())
    unsupported: list[str] = []
    supported: dict[str, str] = {}
    for key in req:
        if key not in fields:
            unsupported.append(f"missing:{key}")
            continue
        val = _norm(fields[key])
        if not _source_contains(source, val):
            unsupported.append(key)
        else:
            supported[key] = val

    if unsupported:
        return {
            "ok": False,
            "uncertain": False,
            "rejected": True,
            "reason": "plausible_but_unsupported_extracted_value",
            "unsupported_fields": unsupported,
            "supported_fields": supported,
            "note": "Valid JSON does not establish factual correctness.",
        }
    return {
        "ok": True,
        "uncertain": False,
        "supported_fields": supported,
        "factual_correctness": "evidence_backed",
    }


def check_classify_evidence(
    *,
    source: str,
    result: dict[str, Any],
    allowed_labels: list[str] | None = None,
) -> dict[str, Any]:
    if result.get("uncertain") is True:
        return {"ok": True, "uncertain": True, "reason": result.get("reason") or "explicit_uncertain"}
    label = _norm(result.get("label") or result.get("class"))
    if not label:
        return {"ok": False, "rejected": True, "reason": "missing_label"}
    if allowed_labels is not None and label not in allowed_labels:
        return {
            "ok": False,
            "rejected": True,
            "reason": "label_not_in_allowed_set",
            "label": label,
            "allowed": list(allowed_labels),
        }
    # Require a cited span or keyword from source when evidence is declared
    evidence = result.get("evidence")
    if evidence:
        span = _norm(evidence if isinstance(evidence, str) else (evidence or {}).get("span"))
        if span and not _source_contains(source, span):
            return {
                "ok": False,
                "rejected": True,
                "reason": "classification_evidence_span_not_in_source",
                "span": span,
            }
    elif allowed_labels:
        # Without evidence, only accept if label token appears in source (weak but non-invented)
        if label.lower() not in source.lower() and not any(
            _norm(a).lower() in source.lower() for a in allowed_labels if a == label
        ):
            # Still allow closed-set label if rules matched — mark requires_rules
            if not result.get("rule_id"):
                return {
                    "ok": False,
                    "rejected": True,
                    "reason": "classification_lacks_evidence_or_rule",
                    "label": label,
                }
    return {"ok": True, "uncertain": False, "label": label}


def check_summarize_evidence(
    *,
    source: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    if result.get("uncertain") is True:
        return {"ok": True, "uncertain": True, "reason": result.get("reason") or "explicit_uncertain"}
    summary = _norm(result.get("summary"))
    if not summary:
        return {"ok": False, "rejected": True, "reason": "missing_summary"}
    # Reject summaries that introduce tokens absent from source (crude hallucination guard)
    # Allow short stopwords; flag long novel tokens
    tokens = re.findall(r"[A-Za-z0-9_.\-]{4,}", summary)
    novel = [t for t in tokens if t.lower() not in source.lower()]
    if len(novel) > max(2, len(tokens) // 2):
        return {
            "ok": False,
            "rejected": True,
            "reason": "summary_introduces_unsupported_content",
            "novel_tokens": novel[:12],
            "note": "Valid JSON/string alone does not establish factual correctness.",
        }
    return {"ok": True, "uncertain": False, "summary": summary}


def check_propose_code_evidence(
    *,
    source: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    if result.get("uncertain") is True:
        return {"ok": True, "uncertain": True, "reason": result.get("reason") or "explicit_uncertain"}
    proposal = result.get("proposal") or result.get("code") or ""
    if not _norm(proposal):
        return {"ok": False, "rejected": True, "reason": "missing_proposal"}
    # Proposals are never claimed implemented/verified
    if result.get("implemented") is True or result.get("verified") is True:
        return {
            "ok": False,
            "rejected": True,
            "reason": "proposal_must_not_claim_implemented_or_verified",
        }
    return {
        "ok": True,
        "uncertain": False,
        "proposal": proposal,
        "claims": {
            "implemented": False,
            "verified": False,
            "is_proposal_only": True,
        },
    }


def check_ai_evidence(ai_type: str, *, source: str, result: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    if ai_type == "extract":
        return check_extract_evidence(source=source, extracted=result, required_fields=kwargs.get("required_fields"))
    if ai_type == "classify":
        return check_classify_evidence(
            source=source, result=result, allowed_labels=kwargs.get("allowed_labels")
        )
    if ai_type == "summarize":
        return check_summarize_evidence(source=source, result=result)
    if ai_type == "propose_code":
        return check_propose_code_evidence(source=source, result=result)
    return {"ok": False, "rejected": True, "reason": f"unknown_ai_type:{ai_type}"}
