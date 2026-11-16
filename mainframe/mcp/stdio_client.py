"""Minimal MCP-style JSON-RPC client over stdio (local processes only).

Not a full MCP SDK. Speaks initialize + tools/list + tools/call with a
newline-delimited JSON child process. Remote/network endpoints are refused.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


class StdioMcpClient:
    def __init__(
        self,
        command: list[str],
        *,
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
        timeout_s: float = 30.0,
    ) -> None:
        if not command:
            raise ValueError("command required")
        # Refuse obvious remote shells / network helpers as "MCP servers"
        joined = " ".join(command).lower()
        for bad in ("curl ", "wget ", "ssh ", "http://", "https://"):
            if bad in joined:
                raise ValueError(f"remote_or_network_command_refused:{bad.strip()}")
        self.command = list(command)
        self.cwd = str(cwd) if cwd else None
        self.env = env
        self.timeout_s = timeout_s
        self._proc: subprocess.Popen[str] | None = None
        self._next_id = 1

    def start(self) -> dict[str, Any]:
        self._proc = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=self.cwd,
            env=self.env,
            bufsize=1,
        )
        init = self.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "mainframe-mcp", "version": "0.1.56"},
            },
        )
        # notifications/initialized (no response expected)
        self.notify("notifications/initialized", {})
        return init

    def close(self) -> None:
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except OSError:
                pass
        self._proc = None

    def __enter__(self) -> "StdioMcpClient":
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _send(self, obj: dict[str, Any]) -> None:
        if not self._proc or not self._proc.stdin:
            raise RuntimeError("client_not_started")
        self._proc.stdin.write(json.dumps(obj) + "\n")
        self._proc.stdin.flush()

    def _recv(self) -> dict[str, Any]:
        if not self._proc or not self._proc.stdout:
            raise RuntimeError("client_not_started")
        line = self._proc.stdout.readline()
        if not line:
            err = ""
            if self._proc.stderr:
                err = self._proc.stderr.read() or ""
            raise RuntimeError(f"mcp_server_closed:{err[:400]}")
        return json.loads(line)

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self._send(msg)

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        rid = self._next_id
        self._next_id += 1
        msg: dict[str, Any] = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            msg["params"] = params
        self._send(msg)
        # Read until matching id (ignore stray notifications)
        while True:
            resp = self._recv()
            if resp.get("id") == rid:
                if "error" in resp:
                    return {"ok": False, "error": resp["error"], "result": None}
                return {"ok": True, "result": resp.get("result"), "error": None}

    def list_tools(self) -> dict[str, Any]:
        return self.request("tools/list", {})

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request(
            "tools/call",
            {"name": name, "arguments": arguments or {}},
        )


def call_local_server(
    server_module: str,
    *,
    tool: str,
    arguments: dict[str, Any] | None = None,
    timeout_s: float = 30.0,
) -> dict[str, Any]:
    """Spawn ``python -m <server_module>`` and call one tool (stdio only)."""
    cmd = [sys.executable, "-m", server_module]
    client = StdioMcpClient(cmd, timeout_s=timeout_s)
    try:
        client.start()
        listed = client.list_tools()
        called = client.call_tool(tool, arguments)
        return {
            "ok": bool(called.get("ok")),
            "tools_list": listed,
            "call": called,
            "endpoint": f"stdio:{server_module}",
            "remote": False,
        }
    finally:
        client.close()
