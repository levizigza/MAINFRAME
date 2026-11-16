"""Register local MCP tools into the agent tool registry and invoke via stdio."""

from __future__ import annotations

from typing import Any

from mainframe.mcp.stdio_client import call_local_server
from mainframe.tools.mcp_bridge import evaluate_mcp_tool
from mainframe.tools.registry import list_tools, register_mcp_tool


VERIFIED_MEMORY_MODULE = "mainframe.mcp.servers.verified_memory"

# Names exposed to the agent (short); registry uses local.mcp.* capability ids.
AGENT_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "verified_patch_lookup",
        "purpose": "Lookup verified patch memory via local stdio MCP",
        "permission": "read",
        "input_schema": {
            "type": "object",
            "properties": {"goal": {"type": "string"}},
            "required": ["goal"],
        },
    },
    {
        "name": "verified_patch_remember",
        "purpose": "Remember a test-verified patch via local stdio MCP",
        "permission": "write",
        "input_schema": {
            "type": "object",
            "properties": {
                "goal": {"type": "string"},
                "edits": {"type": "array"},
                "tests_ok": {"type": "boolean"},
            },
            "required": ["goal", "edits"],
        },
    },
]


def mcp_tools_for_agent(*, register: bool = True) -> dict[str, Any]:
    """
    Evaluate + optionally register local verified-memory MCP tools.

    Fee-bearing / non-stdio endpoints stay unavailable (not hidden).
    """
    registered: list[dict[str, Any]] = []
    refused: list[dict[str, Any]] = []

    # Prove remote/paid refusal path
    paid = evaluate_mcp_tool(
        name="paid_remote_demo",
        purpose="must refuse",
        input_schema={"type": "object", "properties": {}},
        fee_token_price_usd=0.01,
        endpoint="https://example.com/mcp",
    )
    if not paid.get("available"):
        refused.append(
            {
                "name": "paid_remote_demo",
                "reason": (paid.get("spec").unavailable_reason if paid.get("spec") else None)
                or paid.get("gate", {}).get("reason"),
                "endpoint": "https://example.com/mcp",
            }
        )

    for spec in AGENT_TOOL_SPECS:
        ev = evaluate_mcp_tool(
            name=spec["name"],
            purpose=spec["purpose"],
            input_schema=spec["input_schema"],
            permission=spec["permission"],
            endpoint=f"stdio:{VERIFIED_MEMORY_MODULE}",
        )
        if register and ev.get("available"):
            # Handler closes over tool name for stdio call
            tool_name = spec["name"]

            def _make_handler(tn: str):
                def _handler(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
                    _ = ctx
                    out = call_local_server(
                        VERIFIED_MEMORY_MODULE,
                        tool=tn,
                        arguments=args if isinstance(args, dict) else {},
                    )
                    call = out.get("call") or {}
                    result = call.get("result")
                    return {
                        "mcp": True,
                        "endpoint": out.get("endpoint"),
                        "ok": out.get("ok"),
                        "result": result,
                        "error": call.get("error"),
                    }

                return _handler

            reg = register_mcp_tool(ev, handler=_make_handler(tool_name))
            registered.append(
                {
                    "name": tool_name,
                    "registry_name": ev["spec"].name,
                    "available": True,
                    "register": reg,
                }
            )
        else:
            registered.append(
                {
                    "name": spec["name"],
                    "available": bool(ev.get("available")),
                    "reason": getattr(ev.get("spec"), "unavailable_reason", None),
                }
            )

    names = [r["name"] for r in registered if r.get("available")]
    return {
        "ok": True,
        "tool_names": names,
        "registered": registered,
        "refused_paid_or_remote": refused,
        "registry_size": len(list_tools(include_unavailable=True)),
        "stdio_only_default": True,
    }


def run_mcp_tool_in_loop(
    tool_name: str,
    arguments: dict[str, Any],
    *,
    ensure_registered: bool = True,
    root: Any = None,
) -> dict[str, Any]:
    """Invoke a local MCP tool through the registry (agent-loop path)."""
    import uuid
    from pathlib import Path

    from mainframe.config import ROOT
    from mainframe.tools.invoke import invoke

    if ensure_registered:
        mcp_tools_for_agent(register=True)
    full = tool_name if tool_name.startswith("local.mcp.") else f"local.mcp.{tool_name}"
    call_id = f"call_{uuid.uuid4().hex[:10]}"
    workspace = Path(root) if root is not None else ROOT
    return invoke(full, arguments, call_id=call_id, root=workspace)


def lookup_via_mcp(goal: str) -> dict[str, Any]:
    """Agent-loop helper: verified patch lookup over stdio MCP."""
    out = call_local_server(
        VERIFIED_MEMORY_MODULE,
        tool="verified_patch_lookup",
        arguments={"goal": goal},
    )
    call = out.get("call") or {}
    result = call.get("result") or {}
    # Unwrap text content
    text = ""
    if isinstance(result, dict):
        for block in result.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "text":
                text = str(block.get("text") or "")
                break
    payload: dict[str, Any] = {}
    if text:
        try:
            payload = json_loads(text)
        except Exception:  # noqa: BLE001
            payload = {"raw": text}
    return {
        "ok": bool(out.get("ok")),
        "via": "stdio_mcp",
        "endpoint": out.get("endpoint"),
        "hit": bool(payload.get("hit")),
        "edits": list(payload.get("edits") or []),
        "fingerprint": payload.get("fingerprint"),
        "payload": payload,
    }


def json_loads(s: str) -> dict[str, Any]:
    import json

    data = json.loads(s)
    return data if isinstance(data, dict) else {"value": data}
