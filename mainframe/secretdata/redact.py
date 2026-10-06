"""Redact secrets from logs, traces, prompts, screenshots metadata, and exports."""

from __future__ import annotations

import copy
import re
from typing import Any

from mainframe.cache.redact import REDACTED, SECRET_KEY_RE, SECRET_VALUE_RE, redact_for_storage

# Surfaces that must always be redacted before leave-host or persist-as-log
REDACT_SURFACES = (
    "logs",
    "traces",
    "prompts",
    "screenshots",
    "exports",
)

# Extra patterns for prompt/body exfil
EXTRA_SECRET_RE = re.compile(
    r"(?i)("
    r"api[_-]?key\s*[:=]\s*\S+|"
    r"password\s*[:=]\s*\S+|"
    r"BEGIN (RSA |OPENSSH )?PRIVATE KEY|"
    r"eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}"  # JWT-ish
    r")"
)


def redact_text(text: str) -> str:
    out = SECRET_VALUE_RE.sub(REDACTED, text)
    out = EXTRA_SECRET_RE.sub(REDACTED, out)
    return out


def redact_for_surface(payload: Any, *, surface: str) -> dict[str, Any]:
    if surface not in REDACT_SURFACES:
        return {
            "ok": False,
            "error": "unknown_surface",
            "surface": surface,
            "allowed_surfaces": list(REDACT_SURFACES),
        }
    if isinstance(payload, str):
        redacted = redact_text(payload)
    elif isinstance(payload, dict) and surface == "screenshots":
        # Screenshot exports: scrub metadata/caption fields; never embed secrets
        meta = redact_for_storage(payload)
        if isinstance(meta.get("caption"), str):
            meta["caption"] = redact_text(meta["caption"])
        if isinstance(meta.get("ocr_text"), str):
            meta["ocr_text"] = redact_text(meta["ocr_text"])
        redacted = meta
    else:
        redacted = redact_for_storage(payload)
        if isinstance(redacted, str):
            redacted = redact_text(redacted)
        elif isinstance(redacted, dict):
            # Second pass string fields
            for k, v in list(redacted.items()):
                if isinstance(v, str):
                    redacted[k] = redact_text(v)
    return {
        "ok": True,
        "surface": surface,
        "redacted": redacted,
        "raw_returned": False,
    }


def redact_all_surfaces(payload: Any) -> dict[str, Any]:
    return {s: redact_for_surface(payload, surface=s) for s in REDACT_SURFACES}
