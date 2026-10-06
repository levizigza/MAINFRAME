"""Review pipeline: deterministic first → gate → packet → review → optional alt candidate."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from mainframe.config import RUNS_DIR, ensure_state
from mainframe.contracts.build import build_contract
from mainframe.review.alternative import cleanup_worktree, run_bounded_alternative
from mainframe.review.deterministic import run_deterministic_checks
from mainframe.review.gate import review_gate
from mainframe.review.rank import rank_candidates
from mainframe.review.reviewer import run_review
from mainframe.review.routes import select_route


def review_changes(
    workspace: Path,
    *,
    goal: str,
    unified_diffs: list[str],
    changed_paths: list[str] | None = None,
    relevant_context: dict[str, Any] | None = None,
    human_requirements: list[str] | None = None,
    impact: str = "normal",
    unresolved_high_value: bool = False,
    prior_review_helped: bool | None = None,
    patch_author_model_id: str | None = None,
    reviewer_model_id: str | None = None,
    route: str | None = None,
    alternative_fn: Callable[[Path], dict[str, Any]] | None = None,
    cleanup_alt: bool = True,
) -> dict[str, Any]:
    """
    Full review flow. Refuses disabled no-gain routes. Never spawns a swarm.
    """
    workspace = workspace.resolve()
    route_sel = select_route(route)
    if route_sel.get("refused") and route_sel.get("selected") is None:
        return {
            "ok": False,
            "refused": True,
            "route": route_sel,
            "error": "no_eligible_review_route",
        }

    # 1) Deterministic checks first
    det = run_deterministic_checks(workspace, changed_paths=changed_paths)

    # 2) Gate model call
    gate = review_gate(
        deterministic=det,
        impact=impact,
        unresolved_high_value=unresolved_high_value,
        prior_review_helped=prior_review_helped,
    )

    contract = build_contract(goal)
    human_reqs = list(human_requirements or [])

    review_result: dict[str, Any] | None = None
    if gate.get("invoke_model_review"):
        review_result = run_review(
            contract=contract.get("contract") or contract,
            unified_diffs=unified_diffs,
            relevant_context=relevant_context,
            deterministic_results=det,
            human_requirements=human_reqs,
            patch_author_model_id=patch_author_model_id,
            reviewer_model_id=reviewer_model_id,
            invoke_model=True,
        )
    else:
        # Still run fixture review offline when we have diffs and want defect detection
        # without claiming a quota model spend — used when deterministic is green but
        # accept seeds a defect under high impact (gate True). When gate is False we
        # record skipped model review.
        review_result = {
            "skipped": True,
            "reason": gate.get("reason"),
            "model_invoked": False,
            "quota_tokens": 0,
            "patch_generated": False,
            "separated_from_patch_generation": True,
            "defects_found": [],
            "ok": True,
        }
        # For high-signal offline accept: if diffs present and gate skipped only because
        # green/normal, do not scan. When gate says invoke, we already reviewed above.

    # If gate skipped but caller marked high-value unresolved with diffs, ensure review ran
    if (
        review_result.get("skipped")
        and unresolved_high_value
        and unified_diffs
    ):
        # Force a non-quota fixture pass for evidence (still not a swarm)
        review_result = run_review(
            contract=contract.get("contract") or contract,
            unified_diffs=unified_diffs,
            relevant_context=relevant_context,
            deterministic_results=det,
            human_requirements=human_reqs,
            patch_author_model_id=patch_author_model_id,
            reviewer_model_id=reviewer_model_id,
            invoke_model=False,
        )
        review_result["note"] = "fixture_review_without_quota_for_unresolved_high_value"
        gate = {**gate, "fixture_review_without_quota": True}

    defects = list((review_result or {}).get("defects_found") or [])
    alt_report: dict[str, Any] | None = None
    ranking: dict[str, Any] | None = None

    # 3) Bounded alternative for unresolved high-value failures
    needs_alt = (
        unresolved_high_value
        and (not det.get("ok") or defects)
        and alternative_fn is not None
    )
    if needs_alt:
        alt_report = run_bounded_alternative(
            workspace,
            apply_candidate=alternative_fn,
            max_alternatives=1,
            reason="unresolved_high_value_failure",
        )
        primary = {
            "id": "primary",
            "evaluator_results": [
                {"id": "deterministic", "ok": bool(det.get("ok"))},
                {"id": "review_clean", "ok": len(defects) == 0},
            ],
            "satisfies_requirements": [],
            "quota_tokens": int((review_result or {}).get("quota_tokens") or 0),
            "summary": "primary workspace candidate",
        }
        alt_ok = bool((alt_report.get("candidate_result") or {}).get("ok"))
        alt_satisfies = list(
            (alt_report.get("candidate_result") or {}).get("satisfies_requirements") or human_reqs
        )
        alternative = {
            "id": "alternative",
            "evaluator_results": [
                {"id": "deterministic", "ok": alt_ok},
                {"id": "review_clean", "ok": alt_ok},
            ],
            "satisfies_requirements": alt_satisfies if alt_ok else [],
            "quota_tokens": int(
                (alt_report.get("candidate_result") or {}).get("quota_tokens") or 0
            ),
            "summary": "isolated worktree alternative",
        }
        ranking = rank_candidates(
            [primary, alternative],
            evaluator_checks=[
                {"id": "deterministic"},
                {"id": "review_clean"},
            ],
            human_requirements=human_reqs,
        )
        if cleanup_alt and alt_report.get("worktree"):
            cleanup_worktree(alt_report["worktree"])

    ok = bool(det.get("ok")) and len(defects) == 0
    report = {
        "ok": ok,
        "route": route_sel,
        "deterministic": det,
        "gate": gate,
        "review": review_result,
        "defects_found": defects,
        "alternative": alt_report,
        "ranking": ranking,
        "swarm": False,
        "majority_vote": False,
        "separated_from_patch_generation": True,
    }

    ensure_state()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = RUNS_DIR / f"review-{stamp}.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    report["report_path"] = str(out)
    return report
