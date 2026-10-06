"""Acceptance for reproducible cost audit."""

from __future__ import annotations

from typing import Any

from mainframe.config import ROOT
from mainframe.costaudit.boundary import allow_non_loopback_live, gate_url
from mainframe.costaudit.suite import REPORT_JSON, REPORT_MD, run_cost_audit
from mainframe.connectors.runtime import call_operation


def run_costaudit_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    payload = run_cost_audit()
    acc = payload.get("acceptance") or {}

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
            "id": "acceptance_all_pass",
            "ok": bool(payload.get("ok")) and all(acc.values()),
            "detail": acc,
        }
    )
    checks.append(
        {
            "id": "zero_fees_vs_physical_separated",
            "ok": bool(acc.get("zero_fees_separated_from_physical_resources")),
            "detail": (payload.get("surfaces") or {}).get("separation"),
        }
    )
    checks.append(
        {
            "id": "outbound_proofs_pass",
            "ok": bool(acc.get("outbound_controls_proven")),
            "detail": [
                p.get("path")
                for p in ((payload.get("outbound") or {}).get("control_proofs") or [])
                if not p.get("passed_control")
            ],
        }
    )
    checks.append(
        {
            "id": "hosted_gone_deterministic_ok",
            "ok": bool(acc.get("deterministic_usable_when_hosted_gone"))
            and bool(acc.get("ai_pauses_without_local_model"))
            and bool(acc.get("no_automatic_paid_fallback")),
            "detail": (payload.get("hosted_gone_simulation") or {}).get("contract"),
        }
    )

    # Live connector outside enforceable boundary must refuse (this host has no OS net jail)
    live = allow_non_loopback_live(purpose="accept_probe")
    gated = gate_url("https://dog.ceo/api/breeds/list/all", purpose="accept_probe")
    # When live would be attempted, runtime must refuse — exercise fixture still works
    fix = call_operation("dog_ceo", "list_breeds", mode="fixture", fixture_scenario="ok")
    live_call = call_operation("dog_ceo", "list_breeds", mode="live")
    checks.append(
        {
            "id": "live_outside_boundary_disabled",
            "ok": bool(
                live.get("allowed") is False
                and gated.get("allowed") is False
                and fix.get("ok")
                and live_call.get("ok") is False
            ),
            "detail": {
                "allow_non_loopback": live.get("error") or live.get("allowed"),
                "fixture_ok": fix.get("ok"),
                "live_ok": live_call.get("ok"),
                "live_error": (live_call.get("error") or {}).get("code")
                if isinstance(live_call.get("error"), dict)
                else live_call.get("error"),
            },
        }
    )

    # No required paid account claim
    checks.append(
        {
            "id": "no_required_paid_account_trial_hosted",
            "ok": bool(
                acc.get("no_required_paid_account")
                and acc.get("no_trial_or_promo_required")
                and acc.get("no_required_hosted_component")
            ),
            "detail": {
                k: acc.get(k)
                for k in (
                    "no_required_paid_account",
                    "no_trial_or_promo_required",
                    "no_required_hosted_component",
                )
            },
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
    }
