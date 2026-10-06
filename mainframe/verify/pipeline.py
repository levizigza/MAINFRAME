"""Verification pipeline — reproduce, integrity, evaluator-owned edges, binding."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mainframe.config import STATE_DIR, ensure_state
from mainframe.cost_gate import authorize
from mainframe.verify.binding import bind_result, binding_still_valid
from mainframe.verify.edge_cases import derive_edge_cases
from mainframe.verify.integrity import detect_integrity_violations, snapshot_tests
from mainframe.verify.runner import (
    reproduce_failure,
    run_regression,
    run_targeted,
    run_typecheck,
)
from mainframe.verify.taxonomy import classify_run_failure


def evaluator_dir() -> Path:
    """Evaluator-owned checks live outside editable target workspaces."""
    ensure_state()
    d = STATE_DIR / "evaluator_checks"
    d.mkdir(parents=True, exist_ok=True)
    return d


def verify_repair(
    target_root: Path,
    *,
    contract: dict[str, Any],
    code_paths: list[str],
    example_tests: list[str],
    evaluator_tests: list[str],
    risk: str = "medium",
    spec_traces: list[str] | None = None,
    tests_before: dict[str, dict[str, Any]] | None = None,
    prior_binding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Full verification flow:

    1) Invalidate prior binding if code drifted
    2) Reproduce failure on example tests (preexisting)
    3) Integrity check vs test snapshot
    4) After repair assumed on disk: targeted example + evaluator edge tests
    5) Typecheck + risk regression
    6) Bind results to code+environment
    """
    gate = authorize("tool", "local.verify_repair", local=True)
    if not gate.allowed:
        return {"ok": False, "cost_gate": gate.to_dict()}

    target_root = target_root.resolve()
    edges = derive_edge_cases(contract)
    report: dict[str, Any] = {
        "ok": False,
        "contract_edges": edges,
        "phases": [],
        "evaluator_outside_workspace": True,
    }

    if prior_binding:
        validity = binding_still_valid(target_root, prior_binding)
        report["prior_binding"] = validity
        if validity.get("stale"):
            report["phases"].append(
                {
                    "phase": "invalidate_prior",
                    "classification": {
                        "kind": "stale_verification",
                        "product_defect": False,
                        "detail": "Relevant code changed since last verification",
                    },
                    "validity": validity,
                }
            )

    # Integrity: workspace tests must not be weakened to fake a pass
    tests_root = target_root / "tests"
    if not tests_root.is_dir():
        tests_root = target_root
    after_snap = snapshot_tests(tests_root)
    if tests_before is not None:
        integ = detect_integrity_violations(
            tests_before, after_snap, spec_traces=spec_traces or [contract.get("intent_natural_language") or ""]
        )
        report["phases"].append({"phase": "integrity", **integ})
        if not integ.get("ok"):
            report["ok"] = False
            report["blocking"] = "integrity_violation"
            report["classification"] = {
                "kind": "integrity_violation",
                "product_defect": False,
                "detail": "Assertions weakened or tests deleted without spec trace",
            }
            report["binding"] = bind_result(
                root=target_root,
                code_paths=code_paths,
                phase="integrity_fail",
                checks=report["phases"],
            )
            return report

    # Reproduce before repair (example tests) — caller may have already patched;
    # still useful when pre_repair flag set via optional pre_repair_root... For accept
    # we call reproduce explicitly in accept. Here we run example + evaluator as post.
    py_path = str(target_root)

    example = run_targeted(
        target_root,
        example_tests,
        pythonpath=py_path,
    )
    # Mark edge vs example
    if not example["run"].get("ok"):
        example["classification"] = classify_run_failure(
            exit_code=example["run"].get("exit_code"),
            stdout=example["run"].get("stdout") or "",
            stderr=example["run"].get("stderr") or "",
            error=example["run"].get("error"),
        )
    report["phases"].append(example)

    # Evaluator-owned tests: paths are absolute under evaluator store / fixture outside target
    edge = run_targeted(
        Path(evaluator_tests[0]).resolve().parent if evaluator_tests else target_root,
        evaluator_tests,
        pythonpath=py_path,
    )
    if not edge["run"].get("ok"):
        # Prefer edge_case_failure label when contract derived edges exist
        base = classify_run_failure(
            exit_code=edge["run"].get("exit_code"),
            stdout=edge["run"].get("stdout") or "",
            stderr=edge["run"].get("stderr") or "",
            error=edge["run"].get("error"),
        )
        if base.get("product_defect") and edges:
            base = {
                "kind": "edge_case_failure",
                "product_defect": True,
                "detail": "Failed evaluator-owned edge case derived from contract",
                "edges": [e["id"] for e in edges],
            }
        edge["classification"] = base
    report["phases"].append({**edge, "phase": "evaluator_edge_cases", "owned_outside_target": True})

    types = run_typecheck(target_root, code_paths)
    report["phases"].append(types)

    regress = run_regression(
        target_root,
        risk=risk,
        smoke_paths=example_tests,
        full_paths=example_tests + ([] if risk == "low" else evaluator_tests[:1]),
        pythonpath=py_path,
    )
    report["phases"].append(regress)

    # Overall ok: example + edge must pass; integrity already handled; typecheck soft if skipped
    example_ok = example["run"].get("ok")
    edge_ok = edge["run"].get("ok")
    type_ok = types.get("skipped") or types["run"].get("ok")
    report["ok"] = bool(example_ok and edge_ok and type_ok)
    if not example_ok:
        report["blocking"] = "example_tests"
    elif not edge_ok:
        report["blocking"] = "edge_case"
        report["classification"] = edge.get("classification")
    elif not type_ok:
        report["blocking"] = "typecheck"

    report["binding"] = bind_result(
        root=target_root,
        code_paths=code_paths,
        phase="post_repair_verify",
        checks=report["phases"],
        contract_id=str(contract.get("intent_natural_language", ""))[:80],
    )
    return report


def save_binding(binding: dict[str, Any], name: str = "last") -> Path:
    ensure_state()
    path = STATE_DIR / "verify_bindings" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(binding, indent=2) + "\n", encoding="utf-8")
    return path
