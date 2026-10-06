"""Typed AI workflow steps — eligibility + interactive quota; evidence-gated outputs."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from mainframe.ai import probe_free_inference, run_ai_step
from mainframe.cache.facades import cached_model_response
from mainframe.eligibility import ELIGIBLE_PROVIDERS
from mainframe.quota import AdmissionController, ActualUsage, UsageEstimate
from mainframe.workflows.evidence import AI_STEP_TYPES, check_ai_evidence
from mainframe.workflows.parsers import parse_known_format
from mainframe.workflows.typesafe import validate_value_against_schema

# Interactive coding uses the same ledger priority.
INTERACTIVE_PRIORITY = "interactive"


def _stable_input_key(ai_type: str, source: str, args: dict[str, Any]) -> str:
    material = {
        "ai_type": ai_type,
        "source_sha": hashlib.sha256(source.encode()).hexdigest(),
        "args": {k: args[k] for k in sorted(args) if k not in {"operation_id", "_delivery_mode"}},
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True, default=str).encode()).hexdigest()


def _parse_model_json(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                obj = json.loads(text[start : end + 1])
                return obj if isinstance(obj, dict) else None
            except json.JSONDecodeError:
                return None
    return None


def _refuse_silent_fallback(fallback: dict[str, Any] | None) -> dict[str, Any] | None:
    """
    Deterministic fallback must not silently change the promised AI meaning.
    Allowed only when explicitly marked as a non-semantic substitute.
    """
    if not fallback:
        return None
    if fallback.get("silent") is True or fallback.get("pretend_model_output") is True:
        return {
            "ok": False,
            "refused": True,
            "reason": "deterministic_fallback_must_not_silently_change_promised_meaning",
            "detail": fallback,
        }
    if not fallback.get("explicit_substitute"):
        return {
            "ok": False,
            "refused": True,
            "reason": "deterministic_fallback_must_not_silently_change_promised_meaning",
            "note": "Set explicit_substitute=true and is_deterministic_substitute=true to acknowledge.",
            "detail": fallback,
        }
    return None


def _resolve_fixture(model_fixture: dict[str, Any] | None, ai_type: str) -> dict[str, Any] | None:
    if not model_fixture:
        return None
    by = model_fixture.get("by_ai_type")
    if isinstance(by, dict) and ai_type in by:
        return by[ai_type]
    return model_fixture


def run_typed_ai_step(
    *,
    ai_type: str,
    source: str,
    args: dict[str, Any],
    work_dir: Path,
    output_schema: dict[str, Any] | None = None,
    model_fixture: dict[str, Any] | None = None,
    quota: AdmissionController | None = None,
    cache_root: Path | None = None,
    force_unavailable: bool = False,
) -> dict[str, Any]:
    """
    Execute extract | classify | summarize | propose_code.

    Routes through the same eligibility gate and interactive quota ledger as coding.
    """
    if ai_type not in AI_STEP_TYPES:
        return {"ok": False, "error": f"unknown_ai_type:{ai_type}", "checkpoint": True}

    # Known-format path: parsers + validated rules (no model)
    known = args.get("known_format")
    if known and ai_type == "extract":
        parsed = parse_known_format(str(known), source)
        if parsed.get("ok"):
            fields = parsed["fields"]
            evidence = check_ai_evidence(
                "extract",
                source=source,
                result={"fields": fields},
                required_fields=list(args.get("required_fields") or fields.keys()),
            )
            return {
                "ok": True,
                "ai_type": ai_type,
                "via": "known_format_parser",
                "fields": {k: v for k, v in fields.items() if k != "parser"},
                "uncertain": False,
                "evidence": evidence,
                "model_used": False,
                "quota_tokens": 0,
            }
        if args.get("allow_uncertain_on_parse_miss"):
            return {
                "ok": True,
                "ai_type": ai_type,
                "via": "known_format_parser",
                "uncertain": True,
                "reason": parsed.get("reason") or "format_mismatch",
                "fields": {},
                "model_used": False,
                "quota_tokens": 0,
            }

    # Deterministic fallback gate
    fb = args.get("deterministic_fallback")
    fb_refuse = _refuse_silent_fallback(fb if isinstance(fb, dict) else None)
    if fb_refuse is not None and fb:
        # Only refuse when caller attempted a fallback; absence is fine
        if fb.get("use"):
            return {**fb_refuse, "ai_type": ai_type, "checkpoint": False}

    if force_unavailable or args.get("force_unavailable"):
        return {
            "ok": False,
            "paused": True,
            "checkpoint": True,
            "ai_type": ai_type,
            "reason": "inference_forced_unavailable",
            "message": "AI step checkpointed; continue only independent work.",
            "fallback_used": False,
            "promised_meaning_preserved": True,
        }

    # Explicit uncertain without calling the model
    if args.get("force_uncertain"):
        return {
            "ok": True,
            "ai_type": ai_type,
            "uncertain": True,
            "reason": args.get("uncertain_reason") or "explicit_uncertain",
            "fields": {},
            "model_used": False,
            "quota_tokens": 0,
            "evidence": {"ok": True, "uncertain": True},
        }

    probe = probe_free_inference()
    fixture = _resolve_fixture(model_fixture or args.get("model_fixture"), ai_type)
    use_live = probe.status == "available" and fixture is None

    if not use_live and fixture is None:
        # Attempt explicit substitute only if acknowledged
        if isinstance(fb, dict) and fb.get("use") and fb.get("explicit_substitute"):
            return {
                "ok": True,
                "ai_type": ai_type,
                "via": "deterministic_substitute",
                "is_deterministic_substitute": True,
                "promised_meaning_changed": True,
                "fallback_used": True,
                "uncertain": True,
                "reason": "inference_unavailable_explicit_substitute_not_semantic_equivalent",
                "result": fb.get("result") or {},
                "model_used": False,
                "quota_tokens": 0,
                "probe": probe.to_dict(),
            }
        return {
            "ok": False,
            "paused": True,
            "checkpoint": True,
            "ai_type": ai_type,
            "reason": "inference_unavailable",
            "probe": probe.to_dict(),
            "message": "AI step checkpointed; continue only independent work.",
            "fallback_used": False,
            "promised_meaning_preserved": True,
        }

    provider_id = "ollama_local" if use_live else "fixture_local"
    if provider_id not in ELIGIBLE_PROVIDERS and provider_id != "fixture_local":
        return {
            "ok": False,
            "paused": True,
            "checkpoint": True,
            "ai_type": ai_type,
            "reason": "provider_not_eligible",
            "fallback_used": False,
        }

    work_dir.mkdir(parents=True, exist_ok=True)
    ctl = quota or AdmissionController(path=work_dir / "quota_ledger.sqlite")
    estimate = UsageEstimate(
        requests=1,
        tokens=int(args.get("estimate_tokens") or 512),
        context_tokens=min(len(source) // 4, 4096),
        tool_overhead_tokens=32,
    )
    admit = ctl.admit(
        provider_id=provider_id if provider_id in ELIGIBLE_PROVIDERS else "ollama_local",
        estimate=estimate,
        priority=INTERACTIVE_PRIORITY,  # same ledger priority as interactive coding
        window_id="workflow_ai",
    )
    if not admit.allowed:
        return {
            "ok": False,
            "paused": True,
            "checkpoint": True,
            "ai_type": ai_type,
            "reason": f"quota_denied:{admit.denied_code}",
            "quota": admit.to_dict(),
            "fallback_used": False,
            "promised_meaning_preserved": True,
        }

    prompt = _build_prompt(ai_type, source, args)
    cache_root = cache_root or work_dir
    input_key = _stable_input_key(ai_type, source, args)
    model_meta = {
        "provider_id": provider_id,
        "model_id": (fixture or {}).get("model_id") or "local",
        "model_version": (fixture or {}).get("model_version") or "1",
    }

    def _compute() -> dict[str, Any]:
        if fixture is not None:
            # Fixture may be a full result dict or wrap text
            if "text" in fixture:
                return {"text": fixture["text"], "fixture": True}
            return {"text": json.dumps(fixture.get("response") or fixture), "fixture": True}
        out = run_ai_step(prompt)
        if not out.get("ok"):
            return {"text": "", "paused": True, "raw": out}
        return {"text": str(out.get("text") or out.get("response") or ""), "raw": out}

    cached = cached_model_response(
        cache_root,
        prompt=f"{ai_type}:{input_key}:{prompt[:200]}",
        model=model_meta,
        compute_response=_compute,
        freshness_required=bool(args.get("freshness_required")),
    )
    payload = cached.get("result") or {}
    if payload.get("paused"):
        if admit.reservation_id:
            ctl.release(admit.reservation_id, reason="inference_paused")
        return {
            "ok": False,
            "paused": True,
            "checkpoint": True,
            "ai_type": ai_type,
            "reason": "inference_unavailable_during_generate",
            "raw": payload.get("raw"),
            "fallback_used": False,
            "cache_hit": cached.get("cache_hit"),
        }

    text = str(payload.get("text") or "")
    parsed = _parse_model_json(text)
    if parsed is None:
        if admit.reservation_id:
            ctl.reconcile(
                admit.reservation_id,
                ActualUsage(requests=1, tokens=len(text) // 4, unknown=False),
            )
        return {
            "ok": False,
            "rejected": True,
            "ai_type": ai_type,
            "reason": "model_output_not_json_object",
            "schema_valid": False,
            "note": "Valid JSON alone would still require evidence checks.",
            "cache_hit": cached.get("cache_hit"),
            "quota_tokens": estimate.total_tokens(),
        }

    # Schema validation (necessary but not sufficient)
    schema_ok, schema_reason = validate_value_against_schema(parsed, output_schema)
    if output_schema and not schema_ok:
        if admit.reservation_id:
            ctl.reconcile(
                admit.reservation_id,
                ActualUsage(requests=1, tokens=len(text) // 4, unknown=False),
            )
        return {
            "ok": False,
            "rejected": True,
            "ai_type": ai_type,
            "reason": f"schema_invalid:{schema_reason}",
            "schema_valid": False,
            "parsed": parsed,
            "cache_hit": cached.get("cache_hit"),
        }

    evidence = check_ai_evidence(
        ai_type,
        source=source,
        result=parsed,
        required_fields=args.get("required_fields"),
        allowed_labels=args.get("allowed_labels"),
    )
    tokens_used = max(32, len(text) // 4) + estimate.context_tokens // 8
    if admit.reservation_id:
        ctl.reconcile(
            admit.reservation_id,
            ActualUsage(requests=1, tokens=tokens_used, context_tokens=estimate.context_tokens),
        )

    if not evidence.get("ok"):
        return {
            "ok": False,
            "rejected": True,
            "ai_type": ai_type,
            "schema_valid": True,
            "evidence": evidence,
            "parsed": parsed,
            "reason": evidence.get("reason") or "evidence_failed",
            "note": "Valid JSON alone does not establish factual correctness.",
            "cache_hit": cached.get("cache_hit"),
            "quota_tokens": tokens_used,
            "quota_priority": INTERACTIVE_PRIORITY,
        }

    out: dict[str, Any] = {
        "ok": True,
        "ai_type": ai_type,
        "schema_valid": True,
        "evidence": evidence,
        "uncertain": bool(parsed.get("uncertain") or evidence.get("uncertain")),
        "cache_hit": cached.get("cache_hit"),
        "request_avoided": cached.get("request_avoided"),
        "model_used": use_live,
        "fixture_used": fixture is not None,
        "quota_tokens": tokens_used,
        "quota_priority": INTERACTIVE_PRIORITY,
        "eligibility_provider": provider_id,
    }
    if ai_type == "extract":
        out["fields"] = dict(parsed.get("fields") or {k: v for k, v in parsed.items() if k not in {"uncertain", "reason", "evidence"}})
        if parsed.get("uncertain"):
            out["uncertain"] = True
            out["reason"] = parsed.get("reason")
    elif ai_type == "classify":
        out["label"] = parsed.get("label") or parsed.get("class")
        out["evidence_span"] = parsed.get("evidence")
    elif ai_type == "summarize":
        out["summary"] = parsed.get("summary")
    elif ai_type == "propose_code":
        out["proposal"] = parsed.get("proposal") or parsed.get("code")
        out["claims"] = (evidence or {}).get("claims") or {
            "implemented": False,
            "verified": False,
            "is_proposal_only": True,
        }
    if out.get("uncertain"):
        out["reason"] = out.get("reason") or parsed.get("reason") or "explicit_uncertain"
    return out


def _build_prompt(ai_type: str, source: str, args: dict[str, Any]) -> str:
    if ai_type == "extract":
        fields = args.get("required_fields") or ["value"]
        return (
            f"Extract JSON object with fields {fields} from the source. "
            f"If unsure, return {{\"uncertain\": true, \"reason\": \"...\"}}. "
            f"Do not invent values absent from the source.\nSOURCE:\n{source}"
        )
    if ai_type == "classify":
        labels = args.get("allowed_labels") or []
        return (
            f"Classify into one of {labels}. Reply JSON {{\"label\": ..., \"evidence\": \"span\"}}. "
            f"If unsure, {{\"uncertain\": true}}.\nSOURCE:\n{source}"
        )
    if ai_type == "summarize":
        return (
            "Summarize factually using only source content. "
            "JSON {\"summary\": \"...\"} or {\"uncertain\": true}.\nSOURCE:\n" + source
        )
    return (
        "Propose code as JSON {\"proposal\": \"...\"}. Do not claim implemented/verified.\n"
        f"CONTEXT:\n{source}"
    )


# Avoid unused import warning for tempfile — used by callers for ledgers in tests
_ = tempfile
