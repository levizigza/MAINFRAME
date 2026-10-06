"""Expose only necessary read operations through the tool registry."""

from __future__ import annotations

from typing import Any

from mainframe.connectors.catalog import all_connector_specs
from mainframe.connectors.runtime import call_operation
from mainframe.tools.types import ToolHandler, ToolSpec


def _handler(connector_id: str, op_id: str) -> ToolHandler:
    def _run(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        mode = str(ctx.get("connector_mode") or args.pop("_mode", None) or "fixture")
        scenario = str(ctx.get("fixture_scenario") or args.pop("_fixture", None) or "ok")
        # Strip internal keys if present
        clean = {k: v for k, v in args.items() if not str(k).startswith("_")}
        out = call_operation(
            connector_id,
            op_id,
            clean,
            mode=mode,
            fixture_scenario=scenario,
        )
        if not out.get("ok"):
            err = out.get("error") or {}
            return {
                "_error_code": err.get("code") or "connector_error",
                "error": err.get("message") or "connector failed",
                "detail": out,
            }
        return {
            "data": out.get("data"),
            "provenance": out.get("provenance"),
            "connector_id": connector_id,
            "op_id": op_id,
            "capability": "read",
        }

    return _run


def connector_tool_specs() -> list[tuple[ToolSpec, ToolHandler]]:
    """Read-only tool specs only — write ops are never registered."""
    out: list[tuple[ToolSpec, ToolHandler]] = []
    for spec in all_connector_specs():
        for op in spec.operations:
            if not op.expose_as_tool:
                continue
            if op.capability != "read":
                continue
            name = f"conn_{spec.connector_id}_{op.op_id}"
            out.append(
                (
                    ToolSpec(
                        name=name,
                        purpose=op.purpose,
                        input_schema=op.input_schema,
                        permission="read",
                        timeout_s=30.0,
                        task_tags=["automation", "explanation", "feature"],
                        side_effects=False,
                        capability_id=f"connector.{spec.connector_id}.read",
                        source="connector",
                        fee_risk=False,
                        available=True,
                    ),
                    _handler(spec.connector_id, op.op_id),
                )
            )
    return out


def register_connector_tools(register_fn: Any) -> list[str]:
    names: list[str] = []
    for spec, handler in connector_tool_specs():
        register_fn(spec, handler)
        names.append(spec.name)
    return names
