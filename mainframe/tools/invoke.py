"""Invoke tools through the registry — validate first; no side effects on errors."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from mainframe.cost_gate import authorize
from mainframe.tools.audit import CallAudit
from mainframe.tools.registry import get_tool, list_tools
from mainframe.tools.types import ToolResult
from mainframe.tools.validate import parse_arguments, validate_and_correct

# Process-wide audit for duplicate operation IDs within a session
_AUDIT = CallAudit()


def get_audit() -> CallAudit:
    return _AUDIT


def reset_audit() -> None:
    global _AUDIT
    _AUDIT = CallAudit()


def invoke(
    tool_name: str,
    arguments: Any,
    *,
    call_id: str,
    root: Path,
    allow_correction: bool = True,
    project_id: str | None = None,
    require_project: bool = False,
) -> dict[str, Any]:
    """
    Dispatch a tool call.

    Preserves ``call_id``. Rejects unknown tools, invented params, duplicates,
    malformed JSON, incomplete streaming args — **without** invoking handlers
    (no side effects).

    When ``require_project`` is True or ``project_id`` is set, the call is bound
    to an explicit project identity (cross-project isolation).
    """
    if require_project or project_id is not None:
        from mainframe.projects.bind import bind_tool_run

        bound = bind_tool_run(
            project_id=project_id,
            tool_name=tool_name,
            arguments=arguments if isinstance(arguments, dict) else None,
        )
        if not bound.get("ok"):
            return ToolResult(
                ok=False,
                tool=tool_name,
                call_id=call_id,
                error_code="permission_denied",
                error=bound.get("error") or "project binding refused",
                audit={"project_binding": bound, "side_effects_executed": False},
            ).to_dict()

    gate = authorize("tool", "local.tool_registry_invoke", local=True)
    if not gate.allowed:
        return ToolResult(
            ok=False,
            tool=tool_name,
            call_id=call_id,
            error_code="permission_denied",
            error="cost gate denied",
            audit={"cost_gate": gate.to_dict()},
        ).to_dict()

    started = time.time()

    def _fail(code: str, msg: str, **extra: Any) -> dict[str, Any]:
        res = ToolResult(
            ok=False,
            tool=tool_name,
            call_id=call_id,
            error_code=code,
            error=msg,
            side_effects=False,
            duration_ms=int((time.time() - started) * 1000),
            audit={"side_effects_executed": False, **extra},
        )
        _AUDIT.record(res.to_dict())
        return res.to_dict()

    # Duplicate operation ID — no side effects
    if not call_id:
        return _fail("invalid_input", "call_id required")
    if _AUDIT.check_duplicate(call_id):
        return _fail(
            "duplicate_operation_id",
            f"duplicate call_id {call_id!r}; refusing to re-execute",
        )

    # Unknown tool
    entry = get_tool(tool_name)
    if entry is None:
        return _fail("unknown_tool", f"unknown tool: {tool_name!r}")

    spec, handler = entry
    if not spec.available:
        return _fail(
            "capability_unavailable",
            spec.unavailable_reason or "tool unavailable",
            fee_risk=spec.fee_risk,
        )

    # Parse arguments (malformed / incomplete → no handler)
    parsed = parse_arguments(arguments)
    if not parsed.get("ok"):
        return _fail(parsed.get("error_code") or "invalid_input", parsed.get("error") or "bad args")

    args = parsed["args"]
    validated = validate_and_correct(
        args, spec.input_schema, allow_one_correction=allow_correction
    )
    if not validated.get("ok"):
        return _fail(
            validated.get("error_code") or "invalid_input",
            validated.get("error") or "invalid inputs",
            details=validated.get("details"),
            corrections_attempted=validated.get("corrections_attempted"),
        )

    final_args = validated["args"]
    # Permission via cost gate for write/exec
    if spec.permission in {"write", "exec_test"}:
        pg = authorize("tool", spec.capability_id or f"local.tool_{spec.name}", local=True)
        if not pg.allowed:
            return _fail("permission_denied", pg.reason or "denied", cost_gate=pg.to_dict())

    # Mark ID only when we are about to execute (so failed validation can retry same id? 
    # Spec says preserve IDs and reject duplicates — typically ID reserved on attempt.
    # For acceptance: duplicate after successful OR after any recorded attempt.
    # We'll remember after validation passes so malformed retries with new parse can use same id
    # Actually acceptance: "duplicate operation IDs ... cause no side effects" — second call
    # with same ID should not run. Remember at start of successful validate path.
    _AUDIT.remember_id(call_id)

    ctx = {"root": str(root.resolve()), "timeout_s": spec.timeout_s, "call_id": call_id}
    try:
        body = handler(final_args, ctx)
    except Exception as exc:  # noqa: BLE001
        return _fail("invalid_input", f"{type(exc).__name__}: {exc}")

    # Handler-level structured errors
    if isinstance(body, dict) and body.get("_error_code"):
        code = body["_error_code"]
        res = ToolResult(
            ok=False,
            tool=tool_name,
            call_id=call_id,
            error_code=code,
            error=body.get("error"),
            result={k: v for k, v in body.items() if k not in {"_error_code", "error"}},
            side_effects=False,
            duration_ms=int((time.time() - started) * 1000),
            corrected_args=final_args if validated.get("corrected") else None,
            audit={
                "side_effects_executed": False,
                "schema_fingerprint": spec.schema_fingerprint,
            },
        )
        _AUDIT.record(res.to_dict())
        return res.to_dict()

    res = ToolResult(
        ok=True,
        tool=tool_name,
        call_id=call_id,
        result=body,
        side_effects=bool(spec.side_effects),
        duration_ms=int((time.time() - started) * 1000),
        corrected_args=final_args if validated.get("corrected") else None,
        audit={
            "side_effects_executed": bool(spec.side_effects),
            "corrections": validated.get("corrections") or [],
            "permission": spec.permission,
            "purpose": spec.purpose,
            "schema_fingerprint": spec.schema_fingerprint,
            "source": spec.source,
        },
    )
    _AUDIT.record(res.to_dict())
    return res.to_dict()


def expose_for_task(task_kind: str) -> dict[str, Any]:
    return {
        "ok": True,
        "task_kind": task_kind,
        "tools": list_tools(task_kind=task_kind),
    }
