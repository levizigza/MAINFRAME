"""Registry handlers delegating to browser.tools."""

from __future__ import annotations

from typing import Any

from mainframe.browser.tools import invoke_browser_tool


def _wrap(name: str):
    def handler(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        return invoke_browser_tool(name, args, ctx)

    return handler


tool_browser_navigate = _wrap("browser_navigate")
tool_browser_fill = _wrap("browser_fill")
tool_browser_click = _wrap("browser_click")
tool_browser_dom = _wrap("browser_dom")
tool_browser_screenshot = _wrap("browser_screenshot")
tool_browser_download = _wrap("browser_download")
tool_browser_assert = _wrap("browser_assert")
tool_browser_wait = _wrap("browser_wait")
