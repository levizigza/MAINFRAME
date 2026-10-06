"""Provider prompt caching — only where officially supported; record observed benefits."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.config import STATE_DIR, ensure_state

# Official support matrix (as of implementation). Hosted routes remain eligibility-gated.
# Do NOT assume prompt caching removes every quota charge.
PROVIDER_PROMPT_CACHE: dict[str, dict[str, Any]] = {
    "ollama_local": {
        "officially_supported": False,
        "notes": "Local Ollama has no MAINFRAME-documented prompt-cache billing API; prefer exact response reuse to avoid the request.",
    },
    "llamacpp_local": {
        "officially_supported": False,
        "notes": "No official prompt-cache entitlement recorded for loopback llama.cpp in MAINFRAME.",
    },
    "openai_api": {
        "officially_supported": True,
        "disabled_here": True,
        "notes": "OpenAI documents prompt caching; MAINFRAME keeps openai_api disabled (paid/hosted).",
    },
    "anthropic_api": {
        "officially_supported": True,
        "disabled_here": True,
        "notes": "Anthropic documents prompt caching; MAINFRAME keeps anthropic_api disabled.",
    },
    "google_gemini_api": {
        "officially_supported": False,
        "disabled_here": True,
        "notes": "Not treated as verified free prompt-cache entitlement.",
    },
    "groq_cloud": {
        "officially_supported": False,
        "disabled_here": True,
        "notes": "No verified recurring-free prompt-cache entitlement.",
    },
    "mistral_api": {
        "officially_supported": False,
        "disabled_here": True,
        "notes": "No verified recurring-free prompt-cache entitlement.",
    },
}

OBS_PATH = STATE_DIR / "cache" / "prompt_cache_observations.jsonl"


def prompt_cache_status(provider_id: str) -> dict[str, Any]:
    meta = PROVIDER_PROMPT_CACHE.get(provider_id)
    if not meta:
        return {
            "provider_id": provider_id,
            "officially_supported": False,
            "use": False,
            "reason": "unknown_provider",
        }
    use = bool(meta.get("officially_supported")) and not meta.get("disabled_here")
    return {
        "provider_id": provider_id,
        "officially_supported": bool(meta.get("officially_supported")),
        "disabled_here": bool(meta.get("disabled_here")),
        "use": use,
        "notes": meta.get("notes"),
        "assumption_refused": (
            "Do not assume prompt caching removes every quota charge; "
            "prefer avoiding an unnecessary request via exact response cache."
        ),
    }


def record_observed_benefit(
    *,
    provider_id: str,
    tokens_saved: int | None = None,
    latency_ms_saved: int | None = None,
    request_avoided: bool = False,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record measured benefits — never invent savings."""
    ensure_state()
    (STATE_DIR / "cache").mkdir(parents=True, exist_ok=True)
    row = {
        "at": datetime.now(timezone.utc).isoformat(),
        "provider_id": provider_id,
        "tokens_saved": tokens_saved,
        "latency_ms_saved": latency_ms_saved,
        "request_avoided": request_avoided,
        "detail": detail or {},
        "assumed_zero_quota": False,
    }
    with OBS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    return row


def prefer_avoid_request() -> dict[str, Any]:
    return {
        "policy": "prefer_exact_reuse_over_provider_prompt_cache",
        "reason": (
            "Avoiding an unnecessary request entirely is preferred over relying on "
            "provider prompt caching, which may still incur quota."
        ),
    }
