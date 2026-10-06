"""Publish failure matrix: expected vs actual recovery (fixtures separate from live)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mainframe.config import ROOT
from mainframe.faults.scenarios import run_all_fault_scenarios

MATRIX_DIR = ROOT / "docs" / "eval" / "faults"


def build_matrix(rows: list[dict[str, Any]]) -> dict[str, Any]:
    critical_fails = []
    for r in rows:
        if not r.get("pass"):
            for tag in r.get("fixes_required_if_fail") or []:
                critical_fails.append({"scenario": r["id"], "category": tag})

    live = [r for r in rows if r.get("live_service")]
    fixtures = [r for r in rows if not r.get("live_service")]

    return {
        "kind": "failure_matrix",
        "hosting": "local_deterministic_no_hosted_ci",
        "integration_fixtures": len(fixtures),
        "live_observations": len(live),
        "live_note": (
            "Live service observations are recorded separately when eligible; "
            "this matrix run uses integration fixtures only."
        ),
        "passed": sum(1 for r in rows if r.get("pass")),
        "failed": sum(1 for r in rows if not r.get("pass")),
        "critical_failures": critical_fails,
        "gate_before_more_connectors": {
            "data_loss": not any(c["category"] == "data_loss" for c in critical_fails),
            "duplicate_effects": not any(c["category"] == "duplicate_effects" for c in critical_fails),
            "unauthorized_actions": not any(
                c["category"] == "unauthorized_actions" for c in critical_fails
            ),
            "paid_fallback": not any(c["category"] == "paid_fallback" for c in critical_fails),
            "allow_more_connectors": len(critical_fails) == 0,
        },
        "rows": [
            {
                "scenario": r["id"],
                "class": r.get("class"),
                "live_service": r.get("live_service"),
                "expected_recovery": r.get("expected_recovery"),
                "actual_recovery": r.get("actual_recovery"),
                "pass": r.get("pass"),
            }
            for r in rows
        ],
    }


def matrix_markdown(matrix: dict[str, Any]) -> str:
    lines = [
        "# Failure matrix — fault injection (local deterministic)",
        "",
        "Integration fixtures only. Live service observations are separate and must not be fabricated.",
        "",
        f"- Passed: **{matrix['passed']}** / Failed: **{matrix['failed']}**",
        f"- Hosting: `{matrix['hosting']}`",
        f"- Allow more connectors: **{matrix['gate_before_more_connectors']['allow_more_connectors']}**",
        "",
        "| Scenario | Class | Expected recovery | Actual recovery | Pass |",
        "|----------|-------|-------------------|-----------------|------|",
    ]
    for r in matrix["rows"]:
        lines.append(
            f"| `{r['scenario']}` | {r['class']} | `{r['expected_recovery']}` | "
            f"`{r['actual_recovery']}` | {'PASS' if r['pass'] else 'FAIL'} |"
        )
    lines.extend(
        [
            "",
            "## Connector gate",
            "",
            "Fix data loss, duplicate effects, unauthorized actions, and paid fallback paths "
            "before adding more connectors.",
            "",
            "```json",
            json.dumps(matrix["gate_before_more_connectors"], indent=2),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def publish_failure_matrix(*, work: Path | None = None) -> dict[str, Any]:
    rows = run_all_fault_scenarios(work=work)
    matrix = build_matrix(rows)
    MATRIX_DIR.mkdir(parents=True, exist_ok=True)
    json_path = MATRIX_DIR / "FAILURE_MATRIX.json"
    md_path = MATRIX_DIR / "FAILURE_MATRIX.md"
    json_path.write_text(json.dumps(matrix, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(matrix_markdown(matrix), encoding="utf-8")
    return {
        "ok": matrix["failed"] == 0 and matrix["gate_before_more_connectors"]["allow_more_connectors"],
        "matrix": matrix,
        "json_path": str(json_path.relative_to(ROOT)).replace("\\", "/"),
        "md_path": str(md_path.relative_to(ROOT)).replace("\\", "/"),
        "rows": rows,
    }
