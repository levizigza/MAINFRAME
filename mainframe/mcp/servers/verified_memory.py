"""Stdio MCP server: verified-patch memory lookup / remember (local only)."""

from __future__ import annotations

import json
import sys
from typing import Any

from mainframe.memory.verified_patches import lookup_verified, remember_verified

TOOLS = [
    {
        "name": "verified_patch_lookup",
        "description": "Lookup a previously verified patch by goal fingerprint (local SQLite/files).",
        "inputSchema": {
            "type": "object",
            "properties": {"goal": {"type": "string"}},
            "required": ["goal"],
        },
    },
    {
        "name": "verified_patch_remember",
        "description": "Store edits that already passed tests for later zero-model replay.",
        "inputSchema": {
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


def _result_text(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(payload)}],
        "isError": not bool(payload.get("ok", True)),
    }


def handle_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "verified_patch_lookup":
        out = lookup_verified(goal=str(arguments.get("goal") or ""))
        return _result_text(out)
    if name == "verified_patch_remember":
        out = remember_verified(
            goal=str(arguments.get("goal") or ""),
            edits=list(arguments.get("edits") or []),
            tests_ok=bool(arguments.get("tests_ok", True)),
        )
        return _result_text(out)
    return _result_text({"ok": False, "error": f"unknown_tool:{name}"})


def _reply(msg: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def serve_stdio() -> None:
    """Newline-delimited JSON-RPC loop on stdin/stdout."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = req.get("method")
        rid = req.get("id")
        params = req.get("params") or {}

        if method == "initialize":
            _reply(
                {
                    "jsonrpc": "2.0",
                    "id": rid,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {
                            "name": "mainframe-verified-patch-memory",
                            "version": "0.1.56",
                        },
                    },
                }
            )
            continue
        if method == "notifications/initialized":
            continue
        if method == "tools/list":
            _reply({"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}})
            continue
        if method == "tools/call":
            name = str(params.get("name") or "")
            args = params.get("arguments") or {}
            if not isinstance(args, dict):
                args = {}
            result = handle_tool(name, args)
            _reply({"jsonrpc": "2.0", "id": rid, "result": result})
            continue
        if rid is not None:
            _reply(
                {
                    "jsonrpc": "2.0",
                    "id": rid,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }
            )


if __name__ == "__main__":
    serve_stdio()
