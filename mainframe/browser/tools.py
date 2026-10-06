"""Playwright tool operations — navigation, locators, forms, DOM, screenshots, downloads, asserts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mainframe.browser.locators import resolve_locator, semantic_control_present
from mainframe.browser.session import BrowserSessionError, get_page, navigate
from mainframe.browser.waits import wait_for_load, wait_for_selector


def browser_navigate(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    page = get_page(args["session_id"])
    return navigate(page, args["url"])


def browser_fill(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    page = get_page(args["session_id"])
    loc = resolve_locator(page, args["locator"])
    value = args.get("value") or ""
    if args.get("clear"):
        loc.fill("")
    loc.fill(value)
    return {"ok": True, "filled": True, "value_len": len(value)}


def browser_click(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    page = get_page(args["session_id"])
    loc = resolve_locator(page, args["locator"])
    loc.click()
    return {"ok": True, "clicked": True}


def browser_dom(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    page = get_page(args["session_id"])
    mode = args.get("mode") or "snapshot"
    if mode == "selector_text":
        sel = args["selector"]
        wait_for_selector(page, sel)
        text = page.locator(sel).first.inner_text()
        return {"ok": True, "mode": mode, "text": text, "evidence": "dom"}
    if mode == "semantic_presence":
        return {"ok": True, **semantic_control_present(page, role=args["role"], name=args.get("name"))}
    if mode == "html_fragment":
        sel = args.get("selector") or "body"
        html = page.locator(sel).first.inner_html()
        cap = int(args.get("max_chars") or 4000)
        return {"ok": True, "html": html[:cap], "truncated": len(html) > cap, "evidence": "dom"}
    if mode == "accessibility_tree":
        # Prefer Playwright accessibility snapshot when available.
        snap = page.accessibility.snapshot()
        return {"ok": True, "snapshot": snap, "evidence": "dom"}
    return {"ok": False, "error": "unknown_mode", "mode": mode}


def browser_screenshot(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    page = get_page(args["session_id"])
    root = Path(ctx["root"])
    rel = args.get("path") or ".mainframe/browser_shots/capture.png"
    out = root / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    full_page = bool(args.get("full_page"))
    page.screenshot(path=str(out), full_page=full_page)
    return {"ok": True, "path": str(rel).replace("\\", "/"), "full_page": full_page}


def browser_download(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    page = get_page(args["session_id"])
    root = Path(ctx["root"])
    dest_dir = root / (args.get("dest_dir") or ".mainframe/browser_downloads")
    dest_dir.mkdir(parents=True, exist_ok=True)
    loc = resolve_locator(page, args["locator"])
    with page.expect_download() as dl_info:
        loc.click()
    download = dl_info.value
    suggested = download.suggested_filename
    target = dest_dir / suggested
    download.save_as(str(target))
    return {"ok": True, "filename": suggested, "path": str(target.relative_to(root)).replace("\\", "/")}


def browser_assert(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    page = get_page(args["session_id"])
    kind = args.get("kind") or "visible"
    loc = resolve_locator(page, args["locator"])
    if kind == "visible":
        loc.wait_for(state="visible", timeout=int(args.get("timeout_ms") or 15000))
        return {"ok": True, "assertion": "visible", "passed": True}
    if kind == "text":
        expected = args["text"]
        wait_for_load(page)
        actual = loc.inner_text()
        passed = expected in actual if args.get("contains") else actual.strip() == expected.strip()
        return {"ok": passed, "assertion": "text", "passed": passed, "actual": actual}
    if kind == "count":
        expected = int(args["count"])
        actual = loc.count()
        passed = actual == expected
        return {"ok": passed, "assertion": "count", "passed": passed, "actual": actual}
    return {"ok": False, "error": "unknown_assert_kind", "kind": kind}


def browser_wait(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    page = get_page(args["session_id"])
    if args.get("selector"):
        return wait_for_selector(page, args["selector"], state=args.get("state") or "visible")
    return wait_for_load(page, state=args.get("load_state") or "domcontentloaded")


def invoke_browser_tool(name: str, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    try:
        handlers = {
            "browser_navigate": browser_navigate,
            "browser_fill": browser_fill,
            "browser_click": browser_click,
            "browser_dom": browser_dom,
            "browser_screenshot": browser_screenshot,
            "browser_download": browser_download,
            "browser_assert": browser_assert,
            "browser_wait": browser_wait,
        }
        fn = handlers.get(name)
        if not fn:
            return {"_error_code": "unknown_tool", "error": name}
        return fn(args, ctx)
    except BrowserSessionError as exc:
        return {"_error_code": "capability_unavailable", "error": str(exc)}
