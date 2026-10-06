"""Optional llama.cpp server adapter — loopback only.

Uses native `/health` + `/completion` and reports chat-template via `/props`
when available. OpenAI-compat `/v1/*` is not the preferred MAINFRAME path
(kept documented but unused for tool-sensitive flows).
"""

from __future__ import annotations

from typing import Any

from mainframe.eligibility import decide_provider, is_loopback_url
from mainframe.local_model.http_util import http_json

DEFAULT_LLAMACPP_URL = "http://127.0.0.1:8080"

ADAPTER_META = {
    "provider_id": "llamacpp_local",
    "protocol": "llamacpp_native",
    "health_route": "/health",
    "completion_route": "/completion",
    "props_route": "/props",
    "openai_compat_chat": "/v1/chat/completions",
    "openai_compat_used_by_default": False,
    "note": (
        "Optional. Prefer native /completion + /props. "
        "/v1/chat/completions exists but is not required for MAINFRAME."
    ),
}


def probe_llamacpp(base_url: str = DEFAULT_LLAMACPP_URL, timeout_s: float = 1.5) -> dict[str, Any]:
    decision = decide_provider("llamacpp_local", base_url)
    if not decision.eligible:
        return {
            "status": "paused",
            "available": False,
            "provider": "llamacpp_local",
            "detail": decision.reason,
            "adapter": ADAPTER_META,
            "eligibility": decision.to_dict(),
        }
    if not is_loopback_url(base_url):
        return {
            "status": "paused",
            "available": False,
            "provider": "llamacpp_local",
            "detail": "Non-loopback llama.cpp endpoint refused.",
            "adapter": ADAPTER_META,
        }

    health = http_json("GET", f"{base_url.rstrip('/')}/health", timeout_s=timeout_s)
    if not health.get("ok"):
        return {
            "status": "paused",
            "available": False,
            "provider": None,
            "detail": (
                f"No llama.cpp server at {base_url}/health ({health.get('error')}). "
                "Optional; no-local-model mode remains supported."
            ),
            "adapter": ADAPTER_META,
        }

    props = http_json("GET", f"{base_url.rstrip('/')}/props", timeout_s=timeout_s)
    chat_template = None
    model_path = None
    if props.get("ok"):
        data = props.get("data") or {}
        # Field names vary by llama.cpp version
        chat_template = (
            data.get("chat_template")
            or (data.get("default_generation_settings") or {}).get("chat_template")
        )
        model_path = data.get("model_path") or data.get("model")

    return {
        "status": "available",
        "available": True,
        "provider": "llamacpp_local",
        "detail": "llama.cpp /health responded on loopback.",
        "model_path": model_path,
        "chat_template_present": bool(chat_template),
        "chat_template_excerpt": (str(chat_template)[:400] if chat_template else None),
        "adapter": ADAPTER_META,
        "eligibility": decision.to_dict(),
    }


def complete_llamacpp(
    base_url: str,
    prompt: str,
    *,
    n_predict: int = 128,
    timeout_s: float = 120.0,
) -> dict[str, Any]:
    decision = decide_provider("llamacpp_local", base_url)
    if not decision.eligible:
        return {
            "ok": False,
            "paused": True,
            "refused": True,
            "message": decision.reason,
            "fallback_used": False,
        }
    res = http_json(
        "POST",
        f"{base_url.rstrip('/')}/completion",
        {"prompt": prompt, "n_predict": n_predict, "stream": False},
        timeout_s=timeout_s,
    )
    if not res.get("ok"):
        return {
            "ok": False,
            "paused": True,
            "fallback_used": False,
            "message": res.get("error") or "completion failed",
            "route": "/completion",
            "adapter": ADAPTER_META,
        }
    data = res.get("data") or {}
    return {
        "ok": True,
        "paused": False,
        "provider": "llamacpp_local",
        "content": data.get("content", ""),
        "route": "/completion",
        "openai_compat_used": False,
        "raw_timings": data.get("timings"),
        "fallback_used": False,
        "adapter": ADAPTER_META,
        "eligibility": decision.to_dict(),
    }
