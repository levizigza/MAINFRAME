"""Verify server protocol, chat template, tool support, and model license."""

from __future__ import annotations

from typing import Any

from mainframe.config import load_config
from mainframe.eligibility import sanitize_loopback_base
from mainframe.local_model.catalog import candidate_by_id
from mainframe.local_model.cloud_guard import assert_local_only
from mainframe.local_model.llamacpp import probe_llamacpp
from mainframe.local_model.ollama_native import (
    ADAPTER_META,
    NATIVE_CHAT,
    list_local_models,
    show_model,
)


def verify_protocol(
    *,
    base_url: str | None = None,
    model: str | None = None,
    also_probe_llamacpp: bool = True,
) -> dict[str, Any]:
    cfg = load_config()
    raw = base_url or str(cfg.get("ai", {}).get("ollama_base_url", "http://127.0.0.1:11434"))
    safe, rewritten = sanitize_loopback_base(raw)
    if rewritten:
        return {
            "ok": False,
            "available": False,
            "feature_status": "unavailable",
            "reason": "Non-loopback endpoint rejected; local-model feature unavailable.",
            "protocol": ADAPTER_META,
        }

    tags = list_local_models(safe, timeout_s=0.8)
    if not tags.get("available"):
        out: dict[str, Any] = {
            "ok": True,  # verification ran; feature may be unavailable
            "available": False,
            "feature_status": "unavailable",
            "reason": tags.get("reason") or "No local Ollama models on loopback.",
            "protocol": {
                **ADAPTER_META,
                "verified_routes": {
                    "tags": "/api/tags",
                    "show": "/api/show",
                    "chat": NATIVE_CHAT,
                    "openai_v1_used": False,
                },
            },
            "local_only": assert_local_only(safe),
            "ollama": tags,
            "frontier_parity_claimed": False,
        }
        if also_probe_llamacpp:
            out["llamacpp"] = probe_llamacpp()
            if out["llamacpp"].get("available"):
                out["available"] = True
                out["feature_status"] = "available_llamacpp"
        return out

    models = tags.get("models") or []
    chosen = model
    if not chosen:
        chosen = models[0]
    guard = assert_local_only(safe, chosen)
    if not guard["ok"]:
        return {
            "ok": False,
            "available": False,
            "feature_status": "unavailable",
            "reason": guard["reason"],
            "frontier_parity_claimed": False,
        }

    shown = show_model(safe, chosen)
    catalog = candidate_by_id(chosen) or candidate_by_id(chosen.split(":")[0])

    return {
        "ok": bool(shown.get("ok")),
        "available": True,
        "feature_status": "available",
        "endpoint": safe,
        "model": chosen,
        "protocol": {
            **ADAPTER_META,
            "server_protocol": "HTTP JSON — Ollama native API",
            "chat_route": NATIVE_CHAT,
            "openai_compat_used": False,
            "openclaw_doc": "https://docs.openclaw.ai/providers/ollama/",
        },
        "chat_template": shown.get("chat_template"),
        "tools": shown.get("tools"),
        "license": shown.get("license"),
        "catalog_hints": catalog,
        "cloud_models_excluded": tags.get("cloud_models_excluded") or [],
        "local_only": guard,
        "show": shown,
        "frontier_parity_claimed": False,
        "coding_quality_note": (
            "CPU availability and successful chat do not imply acceptable coding quality."
        ),
    }
