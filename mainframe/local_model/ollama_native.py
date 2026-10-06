"""Ollama native adapter — OpenClaw-documented `/api/chat` (not `/v1`).

Docs: https://docs.openclaw.ai/providers/ollama/
       https://docs.ollama.com/api/chat

Local-only: loopback baseUrl, reject `:cloud` models, prefer OLLAMA_NO_CLOUD.
"""

from __future__ import annotations

import os
from typing import Any

from mainframe.eligibility import decide_provider
from mainframe.local_model.cloud_guard import assert_local_only, filter_local_models
from mainframe.local_model.http_util import http_json

# Documented native routes (no /v1 OpenAI-compat — breaks tools per OpenClaw).
NATIVE_TAGS = "/api/tags"
NATIVE_SHOW = "/api/show"
NATIVE_CHAT = "/api/chat"
# Intentionally unused for tool-capable chat:
OPENAI_COMPAT_PREFIX = "/v1"

ADAPTER_META = {
    "provider_id": "ollama_local",
    "protocol": "ollama_native",
    "chat_route": NATIVE_CHAT,
    "openai_compat_used": False,
    "openclaw_alignment": (
        "Uses baseUrl without /v1 and POST /api/chat (OpenClaw Ollama provider docs)."
    ),
    "local_only_config": {
        "loopback_required": True,
        "reject_cloud_suffix": True,
        "ollama_no_cloud_env": "OLLAMA_NO_CLOUD",
        "server_json_key": "disable_ollama_cloud",
        "note": (
            "MAINFRAME never points at https://ollama.com. "
            "Recommend OLLAMA_NO_CLOUD=1 / disable_ollama_cloud for the daemon."
        ),
    },
}


def _base(url: str) -> str:
    return url.rstrip("/")


def ollama_local_env_hints() -> dict[str, Any]:
    no_cloud = os.environ.get("OLLAMA_NO_CLOUD", "").strip()
    return {
        "OLLAMA_NO_CLOUD": no_cloud or None,
        "ollama_no_cloud_active": no_cloud in {"1", "true", "TRUE", "yes", "YES"},
        "recommendation": "Set OLLAMA_NO_CLOUD=1 (or disable_ollama_cloud in ~/.ollama/server.json).",
    }


def list_local_models(base_url: str, timeout_s: float = 1.0) -> dict[str, Any]:
    decision = decide_provider("ollama_local", base_url)
    if not decision.eligible:
        return {
            "ok": False,
            "available": False,
            "reason": decision.reason,
            "eligibility": decision.to_dict(),
            "adapter": ADAPTER_META,
        }
    guard = assert_local_only(base_url)
    if not guard["ok"]:
        return {**guard, "available": False, "adapter": ADAPTER_META}

    res = http_json("GET", f"{_base(base_url)}{NATIVE_TAGS}", timeout_s=timeout_s)
    if not res.get("ok"):
        return {
            "ok": False,
            "available": False,
            "reason": res.get("error") or "tags probe failed",
            "adapter": ADAPTER_META,
            "env": ollama_local_env_hints(),
        }
    models = res.get("data", {}).get("models") or []
    names = [m.get("name", "") for m in models if isinstance(m, dict) and m.get("name")]
    filtered = filter_local_models(names)
    return {
        "ok": True,
        "available": bool(filtered["local_models"]),
        "models": filtered["local_models"],
        "cloud_models_excluded": filtered["cloud_models_excluded"],
        "adapter": ADAPTER_META,
        "env": ollama_local_env_hints(),
        "eligibility": decision.to_dict(),
    }


def show_model(base_url: str, model: str, timeout_s: float = 10.0) -> dict[str, Any]:
    guard = assert_local_only(base_url, model)
    if not guard["ok"]:
        return {**guard, "verified": False}
    decision = decide_provider("ollama_local", base_url)
    if not decision.eligible:
        return {"ok": False, "verified": False, "reason": decision.reason}

    res = http_json(
        "POST",
        f"{_base(base_url)}{NATIVE_SHOW}",
        {"name": model},
        timeout_s=timeout_s,
    )
    if not res.get("ok"):
        return {
            "ok": False,
            "verified": False,
            "reason": res.get("error") or "show failed",
            "body": res.get("body"),
        }
    data = res.get("data") or {}
    details = data.get("details") or {}
    modelfile = str(data.get("modelfile") or "")
    template = data.get("template")
    license_field = data.get("license")
    # Ollama may return license as string or list
    if isinstance(license_field, list):
        license_text = "\n".join(str(x) for x in license_field)[:4000]
    else:
        license_text = str(license_field or "")[:4000]

    caps = data.get("capabilities") or details.get("capabilities") or []
    tools_cap = False
    if isinstance(caps, list):
        tools_cap = any(str(c).lower() == "tools" for c in caps)
    # Also scan modelfile for TEMPLATE presence
    has_template = bool(template) or ("TEMPLATE" in modelfile.upper())

    return {
        "ok": True,
        "verified": True,
        "model": model,
        "protocol": {
            "route_used": NATIVE_SHOW,
            "chat_route": NATIVE_CHAT,
            "openai_compat_used": False,
        },
        "chat_template": {
            "present": has_template,
            "template_excerpt": (str(template)[:500] if template else None),
            "note": "Ollama applies Modelfile TEMPLATE on native /api/chat (not client-side).",
        },
        "tools": {
            "capability_flag": tools_cap,
            "capabilities": caps if isinstance(caps, list) else [],
            "note": "Capability flag ≠ measured tool round-trip; run bench tool_use.",
        },
        "license": {
            "text_excerpt": license_text[:1500] if license_text else None,
            "reported": bool(license_text.strip()),
            "note": "Re-check weight license before redistribution.",
        },
        "details": details,
        "adapter": ADAPTER_META,
    }


def chat(
    base_url: str,
    model: str,
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    timeout_s: float = 120.0,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """POST native /api/chat — OpenClaw-documented route."""
    guard = assert_local_only(base_url, model)
    if not guard["ok"]:
        return {
            "ok": False,
            "paused": True,
            "refused": True,
            "fallback_used": False,
            "message": guard["reason"],
            "local_only": guard,
        }
    decision = decide_provider("ollama_local", base_url)
    if not decision.eligible:
        return {
            "ok": False,
            "paused": True,
            "refused": True,
            "fallback_used": False,
            "message": decision.reason,
            "eligibility": decision.to_dict(),
        }

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    if tools:
        payload["tools"] = tools
    if options:
        payload["options"] = options

    # Refuse accidental OpenAI-compat base paths
    if "/v1" in _base(base_url).rstrip("/").split("://", 1)[-1]:
        return {
            "ok": False,
            "paused": True,
            "refused": True,
            "fallback_used": False,
            "message": (
                "OpenAI-compatible /v1 baseUrl rejected (OpenClaw: breaks tool calling). "
                "Use http://127.0.0.1:11434 without /v1."
            ),
        }

    res = http_json(
        "POST",
        f"{_base(base_url)}{NATIVE_CHAT}",
        payload,
        timeout_s=timeout_s,
    )
    if not res.get("ok"):
        return {
            "ok": False,
            "paused": True,
            "fallback_used": False,
            "message": res.get("error") or "chat failed",
            "http_status": res.get("status"),
            "body": res.get("body"),
            "route": NATIVE_CHAT,
            "adapter": ADAPTER_META,
        }

    data = res.get("data") or {}
    message = data.get("message") or {}
    return {
        "ok": True,
        "paused": False,
        "provider": "ollama_local",
        "model": model,
        "route": NATIVE_CHAT,
        "openai_compat_used": False,
        "message": message,
        "content": message.get("content", ""),
        "tool_calls": message.get("tool_calls"),
        "raw": {
            "done": data.get("done"),
            "total_duration": data.get("total_duration"),
            "eval_count": data.get("eval_count"),
            "prompt_eval_count": data.get("prompt_eval_count"),
        },
        "fallback_used": False,
        "adapter": ADAPTER_META,
        "eligibility": decision.to_dict(),
    }
