"""Workbench pin/overlay status and Mode B model-fit summary."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from mainframe.ai import probe_free_inference
from mainframe.config import ROOT
from mainframe.doctor import (
    derive_resource_limits,
    estimate_model_fit,
    measure_cpu,
    measure_disk,
    measure_memory,
)

PIN_PATH = ROOT / "workbench" / "PIN.json"
OVERLAY = ROOT / "workbench" / "overlay" / "freeforge"
GOAL = ROOT / "docs" / "IDE_GOAL.md"


def load_pin() -> dict[str, Any]:
    return json.loads(PIN_PATH.read_text(encoding="utf-8"))


def workbench_status() -> dict[str, Any]:
    pin = load_pin() if PIN_PATH.is_file() else {}
    clone_rel = (pin.get("build") or {}).get("clone_dir") or ".workbench-build/vscode"
    clone = ROOT / clone_rel
    overlay_in_clone = clone / "src" / "vs" / "workbench" / "contrib" / "freeforge"
    probe = probe_free_inference()
    probe_d = probe.to_dict() if hasattr(probe, "to_dict") else dict(probe or {})
    return {
        "product": "FreeForge Workbench",
        "goal_doc": "docs/IDE_GOAL.md",
        "goal_doc_present": GOAL.is_file(),
        "pin": {
            "present": PIN_PATH.is_file(),
            "tag": (pin.get("upstream") or {}).get("tag"),
            "repo": (pin.get("upstream") or {}).get("repo"),
        },
        "overlay": {
            "present": (OVERLAY / "freeforge.contribution.ts").is_file(),
            "path": str(OVERLAY.relative_to(ROOT)).replace("\\", "/"),
            "files": sorted(p.name for p in OVERLAY.iterdir() if p.is_file()) if OVERLAY.is_dir() else [],
        },
        "clone": {
            "path": str(clone.relative_to(ROOT)).replace("\\", "/") if clone.exists() else clone_rel,
            "exists": clone.is_dir() and (clone / ".git").exists(),
            "overlay_applied": overlay_in_clone.is_dir(),
        },
        "ai": {
            "status": probe_d.get("status"),
            "provider": probe_d.get("provider"),
            "detail": probe_d.get("detail"),
            "ollama_on_path": shutil.which("ollama") is not None,
        },
        "north_star": "match_or_exceed_cursor_claude_on_measured_suites_free_only",
        "cursor_claude_comparison": "unknown",
        "hosted_ci_required": False,
    }


def model_fit_report() -> dict[str, Any]:
    """Recommend local models from doctor fit math — never downloads."""
    mem = measure_memory()
    cpu = measure_cpu()
    disk = measure_disk()
    limits = derive_resource_limits(mem, cpu, disk)
    budget = float((limits.get("optional_cpu_inference") or {}).get("ram_budget_gib") or 0)
    fit = estimate_model_fit(mem, limits)
    probe = probe_free_inference().to_dict()
    recommended = fit.get("recommended_ids") or []
    # Map catalog ids to plausible ollama pull names (user still chooses explicitly)
    pull_hints = []
    for rid in recommended[:3]:
        if "0.5b" in rid:
            pull_hints.append("ollama pull qwen2.5:0.5b")
        elif "qwen2.5-3b" in rid or "qwen2.5-coder" in rid:
            pull_hints.append("ollama pull qwen2.5-coder:3b")
        elif "llama3.2-3b" in rid:
            pull_hints.append("ollama pull llama3.2:3b")
        elif "tinyllama" in rid:
            pull_hints.append("ollama pull tinyllama")
        else:
            pull_hints.append(f"# see doctor catalog id: {rid}")
    if not recommended:
        pull_hints.append(
            "# No catalog model verified_fit at current available RAM — "
            "close browsers/IDE windows and re-run workbench model-fit, "
            "or free RAM before ollama pull."
        )
    return {
        "ok": True,
        "memory": {k: mem.get(k) for k in ("measured", "available_gib", "total_gib", "source")},
        "inference_budget_gib": budget,
        "fit": fit,
        "recommended_ids": recommended,
        "explicit_pull_hints": pull_hints,
        "ai_probe": probe,
        "downloaded_by_mainframe": False,
        "onboarding_doc": "docs/MODE_B_ONBOARDING.md",
        "note": (
            "Install Ollama, then pull a recommended model explicitly. "
            "MAINFRAME does not auto-download weights."
            if probe.get("status") != "available"
            else "Local inference available — run modeleval/codingbench --live for quality cells."
        ),
    }


def _fit_from_catalog(avail: float, budget: float, measured: bool) -> dict[str, Any]:
    from mainframe.doctor import (
        KV_GIB_PER_BPARAM_PER_1K_CTX,
        MODEL_CATALOG,
        RUNTIME_OVERHEAD_GIB,
        SAFETY_MARGIN_GIB,
    )

    rows = []
    for model in MODEL_CATALOG:
        weights = float(model["weights_gib"])
        params_b = float(model["params_b"])
        ctx = int(model["default_ctx"])
        kv = params_b * (ctx / 1000.0) * KV_GIB_PER_BPARAM_PER_1K_CTX
        total_est = weights + kv + RUNTIME_OVERHEAD_GIB
        verified = measured and (total_est + SAFETY_MARGIN_GIB) <= avail and total_est <= budget and budget > 0
        rows.append(
            {
                "id": model["id"],
                "total_gib_est": round(total_est, 2),
                "verified_fit": verified,
                "recommendation": "eligible_to_consider" if verified else "do_not_recommend",
            }
        )
    return {
        "models": rows,
        "recommended_ids": [r["id"] for r in rows if r["recommendation"] == "eligible_to_consider"],
        "catalog_policy": "No model files downloaded.",
    }


def run_overlay_check() -> dict[str, Any]:
    check = OVERLAY / "check.mjs"
    if not check.is_file():
        return {"ok": False, "error": "overlay_check_missing"}
    node = shutil.which("node")
    if not node:
        return {"ok": False, "error": "node_not_on_path", "note": "Overlay TS present; node check skipped"}
    try:
        p = subprocess.run(
            [node, str(check)],
            cwd=str(OVERLAY),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return {
            "ok": p.returncode == 0,
            "exit_code": p.returncode,
            "stdout": (p.stdout or "").strip(),
            "stderr": (p.stderr or "").strip()[-300:],
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def run_bootstrap(*, skip_clone: bool = False) -> dict[str, Any]:
    """Apply overlay; optionally clone vscode pin (network + disk heavy)."""
    script = ROOT / "workbench" / "scripts" / "bootstrap.ps1"
    if not script.is_file():
        return {"ok": False, "error": "bootstrap_script_missing"}
    if skip_clone:
        # Dry apply into a staging dir under .workbench-build/overlay-staging
        staging = ROOT / ".workbench-build" / "overlay-staging" / "freeforge"
        staging.mkdir(parents=True, exist_ok=True)
        for p in OVERLAY.iterdir():
            if p.is_file():
                (staging / p.name).write_bytes(p.read_bytes())
        return {
            "ok": True,
            "mode": "overlay_staging_only",
            "staging": str(staging.relative_to(ROOT)).replace("\\", "/"),
            "clone_skipped": True,
            "note": "Pass full bootstrap without --skip-clone to git clone vscode pin.",
        }
    if sys.platform != "win32":
        return {"ok": False, "error": "bootstrap_ps1_windows_only", "documented_not_tested": True}
    try:
        p = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                "-RepoRoot",
                str(ROOT),
            ],
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        return {
            "ok": p.returncode == 0 and "ok=true" in (p.stdout or ""),
            "exit_code": p.returncode,
            "stdout_tail": (p.stdout or "")[-800:],
            "stderr_tail": (p.stderr or "")[-400:],
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "bootstrap_timeout"}
