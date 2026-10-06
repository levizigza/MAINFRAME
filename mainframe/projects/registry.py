"""Project identity — explicit IDs, confidentiality, egress, retention."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.config import STATE_DIR, ensure_state

REGISTRY_NAME = "projects_registry.json"

# Confidentiality levels (higher = stricter egress)
CONFIDENTIALITY = ("public", "internal", "confidential", "local_only")

# Data classes that may or may not leave the device depending on policy
DATA_CLASSES = (
    "workspace_source",
    "memory_entries",
    "cache_payloads",
    "artifacts",
    "browser_cookies",
    "secrets",
    "permission_grants",
    "telemetry_diagnostics",
)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_project_id(project_id: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", (project_id or "").strip())
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError("invalid_project_id")
    return cleaned[:64]


def projects_root() -> Path:
    ensure_state()
    root = STATE_DIR / "projects"
    root.mkdir(parents=True, exist_ok=True)
    return root


def registry_path() -> Path:
    return projects_root() / REGISTRY_NAME


def project_home(project_id: str) -> Path:
    pid = safe_project_id(project_id)
    home = projects_root() / pid
    for sub in (
        "workspace",
        "artifacts",
        "memory",
        "cache",
        "secrets",
        "browser_profile",
        "grants",
        "exports",
    ):
        (home / sub).mkdir(parents=True, exist_ok=True)
    return home


def default_egress_policy(*, confidentiality: str) -> dict[str, Any]:
    """
    What may leave the device, and which eligible providers may receive it.

    Free hosted inference is NOT automatically suitable for confidential material.
    """
    c = confidentiality if confidentiality in CONFIDENTIALITY else "internal"
    if c == "local_only":
        return {
            "leave_device": False,
            "allowed_data_classes_off_device": [],
            "eligible_providers_may_receive": [],
            "free_hosted_inference_ok_for_confidential": False,
            "note": "Local-only project: no data may leave the device; pause without approved local model.",
        }
    if c == "confidential":
        return {
            "leave_device": False,
            "allowed_data_classes_off_device": [],
            "eligible_providers_may_receive": [],
            "free_hosted_inference_ok_for_confidential": False,
            "note": "Confidential: free hosted inference is not automatically suitable.",
        }
    if c == "internal":
        return {
            "leave_device": True,
            "allowed_data_classes_off_device": ["telemetry_diagnostics"],
            "eligible_providers_may_receive": ["ollama_local"],
            "free_hosted_inference_ok_for_confidential": False,
            "note": "Internal: only explicitly listed classes may leave; hosted free inference not auto-approved.",
        }
    # public
    return {
        "leave_device": True,
        "allowed_data_classes_off_device": [
            "workspace_source",
            "artifacts",
            "telemetry_diagnostics",
        ],
        "eligible_providers_may_receive": ["ollama_local"],
        "free_hosted_inference_ok_for_confidential": False,
        "note": "Public: still never auto-send secrets/grants/browser cookies.",
    }


def _empty_registry() -> dict[str, Any]:
    return {
        "format_version": "1.0",
        "updated_at": _utc(),
        "projects": {},
        "note": "Explicit project identity binds workspaces, memories, caches, secrets, browser profiles, artifacts, grants.",
    }


def load_registry() -> dict[str, Any]:
    path = registry_path()
    if not path.is_file():
        reg = _empty_registry()
        path.write_text(json.dumps(reg, indent=2) + "\n", encoding="utf-8")
        return reg
    return json.loads(path.read_text(encoding="utf-8"))


def save_registry(reg: dict[str, Any]) -> None:
    reg["updated_at"] = _utc()
    registry_path().write_text(json.dumps(reg, indent=2) + "\n", encoding="utf-8")


def create_project(
    project_id: str,
    *,
    workspace: str | Path | None = None,
    confidentiality: str = "internal",
    display_name: str | None = None,
    retention_days: int | None = 90,
    approved_local_models: list[str] | None = None,
) -> dict[str, Any]:
    pid = safe_project_id(project_id)
    if confidentiality not in CONFIDENTIALITY:
        return {"ok": False, "error": "invalid_confidentiality", "allowed": list(CONFIDENTIALITY)}
    reg = load_registry()
    if pid in (reg.get("projects") or {}):
        return {"ok": False, "error": "project_exists", "project_id": pid}

    home = project_home(pid)
    ws = Path(workspace).resolve() if workspace else (home / "workspace")
    ws.mkdir(parents=True, exist_ok=True)

    record = {
        "project_id": pid,
        "display_name": display_name or pid,
        "workspace": str(ws),
        "home": str(home),
        "confidentiality": confidentiality,
        "local_only": confidentiality == "local_only",
        "egress": default_egress_policy(confidentiality=confidentiality),
        "retention_days": retention_days,
        "approved_local_models": list(approved_local_models or ["ollama_local"]),
        "paths": {
            "artifacts": str(home / "artifacts"),
            "memory": str(home / "memory"),
            "cache": str(home / "cache"),
            "secrets": str(home / "secrets"),
            "browser_profile": str(home / "browser_profile"),
            "grants": str(home / "grants"),
        },
        "created_at": _utc(),
        "updated_at": _utc(),
        "deleted": False,
    }
    reg.setdefault("projects", {})[pid] = record
    save_registry(reg)
    return {"ok": True, "project": record}


def get_project(project_id: str) -> dict[str, Any] | None:
    try:
        pid = safe_project_id(project_id)
    except ValueError:
        return None
    reg = load_registry()
    rec = (reg.get("projects") or {}).get(pid)
    if not rec or rec.get("deleted"):
        return None
    return rec


def list_projects() -> list[dict[str, Any]]:
    reg = load_registry()
    return [p for p in (reg.get("projects") or {}).values() if not p.get("deleted")]


def update_retention(project_id: str, *, retention_days: int | None) -> dict[str, Any]:
    rec = get_project(project_id)
    if not rec:
        return {"ok": False, "error": "project_not_found"}
    reg = load_registry()
    pid = rec["project_id"]
    reg["projects"][pid]["retention_days"] = retention_days
    reg["projects"][pid]["updated_at"] = _utc()
    save_registry(reg)
    return {"ok": True, "project_id": pid, "retention_days": retention_days}


def update_egress(
    project_id: str,
    *,
    allowed_data_classes_off_device: list[str] | None = None,
    eligible_providers_may_receive: list[str] | None = None,
) -> dict[str, Any]:
    rec = get_project(project_id)
    if not rec:
        return {"ok": False, "error": "project_not_found"}
    if rec.get("local_only") or rec.get("confidentiality") in {"local_only", "confidential"}:
        # Refuse expanding leave-device for confidential/local_only
        if allowed_data_classes_off_device:
            bad = [c for c in allowed_data_classes_off_device if c in {"secrets", "permission_grants", "browser_cookies"}]
            if bad or rec.get("local_only"):
                return {
                    "ok": False,
                    "error": "egress_expansion_refused",
                    "confidentiality": rec.get("confidentiality"),
                    "free_hosted_inference_ok_for_confidential": False,
                }
    reg = load_registry()
    pid = rec["project_id"]
    eg = dict(reg["projects"][pid].get("egress") or {})
    if allowed_data_classes_off_device is not None:
        # Never allow secrets/grants/cookies off device via this API
        blocked = {"secrets", "permission_grants", "browser_cookies"}
        eg["allowed_data_classes_off_device"] = [
            c for c in allowed_data_classes_off_device if c not in blocked and c in DATA_CLASSES
        ]
    if eligible_providers_may_receive is not None:
        eg["eligible_providers_may_receive"] = list(eligible_providers_may_receive)
    eg["free_hosted_inference_ok_for_confidential"] = False
    reg["projects"][pid]["egress"] = eg
    reg["projects"][pid]["updated_at"] = _utc()
    save_registry(reg)
    return {"ok": True, "project_id": pid, "egress": eg}
