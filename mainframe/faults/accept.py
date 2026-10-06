"""Acceptance: fault-injection matrix published; critical categories must pass."""

from __future__ import annotations

from typing import Any

from mainframe.faults.matrix import publish_failure_matrix


def run_faults_accept() -> dict[str, Any]:
    published = publish_failure_matrix()
    matrix = published.get("matrix") or {}
    rows = {r["scenario"]: r for r in matrix.get("rows") or []}
    gate = matrix.get("gate_before_more_connectors") or {}

    required = [
        "duplicate_events",
        "clock_changes",
        "interrupted_files",
        "process_crashes",
        "service_timeouts",
        "malformed_model_output",
        "expired_credentials",
        "exhausted_free_quotas",
        "lost_acknowledgement_external_write",
        "cancellation_completed_effects_recorded",
        "unauthorized_actions_and_paid_fallback",
    ]

    checks: list[dict[str, Any]] = []
    for sid in required:
        row = rows.get(sid) or {}
        checks.append(
            {
                "id": sid,
                "ok": bool(row.get("pass")),
                "detail": row,
            }
        )

    checks.append(
        {
            "id": "matrix_published_local",
            "ok": bool(
                published.get("json_path")
                and published.get("md_path")
                and matrix.get("hosting") == "local_deterministic_no_hosted_ci"
                and matrix.get("live_observations") == 0
            ),
            "detail": {
                "json_path": published.get("json_path"),
                "md_path": published.get("md_path"),
                "fixtures": matrix.get("integration_fixtures"),
                "live": matrix.get("live_observations"),
            },
        }
    )

    checks.append(
        {
            "id": "connector_gate_critical_categories",
            "ok": bool(
                gate.get("data_loss")
                and gate.get("duplicate_effects")
                and gate.get("unauthorized_actions")
                and gate.get("paid_fallback")
                and gate.get("allow_more_connectors")
            ),
            "detail": gate,
        }
    )

    # Fixtures vs live separation
    checks.append(
        {
            "id": "fixtures_separated_from_live",
            "ok": all(not (rows.get(s) or {}).get("live_service") for s in required),
            "detail": {"note": "All fault scenarios in this accept run are integration fixtures."},
        }
    )

    passed = sum(1 for c in checks if c["ok"])
    return {
        "suite": "faults-accept",
        "passed": passed,
        "failed": len(checks) - passed,
        "ok": passed == len(checks),
        "checks": checks,
        "matrix_paths": {
            "json": published.get("json_path"),
            "md": published.get("md_path"),
        },
        "note": "Deterministic local fault injection; no hosted CI required.",
    }
