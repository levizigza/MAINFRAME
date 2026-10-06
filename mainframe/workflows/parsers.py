"""Known-format parsers and validated rules (stdlib only — no model required)."""

from __future__ import annotations

import re
from typing import Any, Callable

Parser = Callable[[str], dict[str, Any] | None]

_PACKAGE_VER = re.compile(
    r"(?i)Package\s+(?P<name>[A-Za-z0-9_.\-]+)\s+version\s+(?P<version>\d+(?:\.\d+)*)"
)
_ERROR_PATH = re.compile(
    r"(?i)Error\s+(?P<code>[A-Za-z0-9_\-]+)\s+in\s+(?P<file>[^\s]+)"
)
_EMAIL_SUBJECT = re.compile(r"(?im)^Subject:\s*(?P<subject>.+)$")


def parse_package_version(text: str) -> dict[str, Any] | None:
    m = _PACKAGE_VER.search(text or "")
    if not m:
        return None
    return {"name": m.group("name"), "version": m.group("version"), "parser": "package_version"}


def parse_error_code_path(text: str) -> dict[str, Any] | None:
    m = _ERROR_PATH.search(text or "")
    if not m:
        return None
    return {"code": m.group("code"), "file": m.group("file"), "parser": "error_code_path"}


def parse_email_subject(text: str) -> dict[str, Any] | None:
    m = _EMAIL_SUBJECT.search(text or "")
    if not m:
        return None
    return {"subject": m.group("subject").strip(), "parser": "email_subject"}


PARSERS: dict[str, Parser] = {
    "package_version": parse_package_version,
    "error_code_path": parse_error_code_path,
    "email_subject": parse_email_subject,
}


def parse_known_format(format_id: str, text: str) -> dict[str, Any]:
    """
    Apply a validated parser for a known format.
    Returns ok=False when the format does not match — never invents fields.
    """
    fn = PARSERS.get(format_id)
    if fn is None:
        return {"ok": False, "error": f"unknown_format:{format_id}", "uncertain": True}
    parsed = fn(text)
    if parsed is None:
        return {
            "ok": False,
            "error": "format_mismatch",
            "uncertain": True,
            "format": format_id,
            "reason": "Source does not match known format; refusing invented values.",
        }
    return {"ok": True, "uncertain": False, "format": format_id, "fields": parsed}
