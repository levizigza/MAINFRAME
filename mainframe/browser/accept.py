"""Acceptance: layout-tolerant locators, missing control, external submit hold."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from mainframe.browser.auth import detect_auth_challenge
from mainframe.browser.demo_maintenance import run_website_maintenance_demo, verify_layout_variant
from mainframe.browser.probe import playwright_available
from mainframe.browser.profiles import profile_dir
from mainframe.browser.session import ephemeral_session, open_session, close_session
from mainframe.browser.submit_guard import guard_external_submission
from mainframe.browser.tools import browser_dom, browser_navigate
from mainframe.browser.visual import interpret_page_visually
from mainframe.capabilities.store import CapabilityStore
from mainframe.tools.registry import get_tool, list_tools


def run_browser_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    pw_ok = playwright_available()

    # Tool registry exposes Playwright-backed tools when runtime is present.
    list_tools(include_unavailable=True)
    names = {t["name"] for t in list_tools(include_unavailable=True)}
    expected = {
        "browser_navigate",
        "browser_fill",
        "browser_click",
        "browser_dom",
        "browser_screenshot",
        "browser_assert",
        "browser_wait",
    }
    checks.append(
        {
            "id": "playwright_tools_registered",
            "ok": expected <= names,
            "detail": {"registered": sorted(names & expected), "playwright": pw_ok},
        }
    )

    checks.append(
        {
            "id": "per_project_browser_profiles",
            "ok": profile_dir("proj_a") != profile_dir("proj_b"),
            "detail": {
                "a": str(profile_dir("proj_a")),
                "b": str(profile_dir("proj_b")),
            },
        }
    )

    tmp = Path(tempfile.mkdtemp(prefix="mf-browser-acc-"))
    store = CapabilityStore(tmp / "caps.sqlite")
    store.grant(
        project_id="browser_accept",
        capabilities=["sending_messages"],
        destinations=["reports@example.com"],
        operations=["send_report"],
    )
    hold = guard_external_submission(
        store,
        project_id="browser_accept",
        form_action="https://external.example/report",
    )
    checks.append(
        {
            "id": "external_submission_paused_unapproved",
            "ok": (
                hold.get("external") is True
                and hold.get("held") is True
                and hold.get("paused") is True
                and (hold.get("preview") or {}).get("concrete") is True
            ),
            "detail": {"hold_reason": (hold.get("preview") or {}).get("hold_reason")},
        }
    )

    visual = interpret_page_visually(dom_evidence={"present": False, "summary": "status broken"})
    checks.append(
        {
            "id": "dom_evidence_before_visual_route",
            "ok": visual.get("dom_first") is True and visual.get("visual_used") is False,
            "detail": visual,
        }
    )

    if not pw_ok:
        checks.append(
            {
                "id": "playwright_runtime",
                "ok": False,
                "detail": {"paused": True, "message": "Playwright required for remaining browser accept checks"},
            }
        )
        passed = sum(1 for c in checks if c["ok"])
        return {"ok": False, "paused": True, "passed": passed, "failed": len(checks) - passed, "checks": checks}

    layout = verify_layout_variant()
    checks.append(
        {
            "id": "modest_layout_change_semantic_locator",
            "ok": layout.get("ok") is True,
            "detail": layout,
        }
    )

    demo = run_website_maintenance_demo(store)
    checks.append(
        {
            "id": "website_maintenance_demo",
            "ok": demo.get("ok") is True,
            "detail": {
                "missing_before": (demo.get("missing_control_before") or {}).get("present") is False,
                "status_after": demo.get("status_after"),
                "external_held": (demo.get("external_submit_guard") or {}).get("held"),
            },
        }
    )

    with ephemeral_session(project_id="auth_check") as page:
        page.set_content(
            '<html><body><form action="/login"><input type="password" name="pw"/></form></body></html>'
        )
        auth = detect_auth_challenge(page, "https://example.test/login")
    checks.append(
        {
            "id": "auth_challenge_preserved_for_user",
            "ok": auth.get("auth_challenge") is True and auth.get("paused_for_user") is True,
            "detail": auth,
        }
    )

    # Session tool smoke: navigate + dom via registered handlers
    opened = open_session("tool_smoke")
    sid = opened.get("session_id")
    tool_ok = False
    detail: dict[str, Any] = {}
    if sid:
        from mainframe.config import ROOT

        ctx = {"root": ROOT}
        nav = browser_navigate({"session_id": sid, "url": "about:blank"}, ctx)
        dom = browser_dom(
            {"session_id": sid, "mode": "html_fragment", "selector": "body", "max_chars": 200},
            ctx,
        )
        tool_ok = nav.get("ok") and dom.get("ok")
        detail = {"nav": nav.get("title"), "dom_len": len(dom.get("html") or "")}
        close_session(sid)
    spec = get_tool("browser_navigate")
    checks.append(
        {
            "id": "direct_playwright_api_tools",
            "ok": tool_ok and spec is not None,
            "detail": detail,
        }
    )

    passed = sum(1 for c in checks if c["ok"])
    failed = len(checks) - passed
    return {"ok": failed == 0, "passed": passed, "failed": failed, "checks": checks}
