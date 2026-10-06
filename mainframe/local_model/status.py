"""Unified local-model status — available or visibly unavailable."""

from __future__ import annotations

from typing import Any

from mainframe.config import load_config
from mainframe.eligibility import sanitize_loopback_base
from mainframe.local_model.llamacpp import probe_llamacpp
from mainframe.local_model.ollama_native import list_local_models
from mainframe.local_model.protocol import verify_protocol
from mainframe.local_model.select import select_candidate


def local_model_status() -> dict[str, Any]:
    cfg = load_config()
    ai = cfg.get("ai") or {}
    enabled = bool(ai.get("enabled", True))
    raw = str(ai.get("ollama_base_url", "http://127.0.0.1:11434"))
    safe, rewritten = sanitize_loopback_base(raw)

    if not enabled:
        return {
            "feature_status": "disabled_in_config",
            "available": False,
            "visible": True,
            "message": "AI disabled in config; no-local-model mode fully supported.",
            "no_local_model_supported": True,
            "frontier_parity_claimed": False,
        }

    ollama = list_local_models(safe, timeout_s=0.8)
    llama = probe_llamacpp(timeout_s=0.5)
    selection = select_candidate(base_url=safe)

    available = bool(ollama.get("available") or llama.get("available"))
    if rewritten:
        available = False

    if available:
        status = "available"
        message = "Eligible local model path responded on loopback."
    else:
        status = "unavailable"
        message = (
            "Local-model feature visibly unavailable "
            "(no loopback Ollama model / llama.cpp server). "
            "Deterministic automation remains usable; no cloud fallback."
        )

    return {
        "feature_status": status,
        "available": available,
        "visible": True,
        "message": message,
        "no_local_model_supported": True,
        "endpoint": safe,
        "endpoint_rewritten": rewritten,
        "ollama": ollama,
        "llamacpp": llama,
        "selection": selection,
        "protocol_summary": {
            "ollama_chat": "/api/chat",
            "openai_v1_used": False,
            "openclaw_aligned": True,
        },
        "frontier_parity_claimed": False,
        "coding_quality_assumed": False,
    }


def run_with_optional_model(prompt: str) -> dict[str, Any]:
    """Chat via selected local model or return visibly paused/unavailable."""
    from mainframe.local_model.ollama_native import chat

    st = local_model_status()
    if not st.get("available"):
        return {
            "ok": False,
            "paused": True,
            "feature_status": st["feature_status"],
            "message": st["message"],
            "prompt_preserved": prompt,
            "fallback_used": False,
            "no_local_model_supported": True,
        }
    sel = st.get("selection") or {}
    chosen = None
    if sel.get("selected") and sel["selected"].get("installed"):
        chosen = sel["selected"]["resolved_ollama_name"]
    models = (st.get("ollama") or {}).get("models") or []
    if not chosen and models:
        chosen = models[0]
    if not chosen:
        # llama.cpp path
        from mainframe.local_model.llamacpp import complete_llamacpp, DEFAULT_LLAMACPP_URL

        return complete_llamacpp(DEFAULT_LLAMACPP_URL, prompt)

    return chat(
        st["endpoint"],
        chosen,
        [{"role": "user", "content": prompt}],
    )
