"""Workbench pin, overlay inventory, AI status for FreeForge IDE."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from mainframe.ai import probe_free_inference
from mainframe.config import ROOT
from mainframe.doctor import MODEL_CATALOG, measure_disk, measure_memory

PIN_PATH = ROOT / "workbench" / "PIN.json"
OVERLAY_DIR = ROOT / "workbench" / "overlay" / "freeforge"
CLONE_REL = ".workbench-build/vscode"


def load_pin() -> dict[str, Any]:
    if not PIN_PATH.is_file():
        return {}
    return json.loads(PIN_PATH.read_text(encoding="utf-8"))


def overlay_files() -> list[str]:
    if not OVERLAY_DIR.is_dir():
        return []
    out: list[str] = []
    for p in sorted(OVERLAY_DIR.rglob("*")):
        if p.is_file():
            out.append(str(p.relative_to(OVERLAY_DIR)).replace("\\", "/"))
    return out


def workbench_status() -> dict[str, Any]:
    pin = load_pin()
    probe = probe_free_inference()
    probe_d = probe.to_dict() if hasattr(probe, "to_dict") else dict(probe or {})
    clone = ROOT / CLONE_REL
    return {
        "ok": bool(pin.get("upstream") and OVERLAY_DIR.is_dir()),
        "product": pin.get("product") or "FreeForge Workbench",
        "pin": pin.get("upstream"),
        "inference_mode": (pin.get("inference") or {}).get("mode"),
        "overlay_dir": str(OVERLAY_DIR.relative_to(ROOT)).replace("\\", "/"),
        "overlay_files": overlay_files(),
        "clone_present": (clone / ".git").is_dir(),
        "clone_path": str(clone),
        "ai_probe": probe_d,
        "ai_state": probe_d.get("status"),
        "goal_doc": "docs/IDE_GOAL.md",
        "onboarding_doc": "docs/MODE_B_ONBOARDING.md",
        "hosted_ci_required": False,
        "code_signing_required": False,
        "void_services_vendored": False,
        "north_star": "match_or_exceed_cursor_claude_on_measured_suites_free_local_only",
        "north_star_status": "not_yet_achieved",
    }


def model_fit_report() -> dict[str, Any]:
    """Recommend local models from measured RAM — never downloads."""
    from mainframe.doctor import derive_resource_limits, estimate_model_fit, measure_cpu

    mem = measure_memory()
    disk = measure_disk()
    cpu = measure_cpu()
    try:
        limits = derive_resource_limits(mem, cpu, disk)
        fit = estimate_model_fit(mem, limits)
    except Exception as exc:  # noqa: BLE001
        avail = float(mem.get("available_gib") or 0)
        budget = max(0.0, avail - 4.0)
        rows = []
        for m in MODEL_CATALOG:
            w = float(m["weights_gib"])
            rows.append(
                {
                    "id": m["id"],
                    "weights_gib": w,
                    "recommendation": (
                        "eligible_to_consider" if w + 2.0 <= budget else "too_large"
                    ),
                }
            )
        return {
            "ok": True,
            "error_detail": str(exc),
            "available_gib": avail,
            "inference_budget_gib_est": budget,
            "recommended_ids": [
                r["id"] for r in rows if r["recommendation"] == "eligible_to_consider"
            ],
            "models": rows,
            "pull_required": True,
            "auto_download": False,
            "docs": "docs/MODE_B_ONBOARDING.md",
        }

    return {
        "ok": True,
        "memory": mem,
        "limits": {
            "optional_cpu_inference": (limits or {}).get("optional_cpu_inference"),
        },
        "fit": fit,
        "recommended_ids": (fit or {}).get("recommended_ids") or [],
        "pull_required": True,
        "auto_download": False,
        "docs": "docs/MODE_B_ONBOARDING.md",
        "note": "User must run ollama pull explicitly; MAINFRAME does not auto-download weights.",
    }
