"""Acceptance: stdio MCP client + verified-memory server + paid refuse + loop register."""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Any

from mainframe.config import ROOT
from mainframe.mcp.loop import lookup_via_mcp, mcp_tools_for_agent, run_mcp_tool_in_loop
from mainframe.mcp.stdio_client import StdioMcpClient, call_local_server
from mainframe.memory.verified_patches import remember_verified
from mainframe.tools.invoke import invoke
from mainframe.tools.registry import reset_registry_for_tests


def run_mcp_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    reset_registry_for_tests()

    # 1) stdio client lists tools from verified-memory server
    listed = call_local_server(
        "mainframe.mcp.servers.verified_memory",
        tool="verified_patch_lookup",
        arguments={"goal": "mcp-accept-miss"},
    )
    tools = ((listed.get("tools_list") or {}).get("result") or {}).get("tools") or []
    names = [t.get("name") for t in tools if isinstance(t, dict)]
    checks.append(
        {
            "id": "stdio_tools_list",
            "ok": "verified_patch_lookup" in names and "verified_patch_remember" in names,
            "detail": {"names": names, "endpoint": listed.get("endpoint")},
        }
    )

    # 2) remember via direct API then lookup via MCP (zero model)
    goal = f"mcp-accept-goal-{uuid.uuid4().hex[:8]}"
    edits = [{"path": "x.py", "old": "a", "new": "b"}]
    rem = remember_verified(goal=goal, edits=edits, tests_ok=True)
    via = lookup_via_mcp(goal)
    checks.append(
        {
            "id": "verified_memory_via_stdio_mcp",
            "ok": bool(rem.get("ok") and via.get("hit") and via.get("edits")),
            "detail": {"remember": rem, "lookup": {k: via.get(k) for k in ("hit", "fingerprint", "via")}},
        }
    )

    # 3) register into agent registry; invoke through registry
    reg = mcp_tools_for_agent(register=True)
    checks.append(
        {
            "id": "register_mcp_in_agent_registry",
            "ok": bool(reg.get("ok") and "verified_patch_lookup" in (reg.get("tool_names") or [])),
            "detail": {"tool_names": reg.get("tool_names"), "refused": reg.get("refused_paid_or_remote")},
        }
    )

    call_id = f"call_{uuid.uuid4().hex[:10]}"
    inv = invoke(
        "local.mcp.verified_patch_lookup",
        {"goal": goal},
        call_id=call_id,
        root=ROOT,
    )
    checks.append(
        {
            "id": "invoke_mcp_tool_in_loop",
            "ok": bool(inv.get("ok")),
            "detail": {"tool": inv.get("tool"), "error": inv.get("error")},
        }
    )

    # 4) paid / remote MCP refused (not hidden)
    refused = reg.get("refused_paid_or_remote") or []
    checks.append(
        {
            "id": "refuse_paid_or_remote_mcp",
            "ok": len(refused) >= 1,
            "detail": refused,
        }
    )

    # 5) remote command string refused by client constructor
    remote_refused = False
    try:
        StdioMcpClient(["curl", "https://evil.example/mcp"])
    except ValueError as exc:
        remote_refused = "remote_or_network_command_refused" in str(exc)
    checks.append(
        {
            "id": "refuse_network_stdio_command",
            "ok": remote_refused,
            "detail": {"remote_refused": remote_refused},
        }
    )

    # 6) import-align smoke lives elsewhere; ensure module importable for loop
    from mainframe.codingloop.import_align import propose_import_align_edits

    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        (ws / "utils").mkdir()
        (ws / "utils" / "__init__.py").write_text("", encoding="utf-8")
        (ws / "utils" / "helpers.py").write_text(
            "def formatTitle(name: str) -> str:\n    return name\n",
            encoding="utf-8",
        )
        (ws / "app.py").write_text(
            "from utils.helpers import format_title\n",
            encoding="utf-8",
        )
        align = propose_import_align_edits(ws)
        checks.append(
            {
                "id": "import_align_camel_snake",
                "ok": bool(align.get("edits"))
                and any("format_title" in (e.get("new") or "") for e in align["edits"]),
                "detail": align,
            }
        )

    passed = sum(1 for c in checks if c.get("ok"))
    return {
        "ok": passed == len(checks),
        "passed": passed,
        "failed": len(checks) - passed,
        "checks": checks,
        "o7_gate": "stdio_mcp_live",
    }
