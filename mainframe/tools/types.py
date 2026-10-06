"""Tool registry types — narrow purpose, permissions, structured results."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Literal

PermissionScope = Literal[
    "read",
    "write",
    "exec_test",
    "network_denied",
]

ErrorCode = Literal[
    "unknown_tool",
    "invalid_input",
    "incomplete_streaming_args",
    "duplicate_operation_id",
    "malformed_json",
    "stale_file",
    "capability_unavailable",
    "timeout",
    "permission_denied",
    "fee_or_permission_changed",
]


@dataclass
class ToolSpec:
    name: str
    purpose: str
    input_schema: dict[str, Any]
    permission: PermissionScope
    timeout_s: float
    task_tags: list[str] = field(default_factory=list)  # when to expose
    side_effects: bool = False
    capability_id: str = ""
    source: str = "builtin"  # builtin | mcp
    schema_fingerprint: str | None = None
    fee_risk: bool = False
    available: bool = True
    unavailable_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


ToolHandler = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]
# handler(args, context) -> structured result body


@dataclass
class ToolResult:
    ok: bool
    tool: str
    call_id: str
    result: dict[str, Any] | None = None
    error_code: str | None = None
    error: str | None = None
    corrected_args: dict[str, Any] | None = None
    side_effects: bool = False
    duration_ms: int = 0
    audit: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
