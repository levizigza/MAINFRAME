"""Capability matrix + measured workloads + quotas + weaknesses from evidence."""

from __future__ import annotations

from typing import Any


def build_capability_matrix(
    *,
    modes: dict[str, Any],
    evidence: dict[str, Any],
    hardware: dict[str, Any],
    ai_probe: dict[str, Any],
) -> dict[str, Any]:
    heldout = evidence.get("heldout") or {}
    comparisons = (heldout.get("comparison") or heldout.get("workloads") or {})

    # Normalize heldout structure — HELDOUT_EVAL.json may nest differently
    workload_rows = []
    if isinstance(comparisons, dict) and comparisons:
        for wid, row in comparisons.items():
            if isinstance(row, dict) and ("freeforge" in row or "correct_rate" in str(row)):
                workload_rows.append({"id": wid, **row})

    # Fallback: parse from summary claims / metrics in JSON
    metrics = heldout.get("metrics") or heldout.get("freeforge_metrics") or {}
    if not workload_rows and isinstance(metrics, dict):
        for wid, m in metrics.items():
            rate = m.get("correct_rate") if isinstance(m, dict) else None
            workload_rows.append(
                {
                    "id": wid,
                    "freeforge_rate": (rate or {}).get("rate") if isinstance(rate, dict) else None,
                    "source": "metrics",
                }
            )

    cells = {
        "deterministic_automation": {
            "status": "measured",
            "mode": "deterministic_offline",
            "note": "Held-out W1–W3 + workflow fixtures; model_calls=0",
        },
        "optional_cpu_ai": {
            "status": "unknown" if (ai_probe.get("status") == "paused") else "available",
            "mode": "deterministic_plus_optional_cpu_ai",
            "correctness_on_this_host": "unknown",
            "note": (
                "Ollama paused/unreachable — live local model quality unmeasured on this host."
                if ai_probe.get("status") == "paused"
                else "Loopback AI reachable; quality still requires modeleval live rows."
            ),
        },
        "eligible_free_hosted_ai": {
            "status": "unavailable",
            "mode": "deterministic_plus_eligible_free_hosted_ai",
            "providers": [],
            "note": "No verified recurring-free hosted entitlement (see docs/PROVIDERS.md).",
        },
        "competitor_claude_code_cursor_e2e": {
            "status": "unknown",
            "note": "Unmeasured — no purchased access.",
        },
        "frontier_unlimited_performance": {
            "status": "unknown",
            "explicitly_not_claimed": True,
        },
    }

    return {
        "optimize_objective": "correct_completed_work_per_available_resource",
        "not_optimize_for": ["agent_count", "model_parameter_count", "cosmetic_frontier_label"],
        "modes_summary": {
            mid: {
                "title": m.get("title"),
                "available_now": m.get("available_now", True),
                "uses_ai": m.get("uses_ai"),
            }
            for mid, m in (modes.get("modes") or {}).items()
        },
        "recommended_mode_id": modes.get("recommended_mode_id"),
        "cells": cells,
        "hardware_observations": hardware,
        "heldout_workload_ids": [r.get("id") for r in workload_rows],
    }


def summarize_workloads(evidence: dict[str, Any]) -> dict[str, Any]:
    heldout = evidence.get("heldout") or {}
    # Prefer explicit comparison table if present in JSON
    comparison = heldout.get("comparison") or {}
    claims = heldout.get("claims") or []
    disable = (evidence.get("disable_policy") or {}).get("workloads") or {}

    # HELDOUT_EVAL.json structure from suite — check keys
    results = heldout.get("results") or heldout.get("workload_results") or {}

    measured = {
        "repository_repair": {
            "freeforge_correct_rate": 1.0,
            "minimal_correct_rate": 0.0,
            "manual_correct_rate": 1.0,
            "n": 5,
            "ci95": [0.5655, 1.0],
            "small_sample": True,
            "model_calls": 0,
            "mean_elapsed_s": 0.0082,
            "mean_active_human_s": 0.0,
            "outperforms_minimal": True,
            "outperforms_manual_correctness": False,
            "matches_manual_correctness": True,
            "less_active_human_than_manual": True,
            "source": "docs/eval/workloads/HELDOUT_EVAL.md",
        },
        "website_maintenance": {
            "freeforge_correct_rate": 1.0,
            "minimal_correct_rate": 0.0,
            "manual_correct_rate": 1.0,
            "n": 5,
            "ci95": [0.5655, 1.0],
            "small_sample": True,
            "model_calls": 0,
            "mean_elapsed_s": 0.0058,
            "mean_active_human_s": 0.0,
            "outperforms_minimal": True,
            "matches_manual_correctness": True,
            "less_active_human_than_manual": True,
            "retrieval_required": True,
            "source": "docs/eval/workloads/HELDOUT_EVAL.md",
        },
        "document_reporting": {
            "freeforge_correct_rate": 1.0,
            "minimal_correct_rate": 0.0,
            "manual_correct_rate": 1.0,
            "n": 5,
            "ci95": [0.5655, 1.0],
            "small_sample": True,
            "model_calls": 0,
            "mean_elapsed_s": 0.0059,
            "mean_active_human_s": 0.0,
            "outperforms_minimal": True,
            "matches_manual_correctness": True,
            "less_active_human_than_manual": True,
            "retrieval_required": True,
            "review_required": True,
            "source": "docs/eval/workloads/HELDOUT_EVAL.md",
        },
    }

    # If JSON has live numbers, prefer them over hardcoded MD snapshot
    if isinstance(results, dict) and results:
        for wid, block in results.items():
            if wid in measured and isinstance(block, dict):
                ff = block.get("freeforge") or block.get("full") or {}
                if isinstance(ff, dict) and "rate" in (ff.get("correct_rate") or {}):
                    measured[wid]["freeforge_correct_rate"] = ff["correct_rate"]["rate"]

    sustainable = {
        "note": (
            "Wall-clock theoretical volumes from sub-second deterministic runs are "
            "NOT interactive capacity. Prefer quota + human review limits."
        ),
        "theoretical_wall_clock_8h": "unknown_as_operational_capacity",
        "operational_guidance": {
            "deterministic_jobs_per_hour": "unknown",
            "interactive_coding_tasks_per_day": "unknown",
            "ai_requests_per_window": {
                "ollama_local_default": {
                    "requests": 60,
                    "tokens": 100000,
                    "context": 32000,
                    "concurrency": 4,
                    "source": "quota ledger default bucket",
                }
            },
        },
        "reset_unknown": True,
    }

    weaknesses = [
        {
            "id": "per_feature_vs_joint_ablation",
            "severity": "Disabling every 'no-gain' feature jointly can fail when features compensate (e.g. review covers missing retrieval)",
            "severity": "medium",
        },
        {
            "id": "small_n_heldout",
            "severity": "n=5 per workload; Wilson CI wide (0.57–1.0)",
            "severity": "medium",
        },
        {
            "id": "no_local_model_on_host",
            "severity": "Ollama unreachable — Mode B quality unknown on this machine",
            "severity": "high_for_ai_tasks",
        },
        {
            "id": "no_eligible_hosted_free",
            "severity": "Mode C empty — Groq/Gemini/Mistral unverified_live",
            "severity": "high_for_hosted_ai",
        },
        {
            "id": "no_os_network_isolation",
            "severity": "Live non-loopback connectors disabled without OS net jail",
            "severity": "medium",
        },
        {
            "id": "competitor_e2e_unmeasured",
            "severity": "Claude Code / Cursor E2E not compared",
            "severity": "unknown",
        },
        {
            "id": "schtasks_elevation",
            "severity": "OS logon task create Access denied without elevation",
            "severity": "low",
        },
        {
            "id": "theoretical_daily_volume",
            "severity": "Multi-million theoretical daily volumes must not be treated as capacity",
            "severity": "high_misread_risk",
        },
    ]

    next_improvements = [
        {
            "priority": 1,
            "id": "fit_and_measure_local_cpu_model",
            "action": "Install a RAM-fitting local model; run modeleval live holdout; update Mode B cells from unknown → measured",
        },
        {
            "priority": 2,
            "id": "expand_heldout_n",
            "action": "Increase held-out n beyond 5 before tightening CI-based claims",
        },
        {
            "priority": 3,
            "id": "verify_or_keep_refusing_hosted",
            "action": "Only enable Mode C after recurring-free entitlement evidence; otherwise keep refuse",
        },
        {
            "priority": 4,
            "id": "operational_quota_calibration",
            "action": "Replace theoretical wall-clock volume with measured sustainable interactive quotas",
        },
        {
            "priority": 5,
            "id": "optional_os_network_isolation",
            "action": "If live connectors needed, verify OS network isolation before re-enabling non-loopback",
        },
    ]

    where = {
        "outperforms_measured_baselines": [
            "FreeForge correct rate >> minimal free agent on held-out repair / site / docreport (n=5)",
            "FreeForge matches manual correctness with less active human time on those workloads",
            "Retrieval improves site + docreport; review improves docreport (ablations)",
        ],
        "does_not_outperform_or_unmeasured": [
            "Does not exceed manual correctness rate on those workloads (tied at 1.0)",
            "Competitor Claude Code / Cursor E2E: unknown",
            "Live local/hosted model coding quality on this host: unknown (AI paused)",
            "Unlimited frontier performance: not claimed",
        ],
        "disable_policy_summary": disable,
        "claims_from_heldout": claims if claims else "see HELDOUT_EVAL.md",
        "comparison_raw_present": bool(comparison) or bool(results),
    }

    return {
        "measured_workloads": measured,
        "sustainable_quotas": sustainable,
        "unresolved_weaknesses": weaknesses,
        "prioritized_next_improvements": next_improvements,
        "vs_baselines": where,
    }
