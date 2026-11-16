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

# Rough runtime working-set GiB (weights + KV + overhead) for installed tags.
# Order-of-magnitude only — used to avoid picking a 3B first when free RAM is ~1 GiB.
_RUNTIME_GIB_BY_HINT: list[tuple[str, float]] = [
    ("0.5b", 0.7),
    ("1.1b", 1.1),
    ("1.5b", 1.4),
    ("3b", 2.4),
    ("7b", 5.0),
    ("8b", 5.5),
    ("14b", 9.0),
    ("27b", 17.0),
    ("32b", 20.0),
]


def estimate_runtime_gib(model_name: str) -> float:
    """Estimate load cost from the tag name; unknown tags treated as mid-size."""
    low = (model_name or "").lower()
    for hint, gib in _RUNTIME_GIB_BY_HINT:
        if hint in low:
            return gib
    # Bare family tags without a size suffix — assume mid-small, not frontier.
    return 2.5


def pick_runtime_model(
    installed: list[str],
    *,
    available_gib: float | None = None,
    preferred: str | None = None,
) -> dict[str, Any]:
    """
    Pick an installed local model for inference.

    Prefer an explicit preferred tag when installed. Otherwise pick the *largest*
    installed model that fits a conservative fraction of measured free RAM.
    If none fit, pick the *smallest* installed and label ``unverified_fit``
    (still free/local — do not invent a successful large-model load).
    """
    local = [n for n in installed if n and not is_cloud_model_name(n)]
    if not local:
        return {
            "ok": False,
            "model": None,
            "verified_fit": False,
            "reason": "no_installed_local_models",
        }

    if preferred and preferred in local:
        est = estimate_runtime_gib(preferred)
        fits = available_gib is None or available_gib >= est
        return {
            "ok": True,
            "model": preferred,
            "verified_fit": bool(fits),
            "estimated_runtime_gib": est,
            "available_gib": available_gib,
            "reason": "preferred_installed" if fits else "preferred_unverified_fit",
            "candidates": local,
        }

    ranked = sorted(local, key=estimate_runtime_gib)
    if available_gib is None:
        # No measurement: prefer smallest (safest on constrained hosts).
        chosen = ranked[0]
        return {
            "ok": True,
            "model": chosen,
            "verified_fit": False,
            "estimated_runtime_gib": estimate_runtime_gib(chosen),
            "available_gib": None,
            "reason": "smallest_no_ram_measurement",
            "candidates": ranked,
        }

    # Leave headroom for OS + IDE (~40% of free RAM for model working set).
    budget = max(0.0, float(available_gib) * 0.6)
    fitting = [n for n in ranked if estimate_runtime_gib(n) <= budget]
    if fitting:
        # Largest that still fits.
        chosen = fitting[-1]
        return {
            "ok": True,
            "model": chosen,
            "verified_fit": True,
            "estimated_runtime_gib": estimate_runtime_gib(chosen),
            "available_gib": available_gib,
            "budget_gib": round(budget, 2),
            "reason": "largest_verified_fit",
            "candidates": ranked,
        }

    chosen = ranked[0]
    return {
        "ok": True,
        "model": chosen,
        "verified_fit": False,
        "estimated_runtime_gib": estimate_runtime_gib(chosen),
        "available_gib": available_gib,
        "budget_gib": round(budget, 2),
        "reason": "smallest_unverified_fit",
        "candidates": ranked,
        "note": "No installed model verified against measured free RAM; measuring anyway.",
    }


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

    runtime = pick_runtime_model(
        installed,
        available_gib=float(mem.get("available_gib") or 0) if mem.get("measured") else None,
    )

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
        "runtime_pick": runtime,
        "download_required": bool(selected) and not selected.get("installed"),
        "auto_download": False,
        "coding_quality_assumed": False,
        "note": (
            "Selection uses doctor fit estimates only. "
            "CPU/RAM fit does not imply acceptable coding quality."
        ),
        "frontier_parity_claimed": False,
    }
