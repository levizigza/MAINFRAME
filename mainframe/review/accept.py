"""Acceptance: seeded defect detected with evidence; no-gain routes disabled."""

from __future__ import annotations

import difflib
import shutil
from pathlib import Path
from typing import Any

from mainframe.config import ROOT
from mainframe.review.alternative import cleanup_worktree, create_isolated_worktree
from mainframe.review.deterministic import run_deterministic_checks
from mainframe.review.gate import review_gate
from mainframe.review.pipeline import review_changes
from mainframe.review.rank import rank_candidates
from mainframe.review.routes import disabled_no_gain_routes, select_route
from mainframe.review.reviewer import fixture_review
from mainframe.review.packet import build_review_packet

FIX = ROOT / "docs" / "review" / "fixtures" / "seeded_defect"
WORK = ROOT / ".mainframe" / "review_work"


def _prep() -> Path:
    dest = WORK / "seeded_defect"
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(FIX, dest)
    return dest


def _seeded_diff(workspace: Path) -> list[str]:
    """Unified diff as if an author 'fixed' by introducing the seeded off-by-one."""
    good = '''def summarize(values):
    parts = []
    for i in range(len(values)):
        parts.append(str(values[i]))
    return ";".join(parts)
'''
    bad = (workspace / "summarize.py").read_text(encoding="utf-8")
    # Diff from good → bad (the defective change)
    lines = list(
        difflib.unified_diff(
            good.splitlines(keepends=True),
            # Only the summarize function region — use full file as "new"
            bad.splitlines(keepends=True),
            fromfile="a/summarize.py",
            tofile="b/summarize.py",
        )
    )
    return ["".join(lines)]


def run_review_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    # --- Disabled no-gain routes ---
    disabled = disabled_no_gain_routes()
    ids = {d["route_id"] for d in disabled}
    always = select_route("always_model_review")
    swarm = select_route("swarm_review")
    majority = select_route("majority_vote_rank")
    ok_route = select_route("deterministic_first_gated")
    checks.append(
        {
            "id": "no_gain_routes_disabled",
            "ok": (
                "always_model_review" in ids
                and "swarm_review" in ids
                and "majority_vote_rank" in ids
                and always.get("refused") == "always_model_review"
                and swarm.get("refused") == "swarm_review"
                and majority.get("refused") == "majority_vote_rank"
                and ok_route.get("selected") == "deterministic_first_gated"
                and all(d.get("measured_improvement") is False for d in disabled)
            ),
            "detail": {"disabled": sorted(ids), "fallback": ok_route.get("selected")},
        }
    )

    ws = _prep()
    det = run_deterministic_checks(ws, changed_paths=["summarize.py"])
    # Tests pass (happy path) — deterministic green for syntax/tests as written
    checks.append(
        {
            "id": "deterministic_runs_first_and_can_be_green",
            "ok": det.get("ok") is True and det.get("model_used") is False,
            "detail": {"findings": det.get("findings"), "test_ok": (det.get("test_run") or {}).get("ok")},
        }
    )

    gate_normal = review_gate(deterministic=det, impact="normal")
    gate_high = review_gate(deterministic=det, impact="high", prior_review_helped=True)
    checks.append(
        {
            "id": "gate_skips_model_when_no_measured_benefit",
            "ok": (
                gate_normal.get("invoke_model_review") is False
                and gate_normal.get("quota_justified") is False
                and gate_high.get("invoke_model_review") is True
                and gate_high.get("quota_justified") is True
            ),
            "detail": {"normal": gate_normal, "high": gate_high},
        }
    )

    diffs = _seeded_diff(ws)
    packet = build_review_packet(
        contract={"kind": "repair", "goal": "summarize joins all values"},
        unified_diffs=diffs,
        relevant_context={"paths": ["summarize.py"]},
        deterministic_results=det,
        human_requirements=["include all elements", "handle empty safely"],
        patch_author_model_id="fixture_local/fixture-coder@1.0.0",
        reviewer_model_id="fixture_local/fixture-coder-reviewer@1.0.0",
    )
    checks.append(
        {
            "id": "packet_has_contract_diff_context_results_and_asks",
            "ok": (
                packet.get("task_contract") is not None
                and packet["diff"]["unified"]
                and packet.get("deterministic_results") is det
                and "specific_counterexamples" in packet["ask_for"]
                and "unsupported_assumptions" in packet["ask_for"]
                and packet["separated_from_patch_generation"] is True
                and packet["lineage"]["shared_blind_spot_risk"] is True
            ),
            "detail": {
                "ask_for": packet["ask_for"],
                "lineage": packet["lineage"],
            },
        }
    )

    rev = fixture_review(packet)
    checks.append(
        {
            "id": "review_detects_seeded_defect_with_evidence",
            "ok": (
                rev.get("ok") is False
                and rev.get("patch_generated") is False
                and any(d["id"] == "off_by_one_upper_bound" for d in rev["defects_found"])
                and any(d["id"] == "todo_seeded_defect" for d in rev["defects_found"])
                and all(e.get("reproducible") for e in rev["reproducible_evidence"])
                and len(rev["counterexamples"]) >= 1
                and len(rev["unsupported_assumptions"]) >= 1
            ),
            "detail": {
                "defects": [d["id"] for d in rev["defects_found"]],
                "evidence": rev["reproducible_evidence"],
                "counterexamples": rev["counterexamples"],
            },
        }
    )

    # Pipeline e2e under high impact
    report = review_changes(
        ws,
        goal="Repair summarize to join all values with ';'.",
        unified_diffs=diffs,
        changed_paths=["summarize.py"],
        impact="high",
        prior_review_helped=True,
        human_requirements=["include all elements"],
        patch_author_model_id="fixture_local/same-lineage@1",
        reviewer_model_id="fixture_local/same-lineage@2",
    )
    checks.append(
        {
            "id": "pipeline_gated_review_finds_seed",
            "ok": (
                report.get("swarm") is False
                and report.get("majority_vote") is False
                and report.get("gate", {}).get("invoke_model_review") is True
                and any(
                    d.get("id") == "off_by_one_upper_bound"
                    for d in (report.get("defects_found") or [])
                )
                and (report.get("review") or {}).get("separated_from_patch_generation") is True
            ),
            "detail": {
                "gate": report.get("gate"),
                "defects": [d.get("id") for d in report.get("defects_found") or []],
            },
        }
    )

    # Ranking ≠ majority vote
    ranking = rank_candidates(
        [
            {
                "id": "weak_popular",
                "evaluator_results": [
                    {"id": "deterministic", "ok": False},
                    {"id": "review_clean", "ok": False},
                ],
                "satisfies_requirements": [],
                "quota_tokens": 0,
                "votes": 99,
            },
            {
                "id": "strong_checks",
                "evaluator_results": [
                    {"id": "deterministic", "ok": True},
                    {"id": "review_clean", "ok": True},
                ],
                "satisfies_requirements": ["include all elements", "handle empty safely"],
                "quota_tokens": 10,
            },
        ],
        evaluator_checks=[{"id": "deterministic"}, {"id": "review_clean"}],
        human_requirements=["include all elements", "handle empty safely"],
    )
    checks.append(
        {
            "id": "rank_by_evaluator_not_majority",
            "ok": (
                ranking.get("majority_vote") is False
                and ranking.get("winner") == "strong_checks"
                and ranking["ranked"][0]["id"] == "strong_checks"
            ),
            "detail": ranking,
        }
    )

    # Isolated worktree alternative (bounded)
    wt = create_isolated_worktree(ws, label="accept-alt")
    alt_path = Path(wt["path"])
    # Apply a real fix in the alternative
    fixed = '''def summarize(values):
    parts = []
    for i in range(len(values)):
        parts.append(str(values[i]))
    return ";".join(parts)


def average(values):
    if not values:
        return 0.0
    return sum(values) / len(values)
'''
    (alt_path / "summarize.py").write_text(fixed, encoding="utf-8")
    # Counterexample now passes if we fixed off-by-one — rewrite tests in alt
    (alt_path / "tests" / "test_summarize.py").write_text(
        "import summarize\n\n"
        "def test_summarize_all():\n"
        '    assert summarize.summarize(["a", "b", "c"]) == "a;b;c"\n\n'
        "def test_average_two():\n"
        "    assert summarize.average([2, 4]) == 3.0\n\n"
        "def test_average_empty():\n"
        "    assert summarize.average([]) == 0.0\n",
        encoding="utf-8",
    )
    alt_det2 = run_deterministic_checks(alt_path, changed_paths=["summarize.py"])

    def apply_alt(p: Path) -> dict[str, Any]:
        return {
            "ok": True,
            "satisfies_requirements": ["include all elements", "handle empty safely"],
            "quota_tokens": 5,
            "path": str(p),
        }

    pipe_alt = review_changes(
        ws,
        goal="High value summarize fix",
        unified_diffs=diffs,
        changed_paths=["summarize.py"],
        impact="critical",
        unresolved_high_value=True,
        human_requirements=["include all elements", "handle empty safely"],
        alternative_fn=apply_alt,
        cleanup_alt=True,
    )
    checks.append(
        {
            "id": "bounded_alternative_isolated_worktree",
            "ok": (
                wt.get("isolated") is True
                and wt.get("ok") is True
                and alt_det2.get("ok") is True
                and pipe_alt.get("alternative") is not None
                and pipe_alt["alternative"].get("swarm") is False
                and pipe_alt["alternative"].get("alternatives_n") == 1
                and (pipe_alt.get("ranking") or {}).get("majority_vote") is False
                and (pipe_alt.get("ranking") or {}).get("winner") == "alternative"
            ),
            "detail": {
                "worktree_method": wt.get("method"),
                "alt_det_ok": alt_det2.get("ok"),
                "ranking": pipe_alt.get("ranking"),
                "alternatives_n": (pipe_alt.get("alternative") or {}).get("alternatives_n"),
            },
        }
    )
    cleanup_worktree(wt)

    # Refusing swarm route explicitly
    refused = review_changes(
        ws,
        goal="x",
        unified_diffs=diffs,
        route="swarm_review",
        impact="high",
    )
    checks.append(
        {
            "id": "swarm_route_refused_falls_back_eligible",
            "ok": (
                refused.get("route", {}).get("refused") == "swarm_review"
                and refused.get("route", {}).get("selected") == "deterministic_first_gated"
                and refused.get("swarm") is False
            ),
            "detail": refused.get("route"),
        }
    )

    passed = sum(1 for c in checks if c["ok"])
    failed = len(checks) - passed
    return {"ok": failed == 0, "passed": passed, "failed": failed, "checks": checks}
