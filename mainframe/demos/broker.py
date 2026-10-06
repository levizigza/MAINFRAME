"""
Shared tool broker — same tools mock inference and real models will use.

All filesystem changes go through these tools so verification is real.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from mainframe.cost_gate import authorize, scrub_env_for_child


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ToolResult:
    ok: bool
    tool: str
    detail: dict[str, Any]
    cancelled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Broker:
    """Workspace-scoped tool broker with cancel support and audit log."""

    workspace: Path
    cancelled: bool = False
    log: list[dict[str, Any]] = field(default_factory=list)

    def cancel(self) -> None:
        self.cancelled = True

    def _record(self, tool: str, result: ToolResult) -> ToolResult:
        self.log.append({"at": _utc(), "tool": tool, "result": result.to_dict()})
        return result

    def _gate(self, target: str) -> ToolResult | None:
        decision = authorize("tool", target, local=True)
        if not decision.allowed:
            return ToolResult(False, target, {"cost_gate": decision.to_dict()})
        if self.cancelled:
            return ToolResult(False, target, {"reason": "cancelled"}, cancelled=True)
        return None

    def read_file(self, rel: str) -> ToolResult:
        blocked = self._gate("local.read_file")
        if blocked:
            return self._record("read_file", blocked)
        path = (self.workspace / rel).resolve()
        if not str(path).startswith(str(self.workspace.resolve())):
            return self._record("read_file", ToolResult(False, "read_file", {"error": "path_escape"}))
        if not path.is_file():
            return self._record("read_file", ToolResult(False, "read_file", {"error": "not_found", "path": rel}))
        text = path.read_text(encoding="utf-8")
        return self._record(
            "read_file",
            ToolResult(
                True,
                "read_file",
                {"path": rel, "content": text, "sha256": hashlib.sha256(text.encode()).hexdigest()},
            ),
        )

    def write_file(self, rel: str, content: str) -> ToolResult:
        blocked = self._gate("local.write_file")
        if blocked:
            return self._record("write_file", blocked)
        path = (self.workspace / rel).resolve()
        if not str(path).startswith(str(self.workspace.resolve())):
            return self._record("write_file", ToolResult(False, "write_file", {"error": "path_escape"}))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return self._record(
            "write_file",
            ToolResult(
                True,
                "write_file",
                {"path": rel, "bytes": len(content.encode("utf-8")), "sha256": hashlib.sha256(content.encode()).hexdigest()},
            ),
        )

    def list_tree(self, rel: str = ".") -> ToolResult:
        blocked = self._gate("local.list_tree")
        if blocked:
            return self._record("list_tree", blocked)
        root = (self.workspace / rel).resolve()
        files: list[str] = []
        for p in sorted(root.rglob("*")):
            if p.is_file():
                files.append(str(p.relative_to(self.workspace)).replace("\\", "/"))
        return self._record("list_tree", ToolResult(True, "list_tree", {"files": files, "count": len(files)}))

    def run_tests(self, rel_test: str = "test_app.py") -> ToolResult:
        blocked = self._gate("local.run_tests")
        if blocked:
            return self._record("run_tests", blocked)
        path = self.workspace / rel_test
        if not path.is_file():
            return self._record("run_tests", ToolResult(False, "run_tests", {"error": "missing_test"}))
        proc = subprocess.run(
            [sys.executable, str(path)],
            cwd=str(self.workspace),
            capture_output=True,
            text=True,
            env=scrub_env_for_child(),
            timeout=60,
        )
        return self._record(
            "run_tests",
            ToolResult(
                proc.returncode == 0,
                "run_tests",
                {
                    "exit_code": proc.returncode,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "passed": proc.returncode == 0,
                },
            ),
        )

    def apply_patch(self, rel: str, old: str, new: str) -> ToolResult:
        """Deterministic search-replace patch tool (used by mock and real models)."""
        blocked = self._gate("local.apply_patch")
        if blocked:
            return self._record("apply_patch", blocked)
        read = self.read_file(rel)
        if not read.ok:
            return self._record("apply_patch", ToolResult(False, "apply_patch", {"error": "read_failed", "read": read.detail}))
        content = str(read.detail.get("content", ""))
        if old not in content:
            return self._record(
                "apply_patch",
                ToolResult(False, "apply_patch", {"error": "old_not_found", "path": rel}),
            )
        updated = content.replace(old, new, 1)
        return self.write_file(rel, updated)


ToolFn = Callable[..., ToolResult]
