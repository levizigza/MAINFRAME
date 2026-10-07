"""Mode B model fitness — doctor catalog + live probe; no auto-download."""

from __future__ import annotations

from typing import Any

from mainframe.ai import probe_free_inference
from mainframe.doctor import (
    MODEL_CATALOG,
    derive_resource_limits,
    estimate_model_fit,
    measure_cpu,
    measure_disk,
    measure_memory,
    run_doctor,
)
from mainframe.eligibility import decide_provider


def mode_b_fitness_report(*, run_full_doctor: bool = False) -> dict[str, Any]:
    """
    First-class Mode B report: which catalog models fit measured RAM,
    whether Ollama is reachable, and explicit user pull steps.
    Doctor never downloads weights.
    """
    probe = probe_free_inference()
    probe_d = probe.to_dict() if hasattr(probe, "to_dict") else {}
    decision = decide_provider("ollama_local", endpoint="http://127.0.0.1:11434")

    if run_full_doctor:
        doc = run_doctor()
        mem = doc.get("memory") or {}
        limits = doc.get("resource_limits") or {}
        fit = doc.get("model_fit") or {}
    else:
        mem = measure_memory()
        cpu = measure_cpu()
        disk = measure_disk()
        limits = derive_resource_limits(mem, cpu, disk)
        fit = estimate_model_fit(mem, limits)

    recommended = list(fit.get("recommended_ids") or [])
    available = probe_d.get("status") in ("available", "ok")

    pull_steps = []
    if recommended:
        mid = recommended[0]
        # Map catalog id → plausible ollama library name (user verifies)
        ollama_hint = {
            "tinyllama-1.1b-q4": "tinyllama",
            "qwen2.5-3b-instruct-q4": "qwen2.5:3b-instruct",
            "llama3.2-3b-instruct-q4": "llama3.2:3b",
            "qwen2.5-7b-instruct-q4": "qwen2.5:7b-instruct",
            "llama3.1-8b-instruct-q4": "llama3.1:8b",
        }.get(mid, mid.split("-")[0])
        pull_steps = [
            "Install Ollama from https://ollama.com (free software; not required for Mode A).",
            "Start Ollama so http://127.0.0.1:11434 responds.",
            f"Pull a fitted model (example for top fit `{mid}`): `ollama pull {ollama_hint}`",
            "Re-run: python -m mainframe ai probe",
            "Then: python -m mainframe workbench fitness",
            "Live evals only after probe status is available — never invent success.",
        ]
    else:
        pull_steps = [
            "No catalog model verified against measured RAM/budget on this host.",
            "Free RAM or choose a smaller GGUF/Ollama model; re-run doctor.",
            "Do not download large models based on marketing size labels.",
        ]

    return {
        "ok": True,
        "mode": "deterministic_plus_optional_cpu_ai",
        "mode_label": "Mode B",
        "product_direction": "Mode B first-class for FreeForge Workbench AI coding",
        "provider": {
            "id": "ollama_local",
            "eligible": bool(decision.eligible),
            "endpoint": "http://127.0.0.1:11434",
            "reachable": available,
            "probe_status": probe_d.get("status"),
            "probe_detail": probe_d.get("detail"),
        },
        "memory": {
            "measured": mem.get("measured"),
            "available_gib": mem.get("available_gib"),
            "total_gib": mem.get("total_gib"),
        },
        "inference_budget_gib": (limits.get("optional_cpu_inference") or {}).get(
            "ram_budget_gib"
        ),
        "catalog": MODEL_CATALOG,
        "fit": fit,
        "recommended_ids": recommended,
        "user_pull_steps": pull_steps,
        "auto_download": False,
        "live_coding_quality": "unknown" if not available else "pending_eval",
        "competitor_cursor_e2e": "unknown",
        "note": (
            "Weights are user-initiated pulls only. Throughput stays unmeasured until "
            "modeleval/codingbench --live runs against an installed model."
        ),
    }
