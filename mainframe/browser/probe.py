"""Playwright availability probe (local Chromium only)."""

from __future__ import annotations

from mainframe.freeforge import probe_playwright


def playwright_status() -> dict[str, object]:
    return probe_playwright()


def playwright_available() -> bool:
    st = playwright_status()
    return st.get("status") == "available"
