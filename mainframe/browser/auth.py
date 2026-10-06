"""Preserve authentication challenges for the user — no bypass."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


def detect_auth_challenge(page: Any, url: str) -> dict[str, Any]:
    parsed = urlparse(url)
    path_lower = (parsed.path or "").lower()
    url_hints = any(x in path_lower for x in ("/login", "/signin", "/auth", "/oauth"))
    try:
        password_fields = page.locator('input[type="password"]').count()
    except Exception:  # noqa: BLE001
        password_fields = 0
    challenged = url_hints or password_fields > 0
    return {
        "auth_challenge": challenged,
        "paused_for_user": challenged,
        "bypass_attempted": False,
        "password_fields": password_fields,
        "url_hint": url_hints,
        "message": (
            "Authentication required — complete sign-in manually; automation will not fill credentials."
            if challenged
            else "No auth challenge detected."
        ),
    }
