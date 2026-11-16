"""Deterministic local UI wiring — attach missing click handlers (no model)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def propose_ui_wire_edits(root: Path) -> dict[str, Any]:
    """
    If ``app.js`` defines ``markReady`` (or similar) but never registers a click
    listener, and ``index.html`` exposes a Prepare control, propose the standard
    aria-label listener line used by FreeForge site/UI fixtures.
    """
    root = root.resolve()
    js = root / "app.js"
    html = root / "index.html"
    if not js.is_file() or not html.is_file():
        return {"edits": [], "source": "ui_wire", "model_service_used": False}

    try:
        js_src = js.read_text(encoding="utf-8")
        html_src = html.read_text(encoding="utf-8")
    except OSError:
        return {"edits": [], "source": "ui_wire", "model_service_used": False}

    has_prepare = bool(
        re.search(r'aria-label\s*=\s*["\']Prepare["\']', html_src, re.I)
        or re.search(r">\s*Prepare\s*<", html_src)
    )
    has_status = 'id="status"' in html_src or "id='status'" in html_src
    has_handler = bool(re.search(r"\bfunction\s+markReady\b|\bmarkReady\s*=", js_src))
    already_wired = bool(
        re.search(r"addEventListener\s*\(\s*['\"]click['\"]", js_src)
        or re.search(r"\.onclick\s*=", js_src)
        or "get_by_role" in js_src  # noqa: not JS — keep simple
    )
    if not (has_prepare and has_status and has_handler) or already_wired:
        return {"edits": [], "source": "ui_wire", "model_service_used": False}

    line = (
        "document.querySelector('[aria-label=\"Prepare\"]')"
        ".addEventListener('click', markReady);\n"
    )
    # Append after last non-empty content
    if js_src.endswith("\n"):
        old = js_src
        new = js_src + line
    else:
        old = js_src
        new = js_src + "\n" + line

    # Prefer a minimal old/new suffix edit for patch apply
    # Use the whole file as old if small
    if len(old) < 4000:
        edits = [{"path": "app.js", "old": old, "new": new}]
    else:
        # last 200 chars as anchor
        tail = old[-200:]
        edits = [{"path": "app.js", "old": tail, "new": tail + ("" if tail.endswith("\n") else "\n") + line}]

    return {
        "edits": edits,
        "source": "ui_wire",
        "evidence": {
            "prepare_control": True,
            "markReady": True,
            "listener_was_missing": True,
        },
        "model_service_used": False,
    }
