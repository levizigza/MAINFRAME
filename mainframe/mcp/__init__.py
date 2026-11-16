"""Local stdio MCP — fee-gated; verified-patch memory server first."""

from __future__ import annotations

from mainframe.mcp.accept import run_mcp_accept
from mainframe.mcp.loop import mcp_tools_for_agent, run_mcp_tool_in_loop
from mainframe.mcp.stdio_client import StdioMcpClient, call_local_server

__all__ = [
    "StdioMcpClient",
    "call_local_server",
    "mcp_tools_for_agent",
    "run_mcp_accept",
    "run_mcp_tool_in_loop",
]
