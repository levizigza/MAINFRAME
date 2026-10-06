"""Redact secrets from diagnostic artifacts retained after workflow runs."""

from __future__ import annotations

import re
from typing import Any

_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|secret|token|password|authorization|bearer)\s*[:=]\s*\S+"),
    re.compile(r"(?i)sk-[a-zA-Z0-9]{8,}"),
    re.compile(r"(?i)bearer\s+[a-zA-Z0-9._\-]+"),
)


def redact_text(text: str) -> str:
    out = text
    for pat in _SECRET_PATTERNS:
        out = pat.sub("[REDACTED]", out)
    return out


def redact_diag(obj: Any) -> Any:
    if isinstance(obj, str):
        return redact_text(obj)
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            key = str(k)
            key_l = key.lower()
            secret_key = bool(
                re.search(r"(?i)secret|password|api_key|authorization|api_token|access_token", key)
            ) or ( "token" in key_l and "quota" not in key_l )
            if secret_key:
                out[k] = "[REDACTED]"
            else:
                out[k] = redact_diag(v)
        return out
    if isinstance(obj, list):
        return [redact_diag(x) for x in obj]
    return obj
