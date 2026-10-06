"""Never auto-install code suggested by a retrieved page."""

from __future__ import annotations

import re
from typing import Any

from mainframe.secretdata.untrusted import wrap_untrusted

INSTALL_RE = re.compile(
    r"(?i)\b("
    r"pip\s+install|python\s+-m\s+pip\s+install|"
    r"npm\s+i(nstall)?|pnpm\s+add|yarn\s+add|"
    r"cargo\s+install|go\s+install|"
    r"curl\s+[^\n]+ \|\s*(ba)?sh|"
    r"iex\s*\(|Invoke-Expression"
    r")\b"
)


def detect_install_suggestion(text: str) -> dict[str, Any]:
    m = INSTALL_RE.search(text or "")
    return {
        "suggested": bool(m),
        "matched": m.group(0) if m else None,
    }


def refuse_auto_install_from_page(
    page_text: str,
    *,
    source: str = "retrieved_page",
    url: str | None = None,
) -> dict[str, Any]:
    env = wrap_untrusted(page_text, kind="web_page", source=source, url=url)
    det = detect_install_suggestion(page_text)
    return {
        "ok": True,
        "auto_install": False,
        "install_executed": False,
        "suggestion_detected": det["suggested"],
        "matched": det.get("matched"),
        "reason": "never_auto_install_code_suggested_by_retrieved_page",
        "envelope_untrusted": True,
        "provenance": env["provenance"],
        "page_usable_as_data": True,
    }
