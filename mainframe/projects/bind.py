"""Bind tool and workflow runs to an explicit project identity."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mainframe.projects.egress import local_only_inference_gate, may_leave_device
from mainframe.projects.registry import get_project


def require_project_id(project_id: str | None) -> dict[str, Any]:
    if not project_id or not str(project_id).strip():
        return {
            "ok": False,
            "bound": False,
            "error": "project_id_required",
            "note": "Every tool and workflow run must declare an explicit project identity.",
        }
    rec = get_project(project_id)
    if not rec:
        return {"ok": False, "bound": False, "error": "project_not_found", "project_id": project_id}
    return {
        "ok": True,
        "bound": True,
        "project_id": rec["project_id"],
        "workspace": rec.get("workspace"),
        "confidentiality": rec.get("confidentiality"),
        "local_only": bool(rec.get("local_only")),
    }


def bind_tool_run(
    *,
    project_id: str | None,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    gate = require_project_id(project_id)
    if not gate.get("ok"):
        return {**gate, "tool": tool_name, "side_effects": False}
    # Path-like args must stay in project (checked by caller via isolation.resolve_project_path)
    return {
        **gate,
        "tool": tool_name,
        "binding": "tool_run",
        "arguments_keys": sorted((arguments or {}).keys()),
    }


def bind_workflow_run(
    *,
    project_id: str | None,
    workflow_id: str,
    work_dir: Path | None = None,
) -> dict[str, Any]:
    gate = require_project_id(project_id)
    if not gate.get("ok"):
        return {**gate, "workflow_id": workflow_id, "side_effects": False}
    rec = get_project(project_id)  # type: ignore[arg-type]
    assert rec
    # Prefer project workspace when work_dir omitted
    wd = work_dir or Path(rec["workspace"])
    return {
        **gate,
        "workflow_id": workflow_id,
        "binding": "workflow_run",
        "work_dir": str(wd),
        "artifacts_dir": rec["paths"]["artifacts"],
    }


def gate_inference_for_project(
    project_id: str,
    *,
    available_local_models: list[str] | None = None,
    intended_provider: str | None = None,
    data_class: str = "workspace_source",
) -> dict[str, Any]:
    """Combine local-only pause with egress: confidential never auto-hosts."""
    local = local_only_inference_gate(
        project_id, available_local_models=available_local_models
    )
    if local.get("paused"):
        return {**local, "inference_allowed": False}
    if intended_provider:
        eg = may_leave_device(
            project_id, data_class=data_class, provider_id=intended_provider
        )
        if not eg.get("allowed"):
            return {
                **eg,
                "inference_allowed": False,
                "paused": True if intended_provider != "ollama_local" else False,
                "fallback_used": False,
            }
    return {
        "ok": True,
        "inference_allowed": True,
        "paused": False,
        "provider": intended_provider or (local.get("approved_model") or "ollama_local"),
        "free_hosted_inference_ok_for_confidential": False,
    }
