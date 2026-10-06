"""Choose a small candidate from doctor RAM measurements — no download."""

from __future__ import annotations

from typing import Any

from mainframe.doctor import (
    derive_resource_limits,
    estimate_model_fit,
    measure_cpu,
    measure_disk,
    measure_memory,
)
from mainframe.local_model.catalog import CANDIDATES, candidate_by_id
from mainframe.local_model.cloud_guard import is_cloud_model_name
from mainframe.local_model.ollama_native import list_local_models


def select_candidate(
    *,
    base_url: str = "http://127.0.0.1:11434",
    prefer_installed: bool = True,
) -> dict[str, Any]:
    mem = measure_memory()
    cpu = measure_cpu()
    disk = measure_disk()
    limits = derive_resource_limits(mem, cpu, disk)
    fit = estimate_model_fit(mem, limits)
    recommended_ids = list(fit.get("recommended_ids") or [])

    installed: list[str] = []
    tags = list_local_models(base_url, timeout_s=0.8)
    if tags.get("ok"):
        installed = [n for n in (tags.get("models") or []) if not is_cloud_model_name(n)]

    # Prefer smallest recommended that is installed; else smallest recommended.
    ordered = []
    for cid in recommended_ids:
        c = candidate_by_id(cid)
        if c:
            ordered.append(c)
    if not ordered:
        # Fall back to catalog small class in catalog order
        ordered = [dict(c) for c in CANDIDATES if c.get("size_class") == "small"]

    selected = None
    selection_reason = "none_fit"
    if prefer_installed and installed:
        for c in ordered:
            oname = c["ollama_name"]
            # match exact or prefix
            match = next(
                (
                    n
                    for n in installed
                    if n == oname or n.startswith(oname.split(":")[0] + ":") or n == oname.split(":")[0]
                ),
                None,
            )
            if match:
                selected = {**c, "resolved_ollama_name": match, "installed": True}
                selection_reason = "doctor_fit_and_installed"
                break
        if selected is None:
            # Installed but not in recommended — still report smallest recommended for download
            if ordered:
                selected = {
                    **ordered[0],
                    "resolved_ollama_name": ordered[0]["ollama_name"],
                    "installed": False,
                }
                selection_reason = "doctor_fit_not_installed"
            else:
                selection_reason = "installed_but_no_catalog_match"
    elif ordered:
        selected = {
            **ordered[0],
            "resolved_ollama_name": ordered[0]["ollama_name"],
            "installed": False,
        }
        selection_reason = "doctor_fit_not_installed"

    return {
        "ok": True,
        "memory": {
            "available_gib": mem.get("available_gib"),
            "measured": mem.get("measured"),
        },
        "inference_budget_gib": limits["optional_cpu_inference"]["ram_budget_gib"],
        "doctor_recommended_ids": recommended_ids,
        "installed_local_models": installed,
        "selected": selected,
        "selection_reason": selection_reason,
        "download_required": bool(selected) and not selected.get("installed"),
        "auto_download": False,
        "coding_quality_assumed": False,
        "note": (
            "Selection uses doctor fit estimates only. "
            "CPU/RAM fit does not imply acceptable coding quality."
        ),
        "frontier_parity_claimed": False,
    }
