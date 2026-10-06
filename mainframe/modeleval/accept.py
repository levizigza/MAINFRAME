"""Acceptance: measured routing ≠ size/marketing; unknowns stay unknown; FP invalidates."""

from __future__ import annotations

from typing import Any

from mainframe.modeleval.catalog import holdout_ids, tune_ids
from mainframe.modeleval.matrix import build_matrix
from mainframe.modeleval.routing import invalidate_if_fingerprint_changed, select_routes
from mainframe.modeleval.runners import ModelRef, discover_eligible_models, run_eval


def run_modeleval_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    hold = holdout_ids()
    tune = tune_ids()
    checks.append(
        {
            "id": "holdout_disjoint_from_tune",
            "ok": hold.isdisjoint(tune) and len(hold) >= 4 and "vi_hold_optional" in hold,
            "detail": {"holdout": sorted(hold), "tune": sorted(tune)},
        }
    )

    # Eval holdout on fixture models only (available + eligible)
    fixtures = [
        m
        for m in discover_eligible_models()
        if m.provider_id == "fixture_local" and m.available and m.eligible
    ]
    report = run_eval(split="holdout", models=fixtures, use_quota=True)
    measured = [r for r in report["results"] if r.get("status") == "measured"]
    checks.append(
        {
            "id": "eval_records_provenance",
            "ok": all(
                r.get("evaluated_at")
                and r.get("model", {}).get("model_version")
                and r.get("model", {}).get("provider_id")
                and "context_settings" in (r.get("model") or {})
                and r.get("measurement_kind") == "local_measurement"
                and r.get("published_claim") is False
                for r in measured
            )
            and len(measured) >= 6,
            "detail": {"measured_n": len(measured), "sample": measured[0] if measured else None},
        }
    )

    # Metrics present
    checks.append(
        {
            "id": "metrics_include_latency_tools_retries_quota",
            "ok": all(
                "latency_ms" in r
                and "invalid_tool_calls" in r
                and "retries" in r
                and "quota_tokens" in r
                and "correctness" in r
                for r in measured
            ),
            "detail": "required metric fields on measured rows",
        }
    )

    matrix = build_matrix(report)
    # Missing vision for non-vision models stays unknown
    strong = "fixture_local/fixture-strong@1.0.0"
    vision_cell = (matrix["cells"].get(strong) or {}).get("vision") or {}
    checks.append(
        {
            "id": "missing_measurements_remain_unknown",
            "ok": vision_cell.get("status") == "unknown",
            "detail": vision_cell,
        }
    )

    routes = select_routes(matrix)
    # code_repair / tool_selection / etc. should pick fixture-strong, NOT huge marketing label
    picked = {
        cls: (routes["routes"].get(cls) or {}).get("selected")
        for cls in ("code_repair", "tool_selection", "structured_extraction", "planning")
    }
    huge = "fixture_local/fixture-weak-huge-label@1.0.0"
    checks.append(
        {
            "id": "routing_follows_measured_not_size_or_marketing",
            "ok": all(v == strong for v in picked.values()) and huge not in picked.values(),
            "detail": {"picked": picked, "routes_rules": {c: routes["routes"][c].get("rule") for c in picked}},
        }
    )

    # Vision route → vision model when measured
    vis = routes["routes"].get("vision") or {}
    checks.append(
        {
            "id": "vision_optional_measured_when_supported",
            "ok": vis.get("selected") == "fixture_local/fixture-vision@1.0.0" and vis.get("status") == "measured",
            "detail": vis,
        }
    )

    # Fingerprint change invalidates
    stored = routes
    changed_models = []
    for m in fixtures:
        d = m.to_dict()
        if d["model_id"] == "fixture-strong":
            d["model_version"] = "1.0.1"  # change version → new fingerprint
            d["fingerprint"] = ModelRef(
                provider_id=m.provider_id,
                model_id=m.model_id,
                model_version="1.0.1",
                context_settings=m.context_settings,
                eligible=True,
                available=True,
                availability_kind="local_runtime",
            ).fingerprint()
        changed_models.append(d)
    inv = invalidate_if_fingerprint_changed(stored, changed_models)
    checks.append(
        {
            "id": "model_change_invalidates_stale_ranking",
            "ok": (
                "code_repair" in inv["invalidated_classes"]
                and (inv["routes"].get("code_repair") or {}).get("status") == "unknown"
                and (inv["routes"].get("code_repair") or {}).get("inherited_ranking") is False
            ),
            "detail": inv,
        }
    )

    # Account-dependent hosted not treated as measured
    hosted = [m for m in discover_eligible_models() if m.availability_kind == "account_dependent"]
    checks.append(
        {
            "id": "account_dependent_not_auto_measured",
            "ok": len(hosted) >= 1 and all(not m.eligible or not m.available for m in hosted),
            "detail": [m.to_dict() for m in hosted[:3]],
        }
    )

    # Interpretable + reversible flags
    checks.append(
        {
            "id": "routing_interpretable_reversible",
            "ok": routes.get("interpretable") is True
            and routes.get("uses_model_size") is False
            and routes.get("uses_marketing_labels") is False
            and all((r.get("reversible") is True) or r.get("status") == "unknown" for r in routes["routes"].values()),
            "detail": {"uses_model_size": routes.get("uses_model_size")},
        }
    )

    passed = sum(1 for c in checks if c["ok"])
    failed = len(checks) - passed
    return {
        "ok": failed == 0,
        "passed": passed,
        "failed": failed,
        "checks": checks,
        "matrix_summary": {
            "models": list(matrix.get("models", {}).keys()),
            "route_selected": picked,
        },
    }
