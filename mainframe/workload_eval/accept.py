"""Acceptance for held-out workload evaluation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mainframe.config import ROOT
from mainframe.workload_eval.suite import (
    REPORT_JSON,
    REPORT_MD,
    POLICY_PATH,
    run_heldout_eval,
)


def run_workload_eval_accept(*, trials: int = 3) -> dict[str, Any]:
    """
    Run a smaller trial count for accept speed; still publishes reports.
    Acceptance: only evidence-supported claims; disable policy present; competitors unmeasured.
    """
    checks: list[dict[str, Any]] = []
    payload = run_heldout_eval(trials=trials)

    checks.append(
        {
            "id": "heldout_fixtures_present",
            "ok": all(
                (ROOT / "docs/eval/workloads/holdout" / p).exists()
                for p in (
                    "w1_repo_repair/broken_math.py",
                    "w1_repo_repair/decoy_ops.py",
                    "w2_site_maint/index.html",
                    "w3_doc_report/batch.csv",
                )
            ),
            "detail": "holdout paths",
        }
    )
    checks.append(
        {
            "id": "reports_published",
            "ok": REPORT_MD.is_file() and REPORT_JSON.is_file() and POLICY_PATH.is_file(),
            "detail": {
                "md": str(REPORT_MD.relative_to(ROOT)).replace("\\", "/"),
                "json": str(REPORT_JSON.relative_to(ROOT)).replace("\\", "/"),
            },
        }
    )
    checks.append(
        {
            "id": "small_sample_acknowledged",
            "ok": bool(payload.get("small_sample_acknowledged")),
            "detail": {"trials_per_cell": payload.get("trials_per_cell")},
        }
    )
    checks.append(
        {
            "id": "competitors_unmeasured",
            "ok": (payload.get("competitors") or {}).get("claude_code_e2e") == "unmeasured"
            and (payload.get("competitors") or {}).get("cursor_e2e") == "unmeasured",
            "detail": payload.get("competitors"),
        }
    )

    # Metrics keys present for freeforge
    comp = payload.get("comparison") or {}
    wl = (comp.get("repository_repair") or {}).get("freeforge") or {}
    agg = wl.get("aggregate") or {}
    required = {
        "correct_completion_rate",
        "total_elapsed_s_mean",
        "active_human_s_mean",
        "retries_total",
        "model_calls_total",
        "failure_recoveries_total",
        "setup_s_sum",
        "maintenance_s_sum",
        "sustainable_daily_volume_est",
    }
    checks.append(
        {
            "id": "metrics_reported",
            "ok": required.issubset(set(agg.keys()))
            and isinstance(agg.get("correct_completion_rate"), dict)
            and "ci95_low" in (agg.get("correct_completion_rate") or {}),
            "detail": sorted(agg.keys()),
        }
    )

    # Ablations present
    abl = payload.get("ablations") or {}
    abl_ok = all(
        set((abl.get(w) or {}).keys())
        >= {"full", "no_retrieval", "no_workflow_reuse", "no_review", "no_caching"}
        for w in ("repository_repair", "website_maintenance", "document_reporting")
    )
    checks.append({"id": "ablations_run", "ok": abl_ok, "detail": {w: list((abl.get(w) or {}).keys()) for w in abl}})

    # Claims: no unsupported universal superiority; every supported claim has evidence
    claims = payload.get("claims") or []
    bad_universal = any(
        c.get("supported") and "universal" in str(c.get("claim") or "").lower() for c in claims
    )
    supported = [c for c in claims if c.get("supported")]
    evidence_ok = all(c.get("evidence") or c.get("claim", "").startswith("disable_") for c in supported)
    checks.append(
        {
            "id": "evidence_supported_claims_only",
            "ok": (not bad_universal) and evidence_ok and any(not c.get("supported") for c in claims),
            "detail": {"supported_n": len(supported), "total_claims": len(claims)},
        }
    )

    # Disable policy: at least one disable OR one positive contribution recorded
    pol = (payload.get("disable_policy") or {}).get("workloads") or {}
    any_signal = False
    for feats in pol.values():
        for meta in feats.values():
            if meta.get("disabled") or meta.get("contribution", 0) > 0:
                any_signal = True
    checks.append(
        {
            "id": "disable_or_contribution_policy",
            "ok": bool(pol) and any_signal,
            "detail": pol,
        }
    )

    # FreeForge beats minimal on at least one workload (evidence) OR we honestly claim none
    ff_beats = any(
        c.get("claim") == "freeforge_correct_rate_exceeds_minimal_free_agent" and c.get("supported")
        for c in claims
    )
    honest_none = any(
        c.get("claim") == "no_superiority_vs_minimal_on_correct_rate" for c in claims
    )
    checks.append(
        {
            "id": "workload_specific_superiority_honest",
            "ok": ff_beats or honest_none,
            "detail": {"ff_beats_minimal": ff_beats, "honest_none": honest_none},
        }
    )

    passed = sum(1 for c in checks if c.get("ok"))
    failed = len(checks) - passed
    return {
        "ok": failed == 0,
        "passed": passed,
        "failed": failed,
        "checks": checks,
        "report_md": payload.get("report_md"),
        "report_json": payload.get("report_json"),
        "trials_per_cell": trials,
    }
