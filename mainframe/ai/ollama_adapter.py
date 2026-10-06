"""Eligible Ollama adapter — loopback only, behind eligibility gate.

Prefers OpenClaw-documented native `/api/chat`; rejects `:cloud` models.
"""

from __future__ import annotations

from typing import Any

from mainframe.eligibility import decide_provider
from mainframe.local_model.cloud_guard import assert_local_only
from mainframe.local_model.ollama_native import chat as native_chat
from mainframe.local_model.ollama_native import list_local_models


def probe_ollama(base_url: str, timeout_s: float = 2.0) -> dict[str, Any]:
    decision = decide_provider("ollama_local", base_url)
    if not decision.eligible:
        return {
            "status": "paused",
            "provider": "ollama_local",
            "detail": decision.reason,
            "free_only": True,
            "eligibility": decision.to_dict(),
        }

    tags = list_local_models(base_url, timeout_s=timeout_s)
    if not tags.get("ok"):
        return {
            "status": "paused",
            "provider": None,
            "detail": (
                f"No free local inference at {base_url.rstrip('/')}/api/tags "
                f"({tags.get('reason')}). Progress preserved; AI-dependent steps paused."
            ),
            "free_only": True,
            "eligibility": decision.to_dict(),
            "cloud_models_excluded": tags.get("cloud_models_excluded") or [],
        }

    names = tags.get("models") or []
    excluded = tags.get("cloud_models_excluded") or []
    if names:
        detail = f"Local Ollama responded with models: {', '.join(names[:8])}"
        if excluded:
            detail += f" (excluded cloud: {', '.join(excluded[:4])})"
        return {
            "status": "available",
            "provider": "ollama_local",
            "detail": detail,
            "free_only": True,
            "models": names,
            "cloud_models_excluded": excluded,
            "protocol": "ollama_native_/api/chat",
            "eligibility": decision.to_dict(),
        }
    return {
        "status": "paused",
        "provider": "ollama_local",
        "detail": (
            "Ollama is reachable but no local (non-cloud) models are installed. "
            "AI-dependent steps paused; deterministic automation remains usable."
        ),
        "free_only": True,
        "models": [],
        "cloud_models_excluded": excluded,
        "eligibility": decision.to_dict(),
    }


def generate_ollama(base_url: str, prompt: str, model: str, timeout_s: float = 60.0) -> dict[str, Any]:
    decision = decide_provider("ollama_local", base_url)
    if not decision.eligible:
        return {
            "ok": False,
            "paused": True,
            "refused": True,
            "fallback_used": False,
            "prompt_preserved": prompt,
            "message": decision.reason,
            "eligibility": decision.to_dict(),
        }

    guard = assert_local_only(base_url, model)
    if not guard["ok"]:
        return {
            "ok": False,
            "paused": True,
            "refused": True,
            "fallback_used": False,
            "prompt_preserved": prompt,
            "message": guard["reason"],
            "local_only": guard,
        }

    # Native /api/chat (OpenClaw); map to legacy response field for callers.
    result = native_chat(
        base_url,
        model,
        [{"role": "user", "content": prompt}],
        timeout_s=timeout_s,
    )
    if not result.get("ok"):
        return {
            "ok": False,
            "paused": True,
            "fallback_used": False,
            "prompt_preserved": prompt,
            "message": result.get("message") or "Local chat failed; paused.",
            "eligibility": decision.to_dict(),
            "route": result.get("route"),
        }
    return {
        "ok": True,
        "paused": False,
        "provider": "ollama_local",
        "model": model,
        "response": result.get("content", ""),
        "route": result.get("route"),
        "openai_compat_used": False,
        "fallback_used": False,
        "eligibility": decision.to_dict(),
    }
