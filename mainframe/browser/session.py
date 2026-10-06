"""Browser session with per-project persistent profile."""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Any, Iterator
from urllib.parse import urlparse

from mainframe.browser.probe import playwright_available
from mainframe.browser.profiles import profile_dir
from mainframe.browser.waits import wait_for_load


class BrowserSessionError(RuntimeError):
    pass


_SESSIONS: dict[str, dict[str, Any]] = {}


@contextmanager
def ephemeral_session(*, project_id: str, headless: bool = True) -> Iterator[Any]:
    """Launch Chromium with isolated user data dir; always closes on exit."""
    if not playwright_available():
        raise BrowserSessionError("Playwright unavailable")
    from playwright.sync_api import sync_playwright

    user_data = profile_dir(project_id)
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(user_data),
            headless=headless,
            accept_downloads=True,
        )
        page = context.pages[0] if context.pages else context.new_page()
        try:
            yield page
        finally:
            context.close()


def open_session(project_id: str, *, headless: bool = True) -> dict[str, Any]:
    if not playwright_available():
        return {"ok": False, "error": "playwright_unavailable"}
    sid = f"bs_{uuid.uuid4().hex[:12]}"
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    user_data = profile_dir(project_id)
    context = pw.chromium.launch_persistent_context(
        user_data_dir=str(user_data),
        headless=headless,
        accept_downloads=True,
    )
    page = context.pages[0] if context.pages else context.new_page()
    _SESSIONS[sid] = {"playwright": pw, "context": context, "page": page, "project_id": project_id}
    return {"ok": True, "session_id": sid, "project_id": project_id}


def close_session(session_id: str) -> dict[str, Any]:
    rec = _SESSIONS.pop(session_id, None)
    if not rec:
        return {"ok": False, "error": "unknown_session"}
    try:
        rec["context"].close()
        rec["playwright"].stop()
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "session_id": session_id}


def get_page(session_id: str) -> Any:
    rec = _SESSIONS.get(session_id)
    if not rec:
        raise BrowserSessionError("unknown_session")
    return rec["page"]


def get_session(session_id: str) -> dict[str, Any] | None:
    return _SESSIONS.get(session_id)


def get_page_for_project(session_id: str, project_id: str) -> dict[str, Any]:
    """Refuse reused browser sessions across projects — no cookie/storage exposure."""
    from mainframe.projects.isolation import refuse_reused_browser_session

    rec = _SESSIONS.get(session_id)
    gate = refuse_reused_browser_session(
        session_project_id=(rec or {}).get("project_id") if rec else None,
        requester_project_id=project_id,
        session_id=session_id,
    )
    if not gate.get("allowed"):
        return {
            "ok": False,
            **gate,
            "page": None,
        }
    return {"ok": True, "page": rec["page"], "project_id": project_id, "session_id": session_id}


def navigate(page: Any, url: str, *, wait: bool = True) -> dict[str, Any]:
    parsed = urlparse(url)
    if parsed.scheme not in ("file", "http", "https", "about"):
        return {"ok": False, "error": "unsupported_scheme", "url": url}
    page.goto(url, wait_until="domcontentloaded")
    if wait:
        wait_for_load(page)
    return {"ok": True, "url": page.url, "title": page.title()}
