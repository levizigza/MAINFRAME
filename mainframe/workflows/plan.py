"""Dry-run execution plan — no side effects."""

from __future__ import annotations

from typing import Any

from mainframe.workflows.schema import normalize_workflow
from mainframe.workflows.validate import validate_workflow


def topological_order(wf: dict[str, Any]) -> list[str]:
    smap = {s["id"]: s for s in wf.get("steps") or []}
    indeg = {sid: 0 for sid in smap}
    # Edge dep → step (dep must run first)
    children: dict[str, list[str]] = {sid: [] for sid in smap}
    for sid, step in smap.items():
        for dep in step.get("depends_on") or []:
            if dep in smap:
                children[dep].append(sid)
                indeg[sid] += 1
    ready = sorted([s for s, d in indeg.items() if d == 0])
    order: list[str] = []
    while ready:
        n = ready.pop(0)
        order.append(n)
        for c in sorted(children[n]):
            indeg[c] -= 1
            if indeg[c] == 0:
                ready.append(c)
                ready.sort()
    return order


def dry_run_plan(
    raw: dict[str, Any],
    *,
    inputs: dict[str, Any] | None = None,
    available_capabilities: set[str] | None = None,
    strict_capabilities: bool = True,
) -> dict[str, Any]:
    """Produce an ordered plan without executing steps."""
    validation = validate_workflow(
        raw,
        available_capabilities=available_capabilities,
        strict_capabilities=strict_capabilities,
    )
    if not validation.get("ok"):
        return {
            "ok": False,
            "blocked": True,
            "reason": "validation_failed",
            "validation": validation,
            "plan": [],
        }
    wf = validation["normalized"]
    order = topological_order(wf)
    smap = {s["id"]: s for s in wf["steps"]}
    plan = []
    for sid in order:
        step = smap[sid]
        plan.append(
            {
                "step_id": sid,
                "kind": step.get("kind"),
                "depends_on": list(step.get("depends_on") or []),
                "permissions": list(step.get("permissions") or []),
                "effects": list(step.get("effects") or []),
                "timeout_ms": step.get("timeout_ms"),
                "retries": step.get("retries"),
                "condition": step.get("condition"),
                "loop": step.get("loop"),
                "artifact_refs": list(step.get("artifact_refs") or []),
                "would_execute": True,
            }
        )
    return {
        "ok": True,
        "blocked": False,
        "workflow_id": wf.get("id"),
        "format_version": wf.get("format_version"),
        "inputs_preview": inputs or {},
        "plan": plan,
        "step_order": order,
        "ownership_note": (
            "FreeForge owns workflow semantics + receipts; "
            "OpenClaw remains owner of Gateway scheduling/session management."
        ),
    }
