"""Aggregate benchmark runs — raw results, uncertainty, failure prioritization."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.config import RUNS_DIR, ensure_state


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def summarize_attempts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_status = Counter()
    for r in rows:
        if r.get("unavailable_provider"):
            by_status["unavailable_provider"] += 1
        elif r.get("timed_out"):
            by_status["timeout"] += 1
        elif r.get("success"):
            by_status["success"] += 1
        else:
            by_status["failed"] += 1
    return dict(by_status)


def failure_categories(rows: list[dict[str, Any]]) -> dict[str, Any]:
    fails = [r for r in rows if not r.get("success") and r.get("split") == "holdout"]
    counts = Counter((r.get("category") or "unknown") for r in fails)
    largest = counts.most_common(1)[0] if counts else ("none", 0)
    return {
        "counts": dict(counts),
        "largest_category": largest[0],
        "largest_count": largest[1],
    }


def prioritize_fix(failure_summary: dict[str, Any]) -> dict[str, Any]:
    cat = failure_summary.get("largest_category") or "none"
    n = failure_summary.get("largest_count") or 0
    if n == 0:
        return {
            "priority": "maintain_holdout_green",
            "largest_failure_category": cat,
            "recommendation": "No holdout failures in this run; avoid adding agent complexity before locking reproducibility.",
        }
    recommendations = {
        "dependency_trap": "Harden dependency-trap handling: pin-aware API shims before suggesting upgrades.",
        "multifile": "Improve cross-file symbol alignment and import graph inspection before patch.",
        "ui_behavior": "Expand DOM-first Playwright verification in the coding loop before visual models.",
        "should_clarify": "Add clarify gate when multiple failing tests or ambiguous scope.",
        "should_decline": "Strengthen policy decline path for eligibility/cost-gate edits.",
        "logic_bug": "Improve local reproduce→patch loop for single-file defects.",
    }
    return {
        "priority": "fix_largest_failure_category_first",
        "largest_failure_category": cat,
        "recommendation": recommendations.get(
            cat, f"Address holdout failures in category '{cat}' before expanding agent features."
        ),
        "do_not_add_agent_complexity_until": f"holdout_{cat}_passes",
    }


def compare_harnesses(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_h: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_h[r.get("harness_id") or "unknown"].append(r)
    out: dict[str, Any] = {}
    for hid, rs in by_h.items():
        succ = [x for x in rs if x.get("success")]
        out[hid] = {
            "attempts": len(rs),
            "successes": len(succ),
            "timeouts": sum(1 for x in rs if x.get("timed_out")),
            "unavailable_provider": sum(1 for x in rs if x.get("unavailable_provider")),
            "mean_latency_ms_success": (
                round(sum(x.get("latency_ms") or 0 for x in succ) / len(succ), 3) if succ else None
            ),
            "mean_model_calls_per_success": (
                round(sum(x.get("model_calls") or 0 for x in succ) / len(succ), 3) if succ else None
            ),
            "human_interventions": sum(1 for x in rs if x.get("human_intervention")),
        }
    return out


def build_report(
    *,
    measurement_kind: str,
    rows: list[dict[str, Any]],
    models: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    failures = failure_categories(rows)
    uncertainty = {
        "holdout_only_claim": True,
        "sample_size_holdout": sum(1 for r in rows if r.get("split") == "holdout"),
        "live_model_quality_measured": measurement_kind == "live_model_quality",
        "mock_integration_separate": measurement_kind == "mock_integration",
        "published_claim": False,
        "confidence": "low" if measurement_kind == "mock_integration" else "unmeasured_unless_live",
        "notes": (
            "Fixture agents measure harness integration only, not frontier model quality. "
            "Live eligible model runs are opt-in and may be unavailable."
        ),
    }
    return {
        "suite": "mainframe-codingbench",
        "evaluated_at": _utc(),
        "measurement_kind": measurement_kind,
        "models": models or [],
        "attempts": rows,
        "attempt_summary": summarize_attempts(rows),
        "harness_comparison": compare_harnesses(rows),
        "failure_analysis": failures,
        "priority_fix": prioritize_fix(failures),
        "uncertainty": uncertainty,
        "all_attempts_reported": True,
    }


def publish_report(report: dict[str, Any]) -> Path:
    ensure_state()
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = RUNS_DIR / f"codingbench-{stamp}.json"
    import json

    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    report["published_path"] = str(path)
    return path
