"""Graph validation before execution."""

from __future__ import annotations

from typing import Any

from mainframe.workflows.schema import (
    AI_STEP_TYPES,
    FORMAT_VERSION,
    KNOWN_CAPABILITIES,
    STEP_KINDS,
    normalize_workflow,
)
from mainframe.workflows.typesafe import type_compatible


def _step_map(wf: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {s["id"]: s for s in wf.get("steps") or [] if s.get("id")}


def validate_workflow(
    raw: dict[str, Any],
    *,
    available_capabilities: set[str] | None = None,
    strict_capabilities: bool = True,
) -> dict[str, Any]:
    """
    Reject invalid references, unbounded cycles, incompatible schemas,
    unavailable capabilities, and undeclared effects.

    When strict_capabilities is False, unavailable capabilities are warnings so
    the runner can execute predecessors then block precisely at the gated step.
    """
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    wf = normalize_workflow(raw)
    # Default: all known caps available (offline deterministic + human). Callers
    # omit ai.infer to simulate unavailable AI.
    if available_capabilities is None:
        available = set(KNOWN_CAPABILITIES)
    else:
        available = set(available_capabilities)

    if wf.get("format_version") != FORMAT_VERSION:
        errors.append(
            {
                "code": "unsupported_format_version",
                "detail": wf.get("format_version"),
                "expected": FORMAT_VERSION,
            }
        )

    steps = wf.get("steps") or []
    ids = [s.get("id") for s in steps]
    if len(ids) != len(set(ids)):
        errors.append({"code": "duplicate_step_id", "detail": ids})

    smap = _step_map(wf)
    artifact_ids = {a.get("id") for a in (wf.get("artifacts") or []) if a.get("id")}

    # --- Invalid references ---
    for step in steps:
        sid = step.get("id")
        kind = step.get("kind")
        if kind not in STEP_KINDS:
            errors.append({"code": "invalid_step_kind", "step": sid, "kind": kind})

        for dep in step.get("depends_on") or []:
            if dep not in smap:
                errors.append({"code": "invalid_dependency_ref", "step": sid, "ref": dep})

        for art in step.get("artifact_refs") or []:
            if art not in artifact_ids:
                errors.append({"code": "invalid_artifact_ref", "step": sid, "ref": art})

        loop = step.get("loop")
        if loop is not None:
            if not isinstance(loop, dict):
                errors.append({"code": "invalid_loop", "step": sid})
            else:
                max_iter = loop.get("max_iterations")
                if max_iter is None or not isinstance(max_iter, int) or max_iter < 1:
                    errors.append(
                        {
                            "code": "unbounded_loop",
                            "step": sid,
                            "detail": "loop requires positive max_iterations",
                        }
                    )
                if max_iter is not None and isinstance(max_iter, int) and max_iter > 10_000:
                    errors.append(
                        {
                            "code": "unbounded_loop",
                            "step": sid,
                            "detail": f"max_iterations {max_iter} exceeds hard cap 10000",
                        }
                    )

        # Undeclared effects: side_effects flag / list must be declared when mutating
        effects = list(step.get("effects") or [])
        if step.get("mutates") and not effects:
            errors.append({"code": "undeclared_effects", "step": sid})
        for eff in effects:
            if not isinstance(eff, str) or not eff.strip():
                errors.append({"code": "invalid_effect", "step": sid, "effect": eff})

        # Permissions / capabilities
        for perm in step.get("permissions") or []:
            if perm not in KNOWN_CAPABILITIES:
                errors.append({"code": "unknown_capability", "step": sid, "capability": perm})
            elif perm not in available:
                item = {
                    "code": "unavailable_capability",
                    "step": sid,
                    "capability": perm,
                }
                if strict_capabilities:
                    errors.append(item)
                else:
                    warnings.append(item)

        if kind == "ai" and "ai.infer" not in (step.get("permissions") or []):
            # AI steps must declare ai.infer
            errors.append({"code": "undeclared_ai_permission", "step": sid})
        elif kind == "ai" and "ai.infer" not in available:
            item = {
                "code": "unavailable_capability",
                "step": sid,
                "capability": "ai.infer",
            }
            # Only add if not already flagged via permissions loop
            already = any(
                e.get("code") == "unavailable_capability"
                and e.get("step") == sid
                and e.get("capability") == "ai.infer"
                for e in errors + warnings
            )
            if not already:
                if strict_capabilities:
                    errors.append(item)
                else:
                    warnings.append(item)
        if kind == "ai":
            ai_type = step.get("ai_type")
            if ai_type and ai_type not in AI_STEP_TYPES:
                errors.append({"code": "invalid_ai_type", "step": sid, "ai_type": ai_type})
        if kind == "human" and "human.decide" not in (step.get("permissions") or ["human.decide"]):
            warnings.append({"code": "human_permission_implied", "step": sid})

        retries = step.get("retries") or {}
        if int(retries.get("max") or 0) < 0:
            errors.append({"code": "invalid_retries", "step": sid})
        if int(step.get("timeout_ms") or 0) <= 0:
            errors.append({"code": "invalid_timeout", "step": sid})

    # --- Cycles: only reject if any cycle lacks a bounded loop on the cycle ---
    cycle = _find_cycle(smap)
    if cycle:
        # A cycle is OK only if every node on the cycle has a bounded loop OR it's not a
        # depends_on cycle that could run forever — depends_on cycles are always invalid.
        errors.append({"code": "unbounded_cycle", "cycle": cycle})

    # --- Schema compatibility along edges (merge all dependency outputs) ---
    for step in steps:
        sid = step["id"]
        deps = [d for d in (step.get("depends_on") or []) if d in smap]
        if not deps:
            continue
        merged_props: dict[str, Any] = {}
        for dep in deps:
            props = (smap[dep].get("outputs") or {}).get("properties") or {}
            merged_props.update(props)
        merged = {
            "type": "object",
            "properties": merged_props,
            "additionalProperties": True,
        }
        ok, reason = type_compatible(merged, step.get("inputs"))
        if not ok:
            errors.append(
                {
                    "code": "incompatible_schema",
                    "from": deps,
                    "to": sid,
                    "reason": reason,
                }
            )

    # Workflow-level permissions must cover step permissions
    wf_perms = set(wf.get("permissions") or [])
    for step in steps:
        for perm in step.get("permissions") or []:
            if wf_perms and perm not in wf_perms:
                errors.append(
                    {
                        "code": "permission_not_granted_at_workflow",
                        "step": step["id"],
                        "capability": perm,
                    }
                )

    return {
        "ok": len(errors) == 0,
        "format_version": wf.get("format_version"),
        "workflow_id": wf.get("id"),
        "errors": errors,
        "warnings": warnings,
        "step_count": len(steps),
        "normalized": wf,
    }


def _find_cycle(smap: dict[str, dict[str, Any]]) -> list[str] | None:
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def dfs(node: str) -> list[str] | None:
        visiting.add(node)
        stack.append(node)
        for dep in smap[node].get("depends_on") or []:
            if dep not in smap:
                continue
            # Edge direction: step depends_on dep means dep → step for topo,
            # but cycle detection walks depends_on as edges from step to dep.
            if dep in visiting:
                i = stack.index(dep)
                return stack[i:] + [dep]
            if dep not in visited:
                found = dfs(dep)
                if found:
                    return found
        visiting.discard(node)
        stack.pop()
        visited.add(node)
        return None

    for n in smap:
        if n not in visited:
            c = dfs(n)
            if c:
                return c
    return None
