"""Workbench product status — shell pin, AI gate, overlay presence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mainframe import __version__
from mainframe.ai import probe_free_inference
from mainframe.config import ROOT
from mainframe.workbench.fitness import mode_b_fitness_report

WORKBENCH_ROOT = ROOT / "freeforge-workbench"
PIN_PATH = WORKBENCH_ROOT / "PINS.json"


def load_workbench_pin() -> dict[str, Any]:
    if not PIN_PATH.is_file():
        return {"present": False}
    data = json.loads(PIN_PATH.read_text(encoding="utf-8"))
    data["present"] = True
    return data


def workbench_status() -> dict[str, Any]:
    probe = probe_free_inference()
    probe_d = probe.to_dict() if hasattr(probe, "to_dict") else {}
    ai_available = probe_d.get("status") in ("available", "ok")
    pin = load_workbench_pin()
    overlay = WORKBENCH_ROOT / "overlay" / "src" / "vs" / "workbench" / "contrib" / "freeforge"
    media = WORKBENCH_ROOT / "overlay" / "media"
    return {
        "ok": True,
        "product": "FreeForge Workbench",
        "mainframe_version": __version__,
        "positioning": (
            "VS Code-class shell + FreeForge local agent — CLI alone is not the IDE"
        ),
        "workbench_root": str(WORKBENCH_ROOT),
        "pin": pin,
        "overlay_present": overlay.is_dir(),
        "media_present": media.is_dir(),
        "ai": {
            "mode": "B_optional_cpu",
            "status": "available" if ai_available else "paused",
            "probe": probe_d.get("status"),
            "detail": probe_d.get("detail"),
            "ui_must_show_paused_when_unavailable": True,
        },
        "deterministic_core_without_ai": True,
        "claims": {
            "exceeds_cursor": "unknown",
            "percentile_rank": "unknown",
            "live_model_quality": "unknown" if not ai_available else "pending_eval",
        },
        "fitness_summary": {
            "recommended_ids": mode_b_fitness_report().get("recommended_ids"),
            "ollama_reachable": ai_available,
        },
    }
