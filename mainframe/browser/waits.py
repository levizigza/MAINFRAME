"""Wait for observable DOM conditions — avoid arbitrary sleeps."""

from __future__ import annotations

from typing import Any


def wait_for_selector(page: Any, selector: str, *, state: str = "visible", timeout_ms: int = 15000) -> dict[str, Any]:
    page.locator(selector).first.wait_for(state=state, timeout=timeout_ms)
    return {"ok": True, "selector": selector, "state": state, "method": "playwright_wait_for"}


def wait_for_load(page: Any, *, state: str = "domcontentloaded", timeout_ms: int = 30000) -> dict[str, Any]:
    page.wait_for_load_state(state, timeout=timeout_ms)
    return {"ok": True, "load_state": state, "method": "playwright_load_state"}
