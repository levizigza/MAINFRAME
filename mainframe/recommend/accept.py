"""Acceptance for recommended FreeForge configuration."""

from __future__ import annotations

from typing import Any

from mainframe.config import ROOT
from mainframe.recommend.suite import REPORT_JSON, REPORT_MD, run_recommend


def run_recommend_accept() -> dict[str, Any]:
    payload = run_recommend()
    acc = payload.get("acceptance") or {}
    demos = payload.get("demos") or {}
    modes = payload.get("modes") or {}
    checks: list[dict[str, Any]] = []

    checks.append(
        {
            "id": "reports_published",
            "ok": REPORT_MD.is_file() and REPORT_JSON.is_file(),
            "detail": {
                "md": str(REPORT_MD.relative_to(ROOT)).replace("\\", "/"),
                "json": str(REPORT_JSON.relative_to(ROOT)).replace("\\", "/"),
            },
        }
    )
    checks.append(
        {
            "id": "three_modes_and_recommended",
            "ok": bool(acc.get("three_modes_explicit"))
            and bool(modes.get("recommended_mode_id")),
            "detail": {
                "recommended": modes.get("recommended_mode_id"),
                "mode_ids": list((modes.get("modes") or {}).keys()),
            },
        }
    )
    checks.append(
        {
            "id": "mode_c_no_false_hosted_eligibility",
            "ok": bool(acc.get("mode_c_honest_empty")),
            "detail": (modes.get("modes") or {})
            .get("deterministic_plus_eligible_free_hosted_ai", {})
            .get("currently_eligible_providers"),
        }
    )
    checks.append(
        {
            "id": "verified_coding_task",
            "ok": bool((demos.get("coding") or {}).get("ok")),
            "detail": demos.get("coding"),
        }
    )
    checks.append(
        {
            "id": "reusable_automation",
            "ok": bool((demos.get("automation") or {}).get("ok")),
            "detail": {
                "ok": (demos.get("automation") or {}).get("ok"),
                "workflow_id": (demos.get("automation") or {}).get("workflow_id"),
                "blocker": (demos.get("automation") or {}).get("blocker"),
            },
        }
    )
    checks.append(
        {
            "id": "baselines_stated_honestly",
            "ok": bool(
                ((payload.get("workloads") or {}).get("vs_baselines") or {}).get(
                    "outperforms_measured_baselines"
                )
            )
            and bool(
                ((payload.get("workloads") or {}).get("vs_baselines") or {}).get(
                    "does_not_outperform_or_unmeasured"
                )
            ),
            "detail": {
                "outperforms_n": len(
                    ((payload.get("workloads") or {}).get("vs_baselines") or {}).get(
                        "outperforms_measured_baselines"
                    )
                    or []
                ),
                "does_not_n": len(
                    ((payload.get("workloads") or {}).get("vs_baselines") or {}).get(
                        "does_not_outperform_or_unmeasured"
                    )
                    or []
                ),
            },
        }
    )
    checks.append(
        {
            "id": "no_unlimited_frontier_promise",
            "ok": bool(acc.get("no_frontier_unlimited_claim"))
            and (
                (payload.get("capability_matrix") or {})
                .get("cells", {})
                .get("frontier_unlimited_performance", {})
                .get("explicitly_not_claimed")
                is True
            ),
            "detail": "explicitly_not_claimed",
        }
    )

    passed = sum(1 for c in checks if c.get("ok"))
    failed = len(checks) - passed
    return {
        "ok": failed == 0,
        "passed": passed,
        "failed": failed,
        "checks": checks,
        "recommended_mode_id": modes.get("recommended_mode_id"),
        "report_md": payload.get("report_md"),
        "report_json": payload.get("report_json"),
        "blockers": [
            (demos.get("coding") or {}).get("blocker"),
            (demos.get("automation") or {}).get("blocker"),
        ],
    }
