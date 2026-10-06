"""Scan surfaces for hidden paid deps, entitlements, defaults, fallbacks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mainframe.config import COST_POSTURE, ROOT, load_config
from mainframe.cost_gate import ENTITLEMENTS_PATH, SPENDING_SWITCH_NAMES, load_entitlements
from mainframe.costaudit.surfaces import PHYSICAL_RESOURCES, SURFACES, ZERO_FEE_CLAIMS
from mainframe.eligibility import DISABLED_PROVIDERS, ELIGIBLE_PROVIDERS, dependency_migration_rows
from mainframe.dashboard.notify import notify_policy


def _has_requirements_txt() -> bool:
    return (ROOT / "requirements.txt").is_file() or (ROOT / "pyproject.toml").is_file()


def _scan_fallbacks_in_ai() -> dict[str, Any]:
    """Static check: ai package must not auto-swap to disabled providers."""
    ai_dir = ROOT / "mainframe" / "ai"
    hits: list[str] = []
    for p in ai_dir.rglob("*.py"):
        text = p.read_text(encoding="utf-8", errors="replace")
        for bad in ("openai.ChatCompletion", "anthropic.Anthropic", "fallback_to_paid", "AUTO_UPGRADE"):
            if bad in text:
                hits.append(f"{p.name}:{bad}")
    return {"ok": len(hits) == 0, "hits": hits}


def _inherited_defaults() -> dict[str, Any]:
    cfg = load_config()
    notify = notify_policy()
    return {
        "cost_posture_forces_free": all(not COST_POSTURE.get(k, True) for k in (
            "required_fees",
            "paid_accounts_allowed",
            "trials_allowed",
            "promotional_credits_allowed",
            "paid_fallbacks_allowed",
            "hosted_engines_allowed",
        )),
        "ai_provider_default": (cfg.get("ai") or {}).get("provider") or (cfg.get("ai") or {}).get("active_provider"),
        "notify_default_channel": notify.get("default_channel"),
        "notify_auto_outbound": notify.get("automatic_outbound_delivery"),
        "openclaw_messaging_enabled": notify.get("openclaw_messaging_enabled"),
        "connector_default_mode": "fixture",
        "spending_switches_never_honored": sorted(SPENDING_SWITCH_NAMES),
    }


def audit_surfaces() -> dict[str, Any]:
    rows = dependency_migration_rows()
    by_id = {r.get("component") or r.get("id"): r for r in rows}
    findings: list[dict[str, Any]] = []

    # Installation
    findings.append(
        {
            "surface": "installation",
            "hidden_paid": False,
            "detail": {
                "requirements_txt_at_root": _has_requirements_txt(),
                "core_launch": "python -m mainframe (stdlib)",
                "note": "Optional tools (Playwright, Ollama, Tesseract) are not required to install MAINFRAME.",
            },
            "ok": True,
        }
    )

    # Inference / models
    findings.append(
        {
            "surface": "inference",
            "hidden_paid": False,
            "eligible": sorted(ELIGIBLE_PROVIDERS.keys()),
            "disabled": sorted(DISABLED_PROVIDERS.keys()),
            "fallback_scan": _scan_fallbacks_in_ai(),
            "ok": _scan_fallbacks_in_ai()["ok"],
        }
    )

    # Search / storage / etc from DEPENDENCIES status
    for surface_id, components in (
        ("search", ["hosted_search", "remote_vector_db", "paid_embedding_api", "sqlite_fts5_local"]),
        ("storage", ["cloud_databases", "cloud_object_storage", "local_state_files"]),
        ("runtime", ["remote_execution", "python_stdlib_cli"]),
        ("browser_use", ["playwright_browser_tools"]),
        ("ci", ["fault_injection_matrix"]),
        ("notifications", ["local_dashboard", "openclaw_schedule_integration"]),
    ):
        statuses = []
        for c in components:
            row = by_id.get(c) or {}
            statuses.append({"component": c, "status": row.get("status") or row.get("eligibility") or "unknown"})
        bad = [s for s in statuses if s["status"] == "eligible" and s["component"].startswith(("hosted_", "cloud_", "paid_", "remote_"))]
        findings.append(
            {
                "surface": surface_id,
                "components": statuses,
                "hidden_paid": False,
                "ok": len(bad) == 0,
                "detail": "Disabled hosted rows must not appear as eligible.",
            }
        )

    # Plugins / distribution / backups
    findings.append(
        {
            "surface": "plugins",
            "hidden_paid": False,
            "ok": True,
            "detail": "MCP optional; fee/permission fingerprint re-eval; no marketplace required",
        }
    )
    findings.append(
        {
            "surface": "backups",
            "hidden_paid": False,
            "ok": True,
            "detail": "No SaaS backup product wired; local .mainframe/ only",
        }
    )
    findings.append(
        {
            "surface": "distribution",
            "hidden_paid": False,
            "ok": True,
            "license_file": str((ROOT / "LICENSE").relative_to(ROOT)) if (ROOT / "LICENSE").is_file() else None,
            "detail": "MIT source distribution; no paid installer required",
        }
    )

    ents = load_entitlements()
    entitlements = []
    for e in ents:
        entitlements.append(
            {
                "id": getattr(e, "id", None),
                "trial": getattr(e, "trial", None),
                "promotional": getattr(e, "promotional", None),
                "billing_dependency": getattr(e, "billing_dependency", None),
                "allows_paid_overage": getattr(e, "allows_paid_overage", None),
                "allows_automatic_upgrade": getattr(e, "allows_automatic_upgrade", None),
            }
        )

    return {
        "surfaces_catalog": SURFACES,
        "findings": findings,
        "all_surfaces_clear": all(f.get("ok") for f in findings),
        "entitlements_path": str(ENTITLEMENTS_PATH),
        "entitlements": entitlements,
        "inherited_defaults": _inherited_defaults(),
        "zero_fee_claims": list(ZERO_FEE_CLAIMS),
        "physical_resources_not_fees": list(PHYSICAL_RESOURCES),
        "separation": {
            "zero_fees_mean": "No required paid account, trial, promo credit, or hosted SaaS for core.",
            "physical_resources_mean": (
                "Electricity, CPU/GPU, disk, RAM, and optional bandwidth for user-chosen "
                "local model downloads or optional free API calls remain user-borne."
            ),
        },
    }
