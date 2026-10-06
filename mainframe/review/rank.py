"""Rank alternative candidates by evaluator-owned checks + human requirements — not majority vote."""

from __future__ import annotations

from typing import Any


def rank_candidates(
    candidates: list[dict[str, Any]],
    *,
    evaluator_checks: list[dict[str, Any]],
    human_requirements: list[str],
) -> dict[str, Any]:
    """
    Score each candidate with evaluator-owned acceptance checks and human requirements.

    Majority vote among reviewers is explicitly *not* used.
    """
    scored: list[dict[str, Any]] = []
    for c in candidates:
        cid = c.get("id") or c.get("candidate_id") or "unknown"
        check_results = c.get("evaluator_results") or c.get("checks") or []
        # Prefer embedded per-candidate results; else apply shared evaluator_checks
        # that the candidate already recorded as pass/fail maps.
        passed = 0
        failed = 0
        failed_ids: list[str] = []
        for ch in check_results or evaluator_checks:
            ok = bool(ch.get("ok"))
            if ok:
                passed += 1
            else:
                failed += 1
                failed_ids.append(str(ch.get("id") or "check"))

        req_hits = 0
        req_miss: list[str] = []
        claimed = set(c.get("satisfies_requirements") or [])
        text_blob = " ".join(
            [
                str(c.get("summary") or ""),
                str(c.get("diff") or ""),
                " ".join(str(x) for x in (c.get("notes") or [])),
            ]
        ).lower()
        for req in human_requirements:
            key = req.strip().lower()
            if req in claimed or key in text_blob or any(key in str(s).lower() for s in claimed):
                req_hits += 1
            else:
                req_miss.append(req)

        # Primary: zero failed evaluator checks; secondary: human req coverage; tertiary: fewer tokens
        score = (
            -failed * 1000
            + passed * 10
            + req_hits * 5
            - int(c.get("quota_tokens") or 0)
        )
        scored.append(
            {
                "id": cid,
                "score": score,
                "evaluator_passed": passed,
                "evaluator_failed": failed,
                "failed_ids": failed_ids,
                "human_req_hits": req_hits,
                "human_req_miss": req_miss,
                "quota_tokens": int(c.get("quota_tokens") or 0),
                "majority_vote_used": False,
            }
        )

    scored.sort(key=lambda r: (-r["score"], r["id"]))
    return {
        "ranking_method": "evaluator_owned_checks_and_human_requirements",
        "majority_vote": False,
        "swarm": False,
        "ranked": scored,
        "winner": scored[0]["id"] if scored else None,
        "evaluator_checks": [c.get("id") for c in evaluator_checks],
        "human_requirements": list(human_requirements),
    }
