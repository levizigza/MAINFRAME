"""Optional MCP tool registration — fingerprint schemas; re-eval fees/permissions."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from mainframe.cost_gate import authorize
from mainframe.tools.types import ToolSpec


def fingerprint_schema(schema: dict[str, Any]) -> str:
    blob = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def evaluate_mcp_tool(
    *,
    name: str,
    purpose: str,
    input_schema: dict[str, Any],
    permission: str = "read",
    fee_token_price_usd: float | None = None,
    endpoint: str | None = None,
    prior_fingerprint: str | None = None,
) -> dict[str, Any]:
    """
    Build/refresh an MCP-backed ToolSpec through the same registry rules.

    Changed fingerprints trigger re-evaluation of fees and permissions.
    """
    fp = fingerprint_schema(input_schema)
    changed = prior_fingerprint is not None and prior_fingerprint != fp

    stdio_local = bool(endpoint is None or str(endpoint).startswith("stdio:"))
    tool_target = f"local.mcp.{name}" if stdio_local else f"mcp.{name}"

    # Fee / permission gate — external MCP never auto-allowed if paid signals present
    gate = authorize(
        "tool",
        tool_target,
        local=stdio_local,
        token_price_usd=fee_token_price_usd,
        endpoint=endpoint if endpoint and not str(endpoint).startswith("stdio:") else None,
    )

    available = gate.allowed
    reason = None if available else (gate.denied_code or gate.reason)
    if fee_token_price_usd is not None and fee_token_price_usd == 0 and not gate.allowed:
        reason = reason or "fee_or_permission_changed"

    spec = ToolSpec(
        name=tool_target,
        purpose=purpose,
        input_schema=input_schema,
        permission=permission,  # type: ignore[arg-type]
        timeout_s=30.0,
        task_tags=["mcp", "external"] if not stdio_local else ["mcp", "local"],
        side_effects=permission in {"write", "exec_test"},
        capability_id=tool_target,
        source="mcp",
        schema_fingerprint=fp,
        fee_risk=fee_token_price_usd is not None
        or (endpoint is not None and not str(endpoint).startswith("stdio:")),
        available=available,
        unavailable_reason=reason,
    )
    return {
        "ok": True,
        "spec": spec,
        "schema_fingerprint": fp,
        "fingerprint_changed": changed,
        "reevaluated": changed or prior_fingerprint is None,
        "gate": gate.to_dict(),
        "available": available,
    }
