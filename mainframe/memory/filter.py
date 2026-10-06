"""Secret / conversation filters — do not save secrets or full chats by default."""

from __future__ import annotations

import re
from typing import Any

from mainframe.inventory.ignore import PRIVACY_BASENAMES, is_privacy_excluded

SECRET_PATTERNS = [
    re.compile(r"(?i)\b(api[_-]?key|secret|password|passwd|token|bearer)\s*[=:]\s*\S+"),
    re.compile(r"(?i)\b(AKIA|ghp_|sk-|xox[baprs]-)[A-Za-z0-9/_+=-]{8,}"),
    re.compile(r"(?i)-----BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY-----"),
]


def looks_like_secret(text: str) -> bool:
    if not text:
        return False
    for pat in SECRET_PATTERNS:
        if pat.search(text):
            return True
    return False


def reject_if_unsafe(
    body: str,
    *,
    paths: list[str] | None = None,
    save_conversation: bool = False,
) -> dict[str, Any]:
    """Return ok=False when content must not be stored."""
    if save_conversation:
        return {
            "ok": False,
            "error": "full_conversations_not_saved_by_default",
            "hint": "Store short accepted solutions or commands, not chat transcripts",
        }
    if looks_like_secret(body):
        return {"ok": False, "error": "secret_like_content_rejected"}
    for p in paths or []:
        if is_privacy_excluded(p) or p.split("/")[-1] in PRIVACY_BASENAMES:
            return {"ok": False, "error": "privacy_path_rejected", "path": p}
    return {"ok": True}
