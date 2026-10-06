"""Redact secrets before any cache write."""

from __future__ import annotations

import copy
import re
from typing import Any

SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|token|secret|password|passwd|authorization|credential|private[_-]?key)",
    re.I,
)
SECRET_VALUE_RE = re.compile(
    r"(?i)(bearer\s+[a-z0-9\-._~+/]+=*|sk-[a-z0-9]{10,}|ghp_[a-z0-9]{20,}|xox[baprs]-[a-z0-9-]{10,})"
)

REDACTED = "[REDACTED]"


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return SECRET_VALUE_RE.sub(REDACTED, value)
    if isinstance(value, dict):
        return redact_mapping(value)
    if isinstance(value, list):
        return [redact_value(v) for v in value]
    return value


def redact_mapping(obj: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in obj.items():
        if SECRET_KEY_RE.search(str(k)):
            out[k] = REDACTED
        else:
            out[k] = redact_value(v)
    return out


def redact_for_storage(payload: Any) -> Any:
    """Deep-copy and redact — never store raw secrets in cache blobs."""
    return redact_value(copy.deepcopy(payload))
