"""Narrow FreeForge visual bridge — edit/invoke workflows; reuse scheduler + effect ledger."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mainframe.schedule.openclaw_payload import COMMAND_POLICY_OWNER, SCHEDULER_OWNER
from mainframe.visual.eval_nodered import evaluate_nodered_optional
from mainframe.visual.secrets_policy import secrets_policy
from mainframe.visual.store import list_workflows, load_saved, save_workflow, workflows_root
from mainframe.workflows.plan import dry_run_plan
from mainframe.workflows.receipts import WorkflowReceiptStore
from mainframe.workflows.runner import run_workflow
from mainframe.workflows.schema import normalize_workflow
from mainframe.workflows.validate import validate_workflow

DEFAULT_CAPS = {
    "local.read",
    "local.write",
    "local.artifact",
    "human.decide",
}


def bridge_status() -> dict[str, Any]:
    eval_nr = evaluate_nodered_optional()
    return {
        "ok": True,
        "visual_kind": "simple_local_form",
        "nodered": eval_nr,
        "scheduler_owner": SCHEDULER_OWNER,
        "command_policy_owner": COMMAND_POLICY_OWNER,
        "effect_ledger": "freeforge_workflow_receipts",
        "dual_trigger_forbidden": True,
        "secrets": secrets_policy(),
        "removable": True,
        "workflows_root": str(workflows_root()),
        "note": (
            "Visual UI only edits/invokes FreeForge. Scheduling remains OpenClaw/FreeForge. "
            "Removing this package leaves saved workflows and schedules intact."
        ),
    }


def describe_workflow(wf: dict[str, Any], *, available_capabilities: set[str] | None = None) -> dict[str, Any]:
    caps = available_capabilities if available_capabilities is not None else set(DEFAULT_CAPS)
    norm = normalize_workflow(wf)
    validation = validate_workflow(norm, available_capabilities=caps, strict_capabilities=True)
    plan = dry_run_plan(norm, available_capabilities=caps, strict_capabilities=False)

    blocked_ai = []
    for step in norm.get("steps") or []:
        if step.get("kind") != "ai":
            continue
        # AI blocked when capability missing or validation flagged
        if "ai.infer" not in caps:
            blocked_ai.append(
                {
                    "step_id": step.get("id"),
                    "handler": step.get("handler"),
                    "reason": "ai.infer_capability_unavailable",
                    "blocked": True,
                }
            )
        else:
            blocked_ai.append(
                {
                    "step_id": step.get("id"),
                    "handler": step.get("handler"),
                    "reason": "eligible_when_runtime_available",
                    "blocked": False,
                }
            )

    # Also surface validation errors about AI
    for err in validation.get("errors") or []:
        if "ai" in str(err).lower():
            blocked_ai.append({"validation_error": err, "blocked": True})

    return {
        "id": norm.get("id"),
        "format_version": norm.get("format_version"),
        "schemas": {
            "inputs": norm.get("inputs"),
            "outputs": norm.get("outputs"),
            "steps": [
                {
                    "id": s.get("id"),
                    "kind": s.get("kind"),
                    "handler": s.get("handler"),
                    "inputs": s.get("inputs"),
                    "outputs": s.get("outputs"),
                }
                for s in norm.get("steps") or []
            ],
        },
        "permissions": norm.get("permissions") or [],
        "blocked_ai_steps": blocked_ai,
        "validation": {"ok": validation.get("ok"), "errors": validation.get("errors")},
        "plan": {
            "ok": plan.get("ok"),
            "step_order": plan.get("step_order"),
            "blocked": plan.get("blocked"),
        },
    }


def create_simple_reporting_workflow(
    *,
    workflow_id: str = "visual_reporting",
    title: str = "Visual bridge report",
) -> dict[str, Any]:
    """Minimal deterministic workflow creatable from the visual form."""
    return {
        "format_version": "1.0",
        "id": workflow_id,
        "description": "Created via FreeForge visual bridge (simple local form)",
        "permissions": ["local.read", "local.write", "local.artifact", "human.decide"],
        "artifacts": [
            {"id": "report_json", "path": "report.json", "content_type": "application/json"}
        ],
        "inputs": {
            "type": "object",
            "properties": {"title": {"type": "string"}},
            "additionalProperties": False,
        },
        "outputs": {
            "type": "object",
            "properties": {
                "artifact_path": {"type": "string"},
                "sha256": {"type": "string"},
            },
        },
        "output_steps": ["write_report"],
        "steps": [
            {
                "id": "load",
                "kind": "deterministic",
                "handler": "load_records",
                "depends_on": [],
                "permissions": ["local.read"],
                "effects": [],
                "args": {"path": "records.json"},
                "inputs": {"type": "object", "properties": {}},
                "outputs": {
                    "type": "object",
                    "required": ["records", "count"],
                    "properties": {"records": {"type": "array"}, "count": {"type": "integer"}},
                },
            },
            {
                "id": "transform",
                "kind": "deterministic",
                "handler": "transform_report",
                "depends_on": ["load"],
                "permissions": ["local.read"],
                "effects": [],
                "args": {"title": title},
                "inputs": {
                    "type": "object",
                    "required": ["records", "count"],
                    "properties": {
                        "records": {"type": "array"},
                        "count": {"type": "integer"},
                        "title": {"type": "string"},
                    },
                },
                "outputs": {
                    "type": "object",
                    "required": ["report"],
                    "properties": {"report": {"type": "object"}},
                },
            },
            {
                "id": "approve",
                "kind": "human",
                "handler": "human_approve",
                "depends_on": ["transform"],
                "permissions": ["human.decide"],
                "effects": [],
                "condition": {"field": "report", "op": "exists"},
                "inputs": {"type": "object", "properties": {"report": {"type": "object"}}},
                "outputs": {
                    "type": "object",
                    "required": ["decision"],
                    "properties": {
                        "decision": {"type": "string"},
                        "approved": {"type": "boolean"},
                    },
                },
            },
            {
                "id": "write_report",
                "kind": "deterministic",
                "handler": "write_artifact",
                "depends_on": ["transform", "approve"],
                "permissions": ["local.write", "local.artifact"],
                "effects": ["write_report_json"],
                "mutates": True,
                "artifact_refs": ["report_json"],
                "args": {"path": "report.json"},
                "condition": {"field": "approved", "op": "eq", "value": True},
                "inputs": {
                    "type": "object",
                    "required": ["report"],
                    "properties": {
                        "report": {"type": "object"},
                        "decision": {"type": "string"},
                        "approved": {"type": "boolean"},
                    },
                    "additionalProperties": True,
                },
                "outputs": {
                    "type": "object",
                    "required": ["artifact_path", "sha256"],
                    "properties": {
                        "artifact_path": {"type": "string"},
                        "sha256": {"type": "string"},
                    },
                },
            },
        ],
        "secret_refs": [],  # secrets outside flow
    }


def invoke_workflow(
    wf: dict[str, Any],
    *,
    work_dir: Path,
    inputs: dict[str, Any] | None = None,
    records: list[dict[str, Any]] | None = None,
    available_capabilities: set[str] | None = None,
    store: WorkflowReceiptStore | None = None,
) -> dict[str, Any]:
    """Invoke FreeForge runner — same path as CLI (effect ledger + receipts)."""
    caps = available_capabilities if available_capabilities is not None else set(DEFAULT_CAPS)
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    if records is not None:
        (work_dir / "records.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    elif not (work_dir / "records.json").is_file():
        # default small fixture
        (work_dir / "records.json").write_text(
            json.dumps(
                [
                    {"id": "a1", "label": "Alpha", "value": 10},
                    {"id": "b2", "label": "Beta", "value": 20},
                ],
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    result = run_workflow(
        wf,
        inputs=inputs or {},
        work_dir=work_dir,
        available_capabilities=caps,
        strict_capabilities=True,
        store=store,
    )
    desc = describe_workflow(wf, available_capabilities=caps)
    return {
        "ok": bool(result.get("ok")),
        "execution": result,
        "exposed": {
            "schemas": desc["schemas"],
            "permissions": desc["permissions"],
            "blocked_ai_steps": desc["blocked_ai_steps"],
            "results": {
                "ok": result.get("ok"),
                "outputs": result.get("outputs"),
                "step_outputs": result.get("step_outputs"),
                "error": result.get("error"),
                "run_id": result.get("run_id"),
            },
        },
        "scheduler_owner": SCHEDULER_OWNER,
        "effect_ledger_used": True,
        "invoked_via": "freeforge_visual_bridge",
    }


def refuse_nodered_independent_trigger(request: dict[str, Any]) -> dict[str, Any]:
    """Node-RED must not independently run the same trigger as OpenClaw/FreeForge."""
    kind = str(request.get("trigger_kind") or request.get("kind") or "")
    owner = str(request.get("scheduler_owner") or "")
    if kind in {"inject_repeat", "nodered_cron", "node_red_schedule", "independent_timer"}:
        return {
            "ok": False,
            "refused": True,
            "error": "dual_trigger_forbidden",
            "detail": (
                "Node-RED must not schedule FreeForge workflows independently. "
                f"Sole scheduler_owner={SCHEDULER_OWNER}."
            ),
            "scheduler_owner": SCHEDULER_OWNER,
        }
    if owner and owner not in {SCHEDULER_OWNER, "freeforge_local_dispatcher"}:
        return {
            "ok": False,
            "refused": True,
            "error": "unknown_scheduler_owner",
            "scheduler_owner": SCHEDULER_OWNER,
        }
    return {"ok": True, "refused": False, "scheduler_owner": SCHEDULER_OWNER}


def schedule_via_freeforge_only(request: dict[str, Any]) -> dict[str, Any]:
    gate = refuse_nodered_independent_trigger(request)
    if gate.get("refused"):
        return gate
    return {
        "ok": True,
        "action": "use_existing_schedule_cli",
        "hint": "python -m mainframe schedule add-report|fire — OpenClaw sole owner when present",
        "scheduler_owner": SCHEDULER_OWNER,
        "command_policy_owner": COMMAND_POLICY_OWNER,
        "note": "Visual bridge does not invent a second cron.",
    }


def remove_visual_leaves_workflows(root: Path | None = None) -> dict[str, Any]:
    """Demonstrate remotion: workflows remain under FreeForge state, not under visual package."""
    listed = list_workflows(root)
    return {
        "ok": True,
        "visual_package_required": False,
        "saved_workflows_remain": True,
        "workflow_count": len(listed),
        "workflows": listed,
        "scheduled_execution_owner": SCHEDULER_OWNER,
    }
