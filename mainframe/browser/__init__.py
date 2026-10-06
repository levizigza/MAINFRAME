"""Playwright browser tools — per-project profiles, DOM-first automation."""

from __future__ import annotations

from mainframe.browser.accept import run_browser_accept
from mainframe.browser.demo_maintenance import run_website_maintenance_demo
from mainframe.browser.probe import playwright_available, playwright_status

__all__ = [
    "playwright_available",
    "playwright_status",
    "run_browser_accept",
    "run_website_maintenance_demo",
]
