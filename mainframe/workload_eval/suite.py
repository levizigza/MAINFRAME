"""Aggregate held-out workload evaluation, ablations, and disable policy."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from mainframe.config import ROOT, RUNS_DIR, ensure_state
from mainframe.workload_eval.features import ABLATIONS, FeatureFlags
from mainframe.workload_eval.runners import RUNNERS, WORK
from mainframe.workload_eval.stats import wilson_interval

REPORT_MD = ROOT / "docs" / "eval" / "workloads" / "HELDOUT_EVAL.md"
REPORT_JSON = ROOT / "docs" / "eval" / "workloads" / "HELDOUT_EVAL.json"
POLICY_PATH = ROOT / "docs" / "eval" / "workloads" / "feature_disable_policy.json"

SYSTEMS = ("freeforge", "minimal", "manual")
WORKLOADS = ("repository_repair", "website_maintenance", "document_reporting")


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _agg(trials: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(trials)
    succ = sum(1 for t in trials if t.get("correct"))
    elapsed = [float(t.get("elapsed_s") or 0) for t in trials]
    human = [float(t.get("active_human_s") or 0) for t in trials]
    retries = sum(int(t.get("retries") or 0) for t in trials)
    models = sum(int(t.get("model_calls") or 0) for t in trials)
    recoveries = sum(int(t.get("failure_recoveries") or 0) for t in trials)
    setup = sum(float(t.get("setup_s") or 0) for t in trials)
    maint = sum(float(t.get("maintenance_s") or 0) for t in trials)
    mean_elapsed = sum(elapsed) / n if n else 0.0
    mean_human = sum(human) / n if n else 0.0
    # Sustainable daily volume: assume 8h wall clock, subtract none for agent;
    # for manual use active human as limiter (8h human budget)
    if mean_human > 0:
        daily = (8 * 3600.0) / mean_human
        daily_basis = "active_human_8h"
    elif mean_elapsed > 0:
        daily = (8 * 3600.0) / mean_elapsed
        daily_basis = "wall_clock_8h_theoretical"
    else:
        daily = 0.0
        daily_basis = "undefined"
    # Cap display when wall-clock is sub-second automation (not a ops capacity claim)
    daily_note = None
    if daily_basis.startswith("wall_clock") and mean_elapsed < 1.0:
        daily_note = (
            "Theoretical from sub-second deterministic runs; not a claim of interactive daily capacity."
        )
    return {
        "trials": n,
        "correct_count": succ,
        "correct_completion_rate": wilson_interval(succ, n),
        "total_elapsed_s_mean": round(mean_elapsed, 4),
        "total_elapsed_s_sum": round(sum(elapsed), 4),
        "active_human_s_mean": round(mean_human, 4),
        "active_human_s_sum": round(sum(human), 4),
        "retries_total": retries,
        "model_calls_total": models,
        "failure_recoveries_total": recoveries,
        "setup_s_sum": round(setup, 4),
        "maintenance_s_sum": round(maint, 4),
        "sustainable_daily_volume_est": round(daily, 2),
        "daily_volume_basis": daily_basis,
        "daily_volume_note": daily_note,
        "small_sample": n < 30,
    }


def _clear_caches() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    for name in ("w1_cache_repair.py", "w2_cache.html", "w3_cache_metrics.json"):
        p = WORK / name
        if p.is_file():
            p.unlink()


def run_comparison(*, trials: int = 5) -> dict[str, Any]:
    """Compare freeforge (full flags) vs minimal vs manual on held-out inputs."""
    out: dict[str, Any] = {}
    for wl in WORKLOADS:
        runner = RUNNERS[wl]
        out[wl] = {}
        for system in SYSTEMS:
            _clear_caches()
            flags = FeatureFlags()
            rows = [
                runner(system=system, flags=flags, trial=i + 1) for i in range(trials)
            ]
            out[wl][system] = {"aggregate": _agg(rows), "trials": rows}
    return out


def run_ablations(*, trials: int = 5) -> dict[str, Any]:
    """Ablate retrieval / workflow reuse / review / caching on FreeForge only."""
    out: dict[str, Any] = {}
    for wl in WORKLOADS:
        runner = RUNNERS[wl]
        out[wl] = {}
        for abl_name, flags in ABLATIONS.items():
            _clear_caches()
            rows = [
                runner(system="freeforge", flags=flags, trial=i + 1) for i in range(trials)
            ]
            out[wl][abl_name] = {"aggregate": _agg(rows), "flags": flags.to_dict(), "trials": rows}
    return out


def derive_disable_policy(ablations: dict[str, Any]) -> dict[str, Any]:
    """
    If removing a feature does not worsen (or improves) correct rate vs full,
    disable that feature for the workload — more features ≠ more intelligence.
    """
    policy: dict[str, Any] = {
        "generated_at": _utc(),
        "rule": "Disable feature for workload when ablation correct rate >= full rate (tied or better without it).",
        "workloads": {},
    }
    for wl, abl in ablations.items():
        full_rate = ((abl.get("full") or {}).get("aggregate") or {}).get("correct_completion_rate", {}).get(
            "rate"
        )
        if full_rate is None:
            continue
        disables: dict[str, Any] = {}
        for feat, key in (
            ("retrieval", "no_retrieval"),
            ("workflow_reuse", "no_workflow_reuse"),
            ("review", "no_review"),
            ("caching", "no_caching"),
        ):
            row = abl.get(key) or {}
            rate = ((row.get("aggregate") or {}).get("correct_completion_rate") or {}).get("rate")
            if rate is None:
                continue
            if rate >= full_rate:
                disables[feat] = {
                    "disabled": True,
                    "reason": "ablation_rate_ge_full",
                    "full_rate": full_rate,
                    "ablation_rate": rate,
                }
            else:
                disables[feat] = {
                    "disabled": False,
                    "reason": "ablation_worsened_outcomes",
                    "full_rate": full_rate,
                    "ablation_rate": rate,
                    "contribution": round(full_rate - rate, 4),
                }
        policy["workloads"][wl] = disables
    return policy


def superiority_claims(comparison: dict[str, Any], policy: dict[str, Any]) -> list[dict[str, Any]]:
    """Only workload-specific, evidence-supported claims."""
    claims: list[dict[str, Any]] = []
    for wl in WORKLOADS:
        ff = ((comparison.get(wl) or {}).get("freeforge") or {}).get("aggregate") or {}
        mn = ((comparison.get(wl) or {}).get("minimal") or {}).get("aggregate") or {}
        man = ((comparison.get(wl) or {}).get("manual") or {}).get("aggregate") or {}
        ff_rate = (ff.get("correct_completion_rate") or {}).get("rate")
        mn_rate = (mn.get("correct_completion_rate") or {}).get("rate")
        man_rate = (man.get("correct_completion_rate") or {}).get("rate")
        if ff_rate is None:
            continue
        if mn_rate is not None and ff_rate > mn_rate:
            claims.append(
                {
                    "workload": wl,
                    "claim": "freeforge_correct_rate_exceeds_minimal_free_agent",
                    "freeforge_rate": ff_rate,
                    "minimal_rate": mn_rate,
                    "evidence": "heldout_comparison",
                    "supported": True,
                }
            )
        elif mn_rate is not None and ff_rate <= mn_rate:
            claims.append(
                {
                    "workload": wl,
                    "claim": "no_superiority_vs_minimal_on_correct_rate",
                    "freeforge_rate": ff_rate,
                    "minimal_rate": mn_rate,
                    "supported": False,
                }
            )
        if man_rate is not None and ff_rate == man_rate and man_rate > 0 and (ff.get("active_human_s_mean") or 0) < (
            man.get("active_human_s_mean") or 0
        ):
            claims.append(
                {
                    "workload": wl,
                    "claim": "freeforge_matches_manual_correctness_with_less_active_human_time",
                    "freeforge_rate": ff_rate,
                    "manual_rate": man_rate,
                    "freeforge_active_human_s_mean": ff.get("active_human_s_mean"),
                    "manual_active_human_s_mean": man.get("active_human_s_mean"),
                    "evidence": "heldout_comparison",
                    "supported": True,
                }
            )
        elif man_rate is not None and ff_rate > man_rate:
            claims.append(
                {
                    "workload": wl,
                    "claim": "freeforge_correct_rate_exceeds_scripted_manual_proxy",
                    "freeforge_rate": ff_rate,
                    "manual_rate": man_rate,
                    "evidence": "heldout_comparison",
                    "supported": True,
                    "note": "Manual cell is a scripted prior-process proxy with budgeted active_human_s.",
                }
            )
        # Feature contribution claims from policy
        for feat, meta in ((policy.get("workloads") or {}).get(wl) or {}).items():
            if meta.get("disabled"):
                claims.append(
                    {
                        "workload": wl,
                        "claim": f"disable_{feat}_for_this_workload",
                        "supported": True,
                        "evidence": "ablation_rate_ge_full",
                        "detail": meta,
                    }
                )
            elif meta.get("contribution", 0) > 0:
                claims.append(
                    {
                        "workload": wl,
                        "claim": f"{feat}_improves_correct_rate",
                        "supported": True,
                        "evidence": "ablation_worsened_when_removed",
                        "detail": meta,
                    }
                )
    claims.append(
        {
            "workload": "*",
            "claim": "competitor_claude_code_cursor_e2e",
            "supported": False,
            "status": "unmeasured",
            "note": "No purchased access; competitor runs omitted.",
        }
    )
    return claims


def _write_markdown(payload: dict[str, Any]) -> None:
    lines = [
        "# Held-out workload evaluation",
        "",
        f"Generated: `{payload.get('generated_at')}`",
        "",
        "Workloads: repository repair, website maintenance, document reporting.",
        "Inputs: `docs/eval/workloads/holdout/` (held out from scorecard W1–W3 and demo fixtures).",
        "Competitors (Claude Code / Cursor E2E): **unmeasured** — no purchased access.",
        "",
        "Sample size is small; Wilson 95% intervals are reported and flagged `small_sample`.",
        "",
        "## Comparison (correct completion rate)",
        "",
        "| Workload | FreeForge | Minimal agent | Manual process |",
        "|----------|-----------|---------------|----------------|",
    ]
    comp = payload.get("comparison") or {}
    for wl in WORKLOADS:
        def cell(system: str) -> str:
            agg = ((comp.get(wl) or {}).get(system) or {}).get("aggregate") or {}
            ci = agg.get("correct_completion_rate") or {}
            if ci.get("rate") is None:
                return "—"
            return f"{ci['rate']} (n={ci['n']}, {ci.get('ci95_low')}–{ci.get('ci95_high')})"

        lines.append(f"| {wl} | {cell('freeforge')} | {cell('minimal')} | {cell('manual')} |")

    lines.extend(["", "## Metrics (FreeForge full)", ""])
    for wl in WORKLOADS:
        agg = ((comp.get(wl) or {}).get("freeforge") or {}).get("aggregate") or {}
        lines.append(f"### {wl}")
        lines.append("")
        lines.append(f"- Correct rate: `{agg.get('correct_completion_rate')}`")
        lines.append(f"- Mean elapsed s: `{agg.get('total_elapsed_s_mean')}`")
        lines.append(f"- Mean active human s: `{agg.get('active_human_s_mean')}`")
        lines.append(f"- Retries total: `{agg.get('retries_total')}`")
        lines.append(f"- Model calls total: `{agg.get('model_calls_total')}`")
        lines.append(f"- Failure recoveries: `{agg.get('failure_recoveries_total')}`")
        lines.append(f"- Setup s sum: `{agg.get('setup_s_sum')}` (separate)")
        lines.append(f"- Maintenance s sum: `{agg.get('maintenance_s_sum')}` (separate)")
        lines.append(
            f"- Sustainable daily volume est: `{agg.get('sustainable_daily_volume_est')}` "
            f"({agg.get('daily_volume_basis')})"
        )
        lines.append("")

    lines.extend(["## Ablations (FreeForge)", ""])
    abl = payload.get("ablations") or {}
    for wl in WORKLOADS:
        lines.append(f"### {wl}")
        lines.append("")
        lines.append("| Condition | Rate |")
        lines.append("|-----------|------|")
        for name, row in (abl.get(wl) or {}).items():
            ci = ((row.get("aggregate") or {}).get("correct_completion_rate") or {})
            lines.append(f"| {name} | {ci.get('rate')} (n={ci.get('n')}) |")
        lines.append("")

    lines.extend(["## Disable policy (features that do not help)", ""])
    pol = payload.get("disable_policy") or {}
    lines.append("```json")
    lines.append(json.dumps(pol.get("workloads") or {}, indent=2))
    lines.append("```")
    lines.append("")
    lines.extend(["## Claims (evidence-gated)", ""])
    for c in payload.get("claims") or []:
        mark = "SUPPORTED" if c.get("supported") else "UNSUPPORTED/UNMEASURED"
        lines.append(f"- **{mark}** `{c.get('workload')}`: {c.get('claim')}")
    lines.append("")
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def flags_from_policy(workload: str, policy: dict[str, Any]) -> FeatureFlags:
    disables = ((policy.get("workloads") or {}).get(workload) or {})
    return FeatureFlags(
        retrieval=not bool((disables.get("retrieval") or {}).get("disabled")),
        workflow_reuse=not bool((disables.get("workflow_reuse") or {}).get("disabled")),
        review=not bool((disables.get("review") or {}).get("disabled")),
        caching=not bool((disables.get("caching") or {}).get("disabled")),
    )


def run_simplified(policy: dict[str, Any], *, trials: int = 5) -> dict[str, Any]:
    """Re-run FreeForge with features disabled per ablation policy."""
    out: dict[str, Any] = {}
    for wl in WORKLOADS:
        runner = RUNNERS[wl]
        flags = flags_from_policy(wl, policy)
        _clear_caches()
        rows = [runner(system="freeforge", flags=flags, trial=i + 1) for i in range(trials)]
        out[wl] = {"flags": flags.to_dict(), "aggregate": _agg(rows), "trials": rows}
    return out


def run_heldout_eval(*, trials: int = 5) -> dict[str, Any]:
    ensure_state()
    WORK.mkdir(parents=True, exist_ok=True)
    _clear_caches()

    comparison = run_comparison(trials=trials)
    ablations = run_ablations(trials=trials)
    policy = derive_disable_policy(ablations)
    simplified = run_simplified(policy, trials=trials)
    claims = superiority_claims(comparison, policy)

    # Prefer simplified when it does not worsen vs full freeforge
    for wl in WORKLOADS:
        full_r = (
            ((comparison.get(wl) or {}).get("freeforge") or {})
            .get("aggregate", {})
            .get("correct_completion_rate", {})
            .get("rate")
        )
        sim_r = (
            (simplified.get(wl) or {})
            .get("aggregate", {})
            .get("correct_completion_rate", {})
            .get("rate")
        )
        if full_r is not None and sim_r is not None and sim_r >= full_r:
            claims.append(
                {
                    "workload": wl,
                    "claim": "simplified_freeforge_preferred_or_tied",
                    "supported": True,
                    "evidence": "post_ablation_simplified_rerun",
                    "full_rate": full_r,
                    "simplified_rate": sim_r,
                    "flags": (simplified.get(wl) or {}).get("flags"),
                }
            )

    payload = {
        "suite": "heldout_workload_eval",
        "generated_at": _utc(),
        "trials_per_cell": trials,
        "holdout_root": "docs/eval/workloads/holdout",
        "competitors": {
            "claude_code_e2e": "unmeasured",
            "cursor_e2e": "unmeasured",
            "note": "Legitimately unavailable without purchasing access for this run.",
        },
        "comparison": comparison,
        "ablations": ablations,
        "disable_policy": policy,
        "freeforge_simplified": simplified,
        "claims": claims,
        "small_sample_acknowledged": trials < 30,
    }

    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    POLICY_PATH.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
    _write_markdown(payload)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_path = RUNS_DIR / f"heldout-eval-{stamp}.json"
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    payload["report_md"] = str(REPORT_MD.relative_to(ROOT)).replace("\\", "/")
    payload["report_json"] = str(REPORT_JSON.relative_to(ROOT)).replace("\\", "/")
    payload["policy_path"] = str(POLICY_PATH.relative_to(ROOT)).replace("\\", "/")
    payload["run_path"] = str(run_path.relative_to(ROOT)).replace("\\", "/")
    payload["ok"] = True
    return payload
