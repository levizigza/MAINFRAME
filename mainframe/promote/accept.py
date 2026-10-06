"""Acceptance: promote reporting (or website) demo; varied inputs; measure avoided calls; reject OOC."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from mainframe.config import ROOT
from mainframe.promote.generate import promote_trace
from mainframe.promote.runner import run_promoted
from mainframe.promote.trace import build_reporting_trace, build_website_trace, save_trace
from mainframe.promote.trust import mark_accepted, mark_reviewed, run_varied_tests

FIXTURES = ROOT / "docs" / "demo" / "fixtures"


def run_promote_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="promote_accept_") as tmp:
        work = Path(tmp)

        # --- Promote reporting demo ---
        trace = build_reporting_trace()
        save_trace(trace, work / "traces" / "reporting.json")
        prog = promote_trace(trace, out_dir=work / "programs")

        checks.append(
            {
                "id": "promote_untrusted_until_reviewed",
                "ok": bool(
                    prog.trust == "untrusted"
                    and prog.generality_claim is False
                    and prog.model_calls_avoided == 2
                    and prog.model_calls_in_program == 0
                    and prog.program_path
                    and prog.metadata_path
                    and any("untrusted" in n.lower() for n in prog.review_notes)
                ),
                "detail": {
                    "trust": prog.trust,
                    "avoided": prog.model_calls_avoided,
                    "source_calls": prog.model_calls_in_source,
                    "steps": [s["id"] for s in prog.steps],
                    "removed_ai": [s["id"] for s in prog.steps if s.get("kind") == "ai"],
                },
            }
        )

        # Removable AI gone; only deterministic steps remain
        kinds = {s["kind"] for s in prog.steps}
        checks.append(
            {
                "id": "remove_unnecessary_model_decisions",
                "ok": kinds == {"deterministic"} and all(
                    s["id"] != "ai_choose_title" and s["id"] != "ai_summarize" for s in prog.steps
                ),
                "detail": {"step_kinds": sorted(kinds), "step_ids": [s["id"] for s in prog.steps]},
            }
        )

        # Metadata: conditions, permissions, source, version, rollback slot
        checks.append(
            {
                "id": "record_conditions_permissions_source_version",
                "ok": bool(
                    prog.source_trace_id == trace.trace_id
                    and prog.permissions
                    and prog.supported_conditions.get("input_schema")
                    and prog.version == "1"
                    and prog.rollback_path is None  # first version
                ),
                "detail": {
                    "source_trace_id": prog.source_trace_id,
                    "permissions": prog.permissions,
                    "version": prog.version,
                    "supported_keys": sorted(prog.supported_conditions.keys()),
                },
            }
        )

        mark_reviewed(prog, note="Accept harness review of reporting promotion.")
        base = json.loads((FIXTURES / "records_report" / "records.json").read_text(encoding="utf-8"))
        cases = [
            {"id": "valid_a", "kind": "valid", "payload": {"records": base}, "expect_ok": True},
            {
                "id": "valid_b",
                "kind": "valid",
                "payload": {
                    "records": [
                        {"id": "x1", "label": "New", "value": 1},
                        {"id": "x2", "label": "Alt", "value": 2},
                        {"id": "x3", "label": "Third", "value": 3},
                    ]
                },
                "expect_ok": True,
            },
            {
                "id": "valid_c",
                "kind": "valid",
                "payload": {"records": [{"id": "solo", "label": "One", "value": 99}]},
                "expect_ok": True,
            },
            {
                "id": "ooc_extra_field",
                "kind": "out_of_contract",
                "payload": {"records": base, "unexpected_cloud_url": "https://evil.example"},
                "expect_ok": False,
            },
            {
                "id": "ooc_bad_row",
                "kind": "out_of_contract",
                "payload": {"records": [{"id": "z", "label": "no value"}]},
                "expect_ok": False,
            },
            {
                "id": "ooc_empty",
                "kind": "out_of_contract",
                "payload": {"records": []},
                "expect_ok": False,
            },
        ]
        tests = run_varied_tests(prog, cases, work_dir=work / "tests")
        checks.append(
            {
                "id": "varied_inputs_and_failure_cases",
                "ok": bool(
                    tests.get("ok")
                    and tests.get("valid_passes", 0) >= 3
                    and tests.get("safe_rejects", 0) >= 1
                    and prog.trust == "tested"
                ),
                "detail": tests,
            }
        )

        mark_accepted(prog)

        # Rerun on several new valid inputs; measure model calls avoided
        rerun_metrics = []
        for i, payload in enumerate(
            [
                {"records": [{"id": "n1", "label": "A", "value": 10}, {"id": "n2", "label": "B", "value": 20}]},
                {"records": [{"id": "n3", "label": "C", "value": 0}]},
                {
                    "records": [
                        {"id": f"r{j}", "label": f"L{j}", "value": j} for j in range(5)
                    ]
                },
            ]
        ):
            out = run_promoted(prog, payload, work_dir=work / f"rerun_{i}", require_trust=True)
            rerun_metrics.append(
                {
                    "ok": out.get("ok"),
                    "model_calls": out.get("model_calls"),
                    "model_calls_avoided": out.get("model_calls_avoided"),
                    "row_count": (out.get("outputs") or {}).get("report", {}).get("row_count")
                    if out.get("ok")
                    else None,
                }
            )
        checks.append(
            {
                "id": "rerun_new_inputs_zero_model_calls",
                "ok": bool(
                    len(rerun_metrics) >= 3
                    and all(m["ok"] for m in rerun_metrics)
                    and all(m["model_calls"] == 0 for m in rerun_metrics)
                    and all(m["model_calls_avoided"] == 2 for m in rerun_metrics)
                ),
                "detail": {"reruns": rerun_metrics, "source_model_calls": prog.model_calls_in_source},
            }
        )

        # Reject out-of-contract safely (no side effects / no artifact)
        ooc_dir = work / "ooc_final"
        ooc = run_promoted(
            prog,
            {"records": base, "hack": True},
            work_dir=ooc_dir,
            require_trust=True,
        )
        artifact_written = (ooc_dir / "report.json").is_file()
        checks.append(
            {
                "id": "reject_out_of_contract_safely",
                "ok": bool(
                    ooc.get("ok") is False
                    and ooc.get("rejected_safely") is True
                    and ooc.get("error") == "out_of_contract"
                    and artifact_written is False
                    and ooc.get("model_calls") == 0
                ),
                "detail": {"result": {k: ooc.get(k) for k in ("ok", "error", "rejected_safely", "model_calls", "contract")}, "artifact_written": artifact_written},
            }
        )

        # Version bump + rollback path recorded
        prog2 = promote_trace(trace, out_dir=work / "programs", previous=prog)
        checks.append(
            {
                "id": "version_and_rollback_path",
                "ok": bool(
                    prog2.version == "2"
                    and prog2.previous_version == "1"
                    and prog2.rollback_path
                    and Path(prog2.rollback_path).exists()
                ),
                "detail": {
                    "version": prog2.version,
                    "previous_version": prog2.previous_version,
                    "rollback_path": prog2.rollback_path,
                },
            }
        )

        # One success ≠ generality claim
        checks.append(
            {
                "id": "no_generality_claim_from_example",
                "ok": prog.generality_claim is False and prog2.generality_claim is False,
                "detail": {"note": trace.note},
            }
        )

        # Website promotion path (deterministic steps + explicit human; removable AI dropped)
        wtrace = build_website_trace()
        wprog = promote_trace(wtrace, out_dir=work / "programs_web")
        broken = (FIXTURES / "site_maintenance" / "index_broken.html").read_text(encoding="utf-8")
        mark_reviewed(wprog)
        wcases = [
            {"id": "web_valid", "kind": "valid", "payload": {"html_text": broken}, "expect_ok": True},
            {
                "id": "web_valid2",
                "kind": "valid",
                "payload": {"html_text": broken.replace("broken", "broken", 1)},
                "expect_ok": True,
            },
            {
                "id": "web_ooc",
                "kind": "out_of_contract",
                "payload": {"html_text": "<html><body>unrelated</body></html>", "extra": 1},
                "expect_ok": False,
            },
        ]
        # Fix OOC: additional property "extra" should fail; also unrelated html without anchor
        wcases[2] = {
            "id": "web_ooc",
            "kind": "out_of_contract",
            "payload": {"html_text": "<html><body>unrelated</body></html>"},
            "expect_ok": False,
        }
        wtests = run_varied_tests(wprog, wcases, work_dir=work / "web_tests")
        human_kept = any(s.get("kind") == "human" for s in wprog.steps)
        ai_removed = all(s.get("id") != "ai_diagnose" for s in wprog.steps)
        checks.append(
            {
                "id": "website_promote_keeps_human_drops_ai",
                "ok": bool(
                    wprog.model_calls_avoided == 1
                    and human_kept
                    and ai_removed
                    and wtests.get("valid_passes", 0) >= 2
                    and wtests.get("safe_rejects", 0) >= 1
                ),
                "detail": {
                    "steps": wprog.steps,
                    "tests": wtests,
                    "avoided": wprog.model_calls_avoided,
                },
            }
        )

    passed = sum(1 for c in checks if c["ok"])
    return {
        "suite": "promote-accept",
        "passed": passed,
        "failed": len(checks) - passed,
        "ok": passed == len(checks),
        "checks": checks,
        "note": "Promotion reuses tested behavior; not model training or free new reasoning.",
    }
