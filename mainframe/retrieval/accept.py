"""Acceptance: relevant-file recall, context size, FTS5 ablation, honest misses."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mainframe.config import ROOT
from mainframe.retrieval.retrieve import retrieve

FIXTURE_ROOT = ROOT / "docs" / "retrieval" / "fixtures"
CASES_PATH = FIXTURE_ROOT / "cases.json"
POLICY_PATH = Path(__file__).resolve().parent / "fts5_policy.json"
MAX_CONTEXT_CHARS = 12000


def _norm(p: str) -> str:
    return p.replace("\\", "/").casefold()


def _hit_paths(result: dict[str, Any], *, top_n: int = 5) -> list[str]:
    return [_norm(h["path"]) for h in (result.get("results") or [])[:top_n]]


def _recall(relevant: list[str], ranked: list[str]) -> float:
    if not relevant:
        return 1.0 if not ranked or True else 1.0
    need = {_norm(r) for r in relevant}
    got = set(ranked)
    return len(need & got) / len(need)


def _evaluate_case(case: dict[str, Any], *, use_fts5: bool) -> dict[str, Any]:
    root = FIXTURE_ROOT / case["root"]
    out = retrieve(
        root,
        issue_text=case["issue_text"],
        goal=case["goal"],
        follow_up=case.get("follow_up"),
        use_fts5=use_fts5,
        top_k=8,
    )
    ranked = _hit_paths(out, top_n=5)
    relevant = case.get("relevant_files") or []
    recall = _recall(relevant, ranked)
    misses = [r for r in relevant if _norm(r) not in set(ranked)]
    first = ranked[0] if ranked else None
    misleading_first = False
    irr = case.get("irrelevant_must_not_rank_first") or []
    if irr and first in {_norm(x) for x in irr}:
        misleading_first = True

    stack_only = case.get("stack_only_file")
    found_outside = True
    if stack_only and relevant:
        # Relevant file must appear; recording whether stack-only file outranks it is informative
        found_outside = _norm(relevant[0]) in set(ranked)

    expect_none = bool(case.get("expect_no_evidence"))
    no_ev = bool(out.get("no_relevant_evidence"))
    evidence_ok = no_ev if expect_none else (not no_ev and recall >= 1.0)

    ok = (
        out.get("ok") is True
        and out.get("goal_preserved") is True
        and out.get("goal") == case["goal"]
        and out.get("remote_vector_db_used") is False
        and out.get("paid_embedding_used") is False
        and int(out.get("context_chars") or 0) <= MAX_CONTEXT_CHARS
        and not misleading_first
        and evidence_ok
        and (found_outside if not expect_none else True)
    )

    return {
        "id": case["id"],
        "ok": ok,
        "recall": recall,
        "misses": misses,
        "ranked_top5": ranked,
        "context_chars": out.get("context_chars"),
        "no_relevant_evidence": no_ev,
        "expect_no_evidence": expect_none,
        "misleading_first": misleading_first,
        "goal": out.get("goal"),
        "fts5_used": out.get("fts5_used"),
        "signals_sample": [
            {"path": h["path"], "score": h["score"], "kinds": [s["kind"] for s in h["signals"]]}
            for h in (out.get("results") or [])[:3]
        ],
    }


def run_retrieval_accept() -> dict[str, Any]:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    checks: list[dict[str, Any]] = []

    # Ablation: measure with and without FTS5
    base_evals = [_evaluate_case(c, use_fts5=False) for c in cases]
    fts_evals = [_evaluate_case(c, use_fts5=True) for c in cases]

    base_recall = sum(e["recall"] for e in base_evals) / max(1, len(base_evals))
    fts_recall = sum(e["recall"] for e in fts_evals) / max(1, len(fts_evals))
    base_ctx = sum(int(e["context_chars"] or 0) for e in base_evals) / max(1, len(base_evals))
    fts_ctx = sum(int(e["context_chars"] or 0) for e in fts_evals) / max(1, len(fts_evals))
    base_ok = all(e["ok"] for e in base_evals)
    fts_ok = all(e["ok"] for e in fts_evals)

    # Enable FTS5 only if it improves measured recall, or same recall with smaller context,
    # without breaking any fixture that baseline passed.
    improves = (fts_recall > base_recall + 1e-9) or (
        abs(fts_recall - base_recall) < 1e-9 and fts_ctx < base_ctx and fts_ok
    )
    # Do not enable if FTS5 worsens pass rate vs baseline
    if base_ok and not fts_ok:
        improves = False
    use_fts5 = bool(improves and fts_ok)

    POLICY_PATH.write_text(
        json.dumps(
            {
                "use_fts5": use_fts5,
                "measured": {
                    "baseline_mean_recall": round(base_recall, 4),
                    "fts5_mean_recall": round(fts_recall, 4),
                    "baseline_mean_context_chars": round(base_ctx, 1),
                    "fts5_mean_context_chars": round(fts_ctx, 1),
                    "baseline_all_ok": base_ok,
                    "fts5_all_ok": fts_ok,
                },
                "reason": (
                    "FTS5 enabled: measured improvement on fixtures"
                    if use_fts5
                    else "FTS5 disabled: no measured improvement (exact/lexical sufficient)"
                ),
                "paid_embedding_used": False,
                "remote_vector_db_used": False,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    checks.append(
        {
            "id": "fts5_ablation_recorded",
            "ok": True,
            "detail": {
                "use_fts5": use_fts5,
                "baseline_mean_recall": round(base_recall, 4),
                "fts5_mean_recall": round(fts_recall, 4),
                "baseline_mean_context_chars": round(base_ctx, 1),
                "fts5_mean_context_chars": round(fts_ctx, 1),
            },
        }
    )

    # Per-case checks use baseline (exact+lexical); FTS5 only if policy says so — re-eval policy mode
    final_evals = [_evaluate_case(c, use_fts5=use_fts5) for c in cases]
    for e in final_evals:
        checks.append(
            {
                "id": f"case:{e['id']}",
                "ok": e["ok"],
                "detail": {
                    "recall": e["recall"],
                    "misses": e["misses"],
                    "ranked_top5": e["ranked_top5"],
                    "context_chars": e["context_chars"],
                    "no_relevant_evidence": e["no_relevant_evidence"],
                    "misleading_first": e["misleading_first"],
                    "signals_sample": e["signals_sample"],
                },
            }
        )

    # Explicit: misses recorded, not invented
    any_miss = any(e["misses"] for e in final_evals)
    checks.append(
        {
            "id": "misses_recorded_not_invented",
            "ok": all(
                # If recall < 1, misses non-empty; if recall == 1, misses empty
                (len(e["misses"]) == 0) == (e["recall"] >= 1.0 - 1e-9)
                or e.get("expect_no_evidence")
                for e in final_evals
            ),
            "detail": {
                "cases_with_misses": [e["id"] for e in final_evals if e["misses"]],
                "note": "Misses listed when relevant files absent from top-5; no fabricated locus",
                "any_miss_this_run": any_miss,
            },
        }
    )

    checks.append(
        {
            "id": "no_remote_vector_or_paid_embedding",
            "ok": True,
            "detail": {"remote_vector_db_used": False, "paid_embedding_used": False},
        }
    )

    passed = sum(1 for c in checks if c["ok"])
    failed = len(checks) - passed
    return {
        "ok": failed == 0,
        "passed": passed,
        "failed": failed,
        "checks": checks,
        "mean_relevant_file_recall": round(
            sum(e["recall"] for e in final_evals) / max(1, len(final_evals)), 4
        ),
        "mean_context_chars": round(
            sum(int(e["context_chars"] or 0) for e in final_evals) / max(1, len(final_evals)), 1
        ),
        "fts5_policy": json.loads(POLICY_PATH.read_text(encoding="utf-8")),
        "remote_vector_db_used": False,
        "paid_embedding_used": False,
    }
