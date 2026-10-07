"""First-run onboarding for FreeForge Workbench + Mode B."""

from __future__ import annotations

from typing import Any

from mainframe.workbench.fitness import mode_b_fitness_report
from mainframe.workbench.status import workbench_status


def onboarding_guide() -> dict[str, Any]:
    status = workbench_status()
    fitness = mode_b_fitness_report()
    ai_paused = status["ai"]["status"] != "available"
    steps = [
        {
            "id": "install_workbench_or_use_cli",
            "title": "Use FreeForge Workbench shell (or CLI twin)",
            "detail": (
                "Desktop shell: build freeforge-workbench on Windows (see freeforge-workbench/README.md). "
                "Headless twin always works: python -m mainframe …"
            ),
            "required_for_mode_a": False,
        },
        {
            "id": "mode_a_works_offline",
            "title": "Deterministic core works without AI",
            "detail": "Edit, terminal, SCM, workflows, retrieve/patch/verify — no model required.",
            "required_for_mode_a": True,
        },
        {
            "id": "optional_ollama",
            "title": "Optional: install Ollama for Mode B",
            "detail": "https://ollama.com — free software; not a MAINFRAME paid dependency.",
            "required_for_mode_a": False,
        },
        {
            "id": "fitness",
            "title": "Run fitness before pulling weights",
            "detail": "python -m mainframe workbench fitness — doctor never auto-downloads models.",
            "required_for_mode_a": False,
            "recommended_ids": fitness.get("recommended_ids"),
        },
        {
            "id": "pull_fitted_model",
            "title": "Pull only a fitted model (user-initiated)",
            "detail": fitness.get("user_pull_steps"),
            "required_for_mode_a": False,
        },
        {
            "id": "probe",
            "title": "Confirm AI available",
            "detail": "python -m mainframe ai probe — Workbench chat stays paused until available.",
            "required_for_mode_a": False,
            "current_ai_status": status["ai"]["status"],
        },
        {
            "id": "live_eval",
            "title": "Measure live quality (do not invent)",
            "detail": (
                "After probe is available: python -m mainframe modeleval accept && "
                "python -m mainframe codingbench run --live. Until then live quality is unknown."
            ),
            "required_for_mode_a": False,
        },
    ]
    return {
        "ok": True,
        "product": "FreeForge Workbench",
        "ai_paused": ai_paused,
        "steps": steps,
        "honesty": {
            "exceeds_cursor": "unknown",
            "live_model_quality": fitness.get("live_coding_quality"),
            "zero_paid_compute": True,
            "physical_resources_user_borne": True,
        },
    }
