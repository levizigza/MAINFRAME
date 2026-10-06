"""Trust lifecycle: untrusted → reviewed → tested → accepted; rollback support."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mainframe.promote.runner import run_promoted
from mainframe.promote.types import PromotedProgram


def mark_reviewed(program: PromotedProgram, *, note: str = "") -> PromotedProgram:
    if program.trust == "untrusted":
        program.trust = "reviewed"
    program.review_notes.append(note or "Human reviewed generated program and metadata.")
    _persist(program)
    return program


def run_varied_tests(
    program: PromotedProgram,
    cases: list[dict[str, Any]],
    *,
    work_dir: Path,
) -> dict[str, Any]:
    """
    Test against varied inputs and failure cases.
    A single success is insufficient — require >=2 valid passes and >=1 safe rejection.
    """
    results: list[dict[str, Any]] = []
    valid_passes = 0
    safe_rejects = 0

    for i, case in enumerate(cases):
        kind = case.get("kind") or "valid"
        payload = case.get("payload") or {}
        sub = work_dir / f"case_{i}_{kind}"
        # Harness may run while reviewed (not yet tested)
        out = run_promoted(program, payload, work_dir=sub, require_trust=False)
        expected_ok = case.get("expect_ok", kind == "valid")
        match = bool(out.get("ok")) == bool(expected_ok)
        if kind == "valid" and out.get("ok"):
            valid_passes += 1
        if kind in ("invalid", "out_of_contract") and out.get("rejected_safely"):
            safe_rejects += 1
        results.append(
            {
                "case": case.get("id") or f"case_{i}",
                "kind": kind,
                "expect_ok": expected_ok,
                "ok": out.get("ok"),
                "match": match,
                "model_calls": out.get("model_calls"),
                "model_calls_avoided": out.get("model_calls_avoided"),
                "error": out.get("error"),
                "rejected_safely": out.get("rejected_safely"),
            }
        )

    program.test_results = results
    enough = valid_passes >= 2 and safe_rejects >= 1 and all(r["match"] for r in results)
    if enough and program.trust in ("reviewed", "tested", "untrusted"):
        # Still require review first for accepted path
        if program.trust == "untrusted":
            program.review_notes.append("Tests ran but trust remains untrusted until review.")
        else:
            program.trust = "tested"
    _persist(program)
    return {
        "ok": enough,
        "valid_passes": valid_passes,
        "safe_rejects": safe_rejects,
        "results": results,
        "trust": program.trust,
        "generality_claim": False,
        "note": "Multiple varied inputs required; one success is not generality.",
    }


def mark_accepted(program: PromotedProgram) -> PromotedProgram:
    if program.trust != "tested":
        raise ValueError("must_be_tested_before_accepted")
    program.trust = "accepted"
    program.generality_claim = False
    program.review_notes.append("Accepted for reuse under recorded supported_conditions only.")
    _persist(program)
    return program


def rollback_to(previous_meta_path: Path) -> PromotedProgram:
    data = json.loads(Path(previous_meta_path).read_text(encoding="utf-8"))
    prog = PromotedProgram(**data)
    prog.review_notes.append(f"Rolled back to version {prog.version} via {previous_meta_path}")
    return prog


def _persist(program: PromotedProgram) -> None:
    if program.metadata_path:
        Path(program.metadata_path).write_text(
            json.dumps(program.to_dict(), indent=2) + "\n", encoding="utf-8"
        )
