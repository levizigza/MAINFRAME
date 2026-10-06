"""Acceptance: mixed AI workflow — offline independent work, resume, reject unsupported extract."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from mainframe.workflows.ai_runtime import run_typed_ai_step
from mainframe.workflows.evidence import check_extract_evidence
from mainframe.workflows.load import load_fixture, materialize_fixture
from mainframe.workflows.parsers import parse_known_format
from mainframe.workflows.receipts import WorkflowReceiptStore
from mainframe.workflows.runner import run_workflow

CAPS = {
    "local.read",
    "local.write",
    "local.artifact",
    "ai.infer",
    "network.denied",
}


def run_workflow_ai_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    tmp = Path(tempfile.mkdtemp(prefix="mf-wf-ai-"))
    wf = load_fixture("mixed_ai_extract")
    work = materialize_fixture("mixed_ai_extract", tmp / "run")
    store = WorkflowReceiptStore(work / "receipts.sqlite")

    # 1) Offline: non-AI finishes; AI checkpointed; summarize waits
    offline = run_workflow(
        wf,
        work_dir=work,
        available_capabilities=CAPS,
        store=store,
        force_ai_unavailable=True,
    )
    digest = work / "digest.json"
    checks.append(
        {
            "id": "mixed_offline_finishes_non_ai",
            "ok": (
                offline.get("state") == "ai_checkpointed"
                and offline.get("independent_work_completed") is True
                and "load" in (offline.get("step_outputs") or {})
                and "write_digest" in (offline.get("step_outputs") or {})
                and digest.is_file()
                and "extract" in (offline.get("checkpointed_ai") or [])
                and "summarize" in (offline.get("skipped_dependent") or [])
                and "extract" not in (offline.get("step_outputs") or {})
            ),
            "detail": {
                "state": offline.get("state"),
                "step_keys": sorted((offline.get("step_outputs") or {}).keys()),
                "checkpointed_ai": offline.get("checkpointed_ai"),
                "skipped_dependent": offline.get("skipped_dependent"),
            },
        }
    )

    # 2) Resume semantic extract with plausible but unsupported value → reject
    bad = run_workflow(
        wf,
        work_dir=work,
        available_capabilities=CAPS,
        store=store,
        resume_run_id=offline.get("run_id"),
        model_fixture={
            "response": {"name": "MAINFRAME", "version": "9.9.9"},
            "model_id": "fixture-extract",
            "model_version": "1",
        },
    )
    checks.append(
        {
            "id": "reject_plausible_unsupported_extract",
            "ok": (
                bad.get("ok") is False
                and bad.get("state") == "rejected"
                and (
                    "unsupported" in (bad.get("blocked_reason") or "")
                    or bad.get("blocked_reason") == "plausible_but_unsupported_extracted_value"
                )
                and digest.is_file()
            ),
            "detail": {
                "state": bad.get("state"),
                "reason": bad.get("blocked_reason"),
                "extract": (bad.get("step_outputs") or {}).get("extract"),
                "receipt_states": [
                    (r.get("step_id"), r.get("state"), r.get("error"))
                    for r in (bad.get("receipts") or [])
                    if r.get("step_id") == "extract"
                ],
            },
        }
    )

    # Direct evidence unit: schema-valid JSON still rejected without source support
    source = (work / "source.txt").read_text(encoding="utf-8")
    ev = check_extract_evidence(
        source=source,
        extracted={"name": "MAINFRAME", "version": "9.9.9"},
        required_fields=["name", "version"],
    )
    checks.append(
        {
            "id": "valid_json_not_factual_correctness",
            "ok": ev.get("ok") is False and ev.get("reason") == "plausible_but_unsupported_extracted_value",
            "detail": ev,
        }
    )

    # 3) Resume with evidence-backed extract after a fresh run (new work dir; prior rejected)
    work2 = materialize_fixture("mixed_ai_extract", tmp / "ok")
    store2 = WorkflowReceiptStore(work2 / "receipts.sqlite")
    paused = run_workflow(
        wf,
        work_dir=work2,
        available_capabilities=CAPS,
        store=store2,
        force_ai_unavailable=True,
    )
    good = run_workflow(
        wf,
        work_dir=work2,
        available_capabilities=CAPS,
        store=store2,
        resume_run_id=paused.get("run_id"),
        model_fixture={
            "by_ai_type": {
                "extract": {
                    "response": {"name": "MAINFRAME", "version": "0.1.20"},
                    "model_id": "fixture-extract",
                    "model_version": "1",
                },
                "summarize": {
                    "response": {
                        "summary": "Package MAINFRAME version 0.1.20 with local workflows and FreeForge receipts."
                    },
                    "model_id": "fixture-summarize",
                    "model_version": "1",
                },
            }
        },
    )
    checks.append(
        {
            "id": "resume_semantic_step_later",
            "ok": (
                paused.get("state") == "ai_checkpointed"
                and good.get("ok") is True
                and (good.get("step_outputs") or {}).get("extract", {}).get("ok") is True
                and (good.get("step_outputs") or {}).get("extract", {}).get("fields", {}).get("version")
                == "0.1.20"
                and "write_digest" in (good.get("duplicated_suppressed") or [])
            ),
            "detail": {
                "paused_state": paused.get("state"),
                "good_state": good.get("state"),
                "extract": (good.get("step_outputs") or {}).get("extract"),
                "duplicated_suppressed": good.get("duplicated_suppressed"),
            },
        }
    )

    # Explicit uncertain allowed
    unc = run_typed_ai_step(
        ai_type="extract",
        source=source,
        args={"force_uncertain": True, "uncertain_reason": "low_confidence"},
        work_dir=tmp / "unc",
    )
    checks.append(
        {
            "id": "explicit_uncertain_allowed",
            "ok": unc.get("ok") is True and unc.get("uncertain") is True,
            "detail": unc,
        }
    )

    # Known-format parser (no model)
    parsed = parse_known_format("package_version", source)
    checks.append(
        {
            "id": "known_format_parser",
            "ok": parsed.get("ok") is True
            and (parsed.get("fields") or {}).get("version") == "0.1.20",
            "detail": parsed,
        }
    )

    # Silent deterministic fallback refused
    silent = run_typed_ai_step(
        ai_type="summarize",
        source=source,
        args={
            "force_unavailable": True,
            "deterministic_fallback": {
                "use": True,
                "silent": True,
                "result": {"summary": "fake summary pretending to be model output"},
            },
        },
        work_dir=tmp / "silent",
    )
    checks.append(
        {
            "id": "silent_fallback_refused",
            "ok": (
                silent.get("ok") is False
                and "silently_change_promised_meaning" in (silent.get("reason") or "")
            ),
            "detail": silent,
        }
    )

    # Cache stable inputs on reuse
    c1 = run_typed_ai_step(
        ai_type="extract",
        source=source,
        args={"required_fields": ["name", "version"]},
        work_dir=tmp / "cache",
        model_fixture={
            "response": {"name": "MAINFRAME", "version": "0.1.20"},
            "model_id": "cache-test",
            "model_version": "1",
        },
        cache_root=tmp / "cache_root",
    )
    c2 = run_typed_ai_step(
        ai_type="extract",
        source=source,
        args={"required_fields": ["name", "version"]},
        work_dir=tmp / "cache",
        model_fixture={
            "response": {"name": "MAINFRAME", "version": "0.1.20"},
            "model_id": "cache-test",
            "model_version": "1",
        },
        cache_root=tmp / "cache_root",
    )
    checks.append(
        {
            "id": "cache_stable_inputs_on_reuse",
            "ok": c1.get("ok") is True and c2.get("cache_hit") is True,
            "detail": {"c1_hit": c1.get("cache_hit"), "c2_hit": c2.get("cache_hit"), "c2": c2},
        }
    )

    # Quota priority interactive
    checks.append(
        {
            "id": "quota_priority_interactive",
            "ok": (c1.get("quota_priority") == "interactive") or (c2.get("quota_priority") == "interactive"),
            "detail": {"c1": c1.get("quota_priority"), "tokens": c1.get("quota_tokens")},
        }
    )

    passed = sum(1 for c in checks if c["ok"])
    failed = len(checks) - passed
    return {"ok": failed == 0, "passed": passed, "failed": failed, "checks": checks}
