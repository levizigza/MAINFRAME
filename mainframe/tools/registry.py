"""Typed tool registry — builtins + optional MCP; task-relevant exposure."""

from __future__ import annotations

from typing import Any

from mainframe.tools import impl
from mainframe.tools.types import ToolHandler, ToolSpec

_REGISTRY: dict[str, tuple[ToolSpec, ToolHandler]] = {}
_MCP_FINGERPRINTS: dict[str, str] = {}


def _register(spec: ToolSpec, handler: ToolHandler) -> None:
    _REGISTRY[spec.name] = (spec, handler)


def _ensure_builtins() -> None:
    if _REGISTRY:
        return
    _register(
        ToolSpec(
            name="search",
            purpose="Lexical/exact issue→code search; returns ranked path ranges",
            input_schema={
                "type": "object",
                "required": ["query"],
                "additionalProperties": False,
                "properties": {
                    "query": {"type": "string"},
                    "goal": {"type": "string"},
                    "top_k": {"type": "integer", "minimum": 1},
                },
            },
            permission="read",
            timeout_s=30.0,
            task_tags=["repair", "feature", "explanation", "refactor"],
            side_effects=False,
            capability_id="local.tool_search",
        ),
        impl.tool_search,
    )
    _register(
        ToolSpec(
            name="file_range",
            purpose="Read a bounded line range from one file",
            input_schema={
                "type": "object",
                "required": ["path"],
                "additionalProperties": False,
                "properties": {
                    "path": {"type": "string"},
                    "start": {"type": "integer", "minimum": 1},
                    "end": {"type": "integer", "minimum": 1},
                    "content_sha256": {"type": "string"},
                },
            },
            permission="read",
            timeout_s=10.0,
            task_tags=["repair", "feature", "explanation", "refactor", "ui"],
            side_effects=False,
            capability_id="local.tool_file_range",
        ),
        impl.tool_file_range,
    )
    _register(
        ToolSpec(
            name="symbols",
            purpose="Lookup symbol definitions (optional module disambiguation)",
            input_schema={
                "type": "object",
                "required": ["name"],
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "module": {"type": "string"},
                },
            },
            permission="read",
            timeout_s=15.0,
            task_tags=["repair", "refactor", "feature", "explanation"],
            side_effects=False,
            capability_id="local.tool_symbols",
        ),
        impl.tool_symbols,
    )
    _register(
        ToolSpec(
            name="diagnostics",
            purpose="Run/collect local diagnostics (Pyright when available)",
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {"require_pyright": {"type": "boolean"}},
            },
            permission="read",
            timeout_s=120.0,
            task_tags=["repair", "refactor"],
            side_effects=False,
            capability_id="local.tool_diagnostics",
        ),
        impl.tool_diagnostics,
    )
    _register(
        ToolSpec(
            name="patch",
            purpose="Apply a unique single-file text replacement with optional stale-hash guard",
            input_schema={
                "type": "object",
                "required": ["path", "old", "new"],
                "additionalProperties": False,
                "properties": {
                    "path": {"type": "string"},
                    "old": {"type": "string"},
                    "new": {"type": "string"},
                    "content_sha256": {"type": "string"},
                },
            },
            permission="write",
            timeout_s=10.0,
            task_tags=["repair", "feature", "refactor", "ui"],
            side_effects=True,
            capability_id="local.tool_patch",
        ),
        impl.tool_patch,
    )
    _register(
        ToolSpec(
            name="tests",
            purpose="Run a bounded local pytest invocation",
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "target": {"type": "string"},
                    "extra": {"type": "array", "items": {"type": "string"}},
                },
            },
            permission="exec_test",
            timeout_s=120.0,
            task_tags=["repair", "feature", "refactor", "automation"],
            side_effects=True,
            capability_id="local.tool_tests",
        ),
        impl.tool_tests,
    )
    _register(
        ToolSpec(
            name="diff",
            purpose="Unified diff or fingerprint for one file",
            input_schema={
                "type": "object",
                "required": ["path"],
                "additionalProperties": False,
                "properties": {
                    "path": {"type": "string"},
                    "before": {"type": "string"},
                },
            },
            permission="read",
            timeout_s=10.0,
            task_tags=["repair", "feature", "refactor", "ui", "explanation"],
            side_effects=False,
            capability_id="local.tool_diff",
        ),
        impl.tool_diff,
    )
    # Read-only verified API connectors (write ops never registered)
    from mainframe.connectors.registry_bridge import register_connector_tools

    register_connector_tools(_register)
    _register_browser_tools()


def _register_browser_tools() -> None:
    from mainframe.browser.handlers import (
        tool_browser_assert,
        tool_browser_click,
        tool_browser_dom,
        tool_browser_download,
        tool_browser_fill,
        tool_browser_navigate,
        tool_browser_screenshot,
        tool_browser_wait,
    )
    from mainframe.browser.probe import playwright_available

    pw = playwright_available()
    reason = None if pw else "Playwright unavailable; install local Chromium browsers"
    common = dict(
        permission="read",
        timeout_s=60.0,
        task_tags=["repair", "feature", "ui", "automation"],
        side_effects=False,
        available=pw,
        unavailable_reason=reason,
    )
    _register(
        ToolSpec(
            name="browser_navigate",
            purpose="Navigate session to URL; wait for DOM content loaded",
            input_schema={
                "type": "object",
                "required": ["session_id", "url"],
                "additionalProperties": False,
                "properties": {"session_id": {"type": "string"}, "url": {"type": "string"}},
            },
            capability_id="local.browser_navigate",
            **common,
        ),
        tool_browser_navigate,
    )
    _register(
        ToolSpec(
            name="browser_fill",
            purpose="Fill a field via semantic locator (role/label/text/test_id/css)",
            input_schema={
                "type": "object",
                "required": ["session_id", "locator", "value"],
                "additionalProperties": False,
                "properties": {
                    "session_id": {"type": "string"},
                    "locator": {"type": "object"},
                    "value": {"type": "string"},
                    "clear": {"type": "boolean"},
                },
            },
            capability_id="local.browser_fill",
            **{**common, "permission": "write", "side_effects": True},
        ),
        tool_browser_fill,
    )
    _register(
        ToolSpec(
            name="browser_click",
            purpose="Click element via semantic locator",
            input_schema={
                "type": "object",
                "required": ["session_id", "locator"],
                "additionalProperties": False,
                "properties": {"session_id": {"type": "string"}, "locator": {"type": "object"}},
            },
            capability_id="local.browser_click",
            **{**common, "permission": "write", "side_effects": True},
        ),
        tool_browser_click,
    )
    _register(
        ToolSpec(
            name="browser_dom",
            purpose="DOM inspection: text, HTML fragment, semantic presence, a11y snapshot",
            input_schema={
                "type": "object",
                "required": ["session_id"],
                "additionalProperties": False,
                "properties": {
                    "session_id": {"type": "string"},
                    "mode": {"type": "string"},
                    "selector": {"type": "string"},
                    "role": {"type": "string"},
                    "name": {"type": "string"},
                    "max_chars": {"type": "integer"},
                },
            },
            capability_id="local.browser_dom",
            **common,
        ),
        tool_browser_dom,
    )
    _register(
        ToolSpec(
            name="browser_screenshot",
            purpose="Capture screenshot to workspace path",
            input_schema={
                "type": "object",
                "required": ["session_id"],
                "additionalProperties": False,
                "properties": {
                    "session_id": {"type": "string"},
                    "path": {"type": "string"},
                    "full_page": {"type": "boolean"},
                },
            },
            capability_id="local.browser_screenshot",
            **{**common, "permission": "write", "side_effects": True},
        ),
        tool_browser_screenshot,
    )
    _register(
        ToolSpec(
            name="browser_download",
            purpose="Click trigger and save download via Playwright expect_download",
            input_schema={
                "type": "object",
                "required": ["session_id", "locator"],
                "additionalProperties": False,
                "properties": {
                    "session_id": {"type": "string"},
                    "locator": {"type": "object"},
                    "dest_dir": {"type": "string"},
                },
            },
            capability_id="local.browser_download",
            **{**common, "permission": "write", "side_effects": True},
        ),
        tool_browser_download,
    )
    _register(
        ToolSpec(
            name="browser_assert",
            purpose="Assert visible/text/count using locator waits (no arbitrary sleep)",
            input_schema={
                "type": "object",
                "required": ["session_id", "locator"],
                "additionalProperties": False,
                "properties": {
                    "session_id": {"type": "string"},
                    "locator": {"type": "object"},
                    "kind": {"type": "string"},
                    "text": {"type": "string"},
                    "count": {"type": "integer"},
                    "contains": {"type": "boolean"},
                    "timeout_ms": {"type": "integer"},
                },
            },
            capability_id="local.browser_assert",
            **common,
        ),
        tool_browser_assert,
    )
    _register(
        ToolSpec(
            name="browser_wait",
            purpose="Wait for selector visibility or load state",
            input_schema={
                "type": "object",
                "required": ["session_id"],
                "additionalProperties": False,
                "properties": {
                    "session_id": {"type": "string"},
                    "selector": {"type": "string"},
                    "state": {"type": "string"},
                    "load_state": {"type": "string"},
                },
            },
            capability_id="local.browser_wait",
            **common,
        ),
        tool_browser_wait,
    )


def get_tool(name: str) -> tuple[ToolSpec, ToolHandler] | None:
    _ensure_builtins()
    return _REGISTRY.get(name)


def list_tools(*, task_kind: str | None = None, include_unavailable: bool = False) -> list[dict[str, Any]]:
    """Expose only task-relevant tools when task_kind is set."""
    _ensure_builtins()
    out: list[dict[str, Any]] = []
    for name, (spec, _) in sorted(_REGISTRY.items()):
        if not include_unavailable and not spec.available:
            continue
        if task_kind and spec.task_tags and task_kind not in spec.task_tags and "mcp" not in spec.task_tags:
            # MCP only if explicitly relevant — still filter by tag if present
            if spec.source == "mcp" and task_kind not in spec.task_tags:
                continue
            if spec.source != "mcp":
                continue
        d = spec.to_dict()
        d["name"] = name
        out.append(d)
    return out


def register_mcp_tool(eval_result: dict[str, Any], handler: ToolHandler | None = None) -> dict[str, Any]:
    """Register or refresh an MCP tool after evaluate_mcp_tool()."""
    _ensure_builtins()
    spec: ToolSpec = eval_result["spec"]
    prior = _MCP_FINGERPRINTS.get(spec.name)
    fp = spec.schema_fingerprint or ""
    if prior and prior != fp:
        # Force re-eval already done by caller; mark fee/permission change if unavailable
        if not spec.available:
            spec.unavailable_reason = spec.unavailable_reason or "fee_or_permission_changed"

    def _unavailable_handler(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        return {
            "_error_code": "capability_unavailable",
            "error": spec.unavailable_reason or "mcp tool unavailable",
        }

    _register(spec, handler or _unavailable_handler)
    if fp:
        _MCP_FINGERPRINTS[spec.name] = fp
    return {
        "ok": True,
        "name": spec.name,
        "available": spec.available,
        "schema_fingerprint": fp,
        "fingerprint_changed": bool(prior and prior != fp),
    }


def reset_registry_for_tests() -> None:
    """Clear registry so builtins re-bind (accept isolation)."""
    _REGISTRY.clear()
    _MCP_FINGERPRINTS.clear()
