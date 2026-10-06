"""Acceptance: edge miss, preexisting failure, invalidate after code change."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from mainframe.config import ROOT
from mainframe.contracts.build import build_contract
from mainframe.verify.binding import binding_still_valid
from mainframe.verify.edge_cases import derive_edge_cases
from mainframe.verify.integrity import detect_integrity_violations, snapshot_tests
from mainframe.verify.pipeline import save_binding, verify_repair
from mainframe.verify.runner import reproduce_failure

LAB = ROOT / "docs" / "verify" / "fixtures" / "repair_lab"
EVAL = ROOT / "docs" / "verify" / "fixtures" / "evaluator_owned"
WORK = ROOT / ".mainframe" / "verify_work" / "repair_lab"


def _prep_work(mathlib_src: Path) -> Path:
    if WORK.exists():
        shutil.rmtree(WORK, ignore_errors=True)
    shutil.copytree(LAB, WORK)
    # overwrite mathlib with chosen variant
    shutil.copyfile(mathlib_src, WORK / "mathlib.py")
    return WORK


def run_verify_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    contract_built = build_contract(
        "Repair total() so it returns the sum of numbers; empty list yields 0; "
        "support negatives. Example: total([1,2])==3."
    )
    contract = contract_built["contract"]
    edges = derive_edge_cases(contract)
    checks.append(
        {
            "id": "edges_from_contract_not_only_impl",
            "ok": any(e["id"] == "empty_input" for e in edges)
            and all(e.get("source") != "proposed_implementation" for e in edges),
            "detail": edges,
        }
    )

    # --- Preexisting failure on buggy code ---
    work = _prep_work(LAB / "mathlib.py")
    pre = reproduce_failure(
        work,
        test_target="tests/test_example.py",
        pythonpath=str(work),
    )
    checks.append(
        {
            "id": "identify_preexisting_failure",
            "ok": (
                pre.get("reproduced") is True
                and (pre.get("classification") or {}).get("kind") == "preexisting_failure"
            ),
            "detail": pre,
        }
    )

    # --- Patch fixes example only → edge catch ---
    work = _prep_work(LAB / "mathlib_example_only.py")
    before_tests = snapshot_tests(work / "tests")
    report = verify_repair(
        work,
        contract=contract,
        code_paths=["mathlib.py"],
        example_tests=[str(work / "tests" / "test_example.py")],
        evaluator_tests=[str(EVAL / "test_contract_edges.py")],
        risk="medium",
        tests_before=before_tests,
    )
    edge_phase = next(
        (p for p in report.get("phases") or [] if p.get("phase") == "evaluator_edge_cases"),
        {},
    )
    checks.append(
        {
            "id": "catch_example_fix_edge_fail",
            "ok": (
                report.get("ok") is False
                and report.get("blocking") == "edge_case"
                and (edge_phase.get("classification") or {}).get("kind") == "edge_case_failure"
                and edge_phase.get("owned_outside_target") is True
            ),
            "detail": {
                "blocking": report.get("blocking"),
                "edge_class": edge_phase.get("classification"),
                "example_ok": next(
                    (
                        p.get("run", {}).get("ok")
                        for p in report.get("phases") or []
                        if p.get("phase") == "targeted_tests"
                    ),
                    None,
                ),
            },
        }
    )

    # Evaluator path is outside WORK
    checks.append(
        {
            "id": "evaluator_checks_outside_editable",
            "ok": not str(EVAL.resolve()).startswith(str(work.resolve())),
            "detail": {"eval": str(EVAL), "work": str(work)},
        }
    )

    # --- Integrity: weakened asserts without spec ---
    weak_before = {
        "test_example.py": {"assert_count": 3, "test_fns": ["test_a", "test_b", "test_c"], "sha256": "x"}
    }
    weak_after = {
        "test_example.py": {"assert_count": 1, "test_fns": ["test_a"], "sha256": "y"}
    }
    integ = detect_integrity_violations(weak_before, weak_after, spec_traces=[])
    integ_ok = detect_integrity_violations(
        weak_before,
        weak_after,
        spec_traces=["User asked to delete test_b and weaken asserts for legacy mode"],
    )
    checks.append(
        {
            "id": "detect_weakened_asserts_without_spec",
            "ok": integ.get("ok") is False and integ_ok.get("ok") is True,
            "detail": {"blocked": integ, "allowed": integ_ok},
        }
    )

    # --- Real fix passes; then invalidate after code change ---
    good = '''def total(nums):
    if not nums:
        return 0
    return sum(nums)
'''
    work = _prep_work(LAB / "mathlib.py")
    (work / "mathlib.py").write_text(good, encoding="utf-8")
    before_tests = snapshot_tests(work / "tests")
    good_report = verify_repair(
        work,
        contract=contract,
        code_paths=["mathlib.py"],
        example_tests=[str(work / "tests" / "test_example.py")],
        evaluator_tests=[str(EVAL / "test_contract_edges.py")],
        risk="low",
        tests_before=before_tests,
    )
    binding = good_report.get("binding") or {}
    save_binding(binding, name="accept_good")
    checks.append(
        {
            "id": "good_fix_passes_edges",
            "ok": good_report.get("ok") is True and bool(binding.get("code_hashes")),
            "detail": {
                "ok": good_report.get("ok"),
                "binding_id": binding.get("binding_id"),
                "env": binding.get("environment"),
            },
        }
    )

    # Relevant code change invalidates
    (work / "mathlib.py").write_text(
        good + "\n# tweak\n", encoding="utf-8"
    )
    validity = binding_still_valid(work, binding)
    checks.append(
        {
            "id": "invalidate_after_relevant_code_change",
            "ok": validity.get("stale") is True and validity.get("valid") is False,
            "detail": validity,
        }
    )

    passed = sum(1 for c in checks if c["ok"])
    failed = len(checks) - passed
    return {
        "ok": failed == 0,
        "passed": passed,
        "failed": failed,
        "checks": checks,
    }
