"""AI gateway — eligibility-gated, no paid/trial automatic fallbacks."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from mainframe.ai.ollama_adapter import generate_ollama, probe_ollama
from mainframe.ai.rejected import invoke_disabled, list_disabled_routes
from mainframe.config import load_config
from mainframe.cost_gate import authorize
from mainframe.eligibility import (
    ELIGIBLE_PROVIDERS,
    decide_provider,
    sanitize_loopback_base,
)


@dataclass
class AiProbeResult:
    status: str  # available | paused | disabled
    provider: str | None
    detail: str
    free_only: bool = True
    eligibility: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _active_base_url() -> tuple[str, bool]:
    cfg = load_config()
    raw = str(cfg.get("ai", {}).get("ollama_base_url", "http://127.0.0.1:11434"))
    return sanitize_loopback_base(raw)


def probe_free_inference(timeout_s: float = 1.5) -> AiProbeResult:
    """Probe eligible local inference only. Never invents availability."""
    cfg = load_config()
    ai = cfg.get("ai", {})
    if not ai.get("enabled", True):
        return AiProbeResult(
            status="disabled",
            provider=None,
            detail="AI disabled in config; deterministic automation remains usable.",
        )

    base, rewritten = _active_base_url()
    if rewritten:
        return AiProbeResult(
            status="paused",
            provider=None,
            detail=(
                "Configured AI endpoint was non-loopback and was rejected "
                "(hosted/remote inference is nonqualifying). "
                "No fallback used; deterministic automation remains usable."
            ),
            eligibility=decide_provider("ollama_local", str(ai.get("ollama_base_url"))).to_dict(),
        )

    raw = probe_ollama(base, timeout_s=timeout_s)
    return AiProbeResult(
        status=str(raw["status"]),
        provider=raw.get("provider"),
        detail=str(raw["detail"]),
        free_only=bool(raw.get("free_only", True)),
        eligibility=raw.get("eligibility"),
    )


def run_ai_step(prompt: str) -> dict[str, Any]:
    """
    Run eligible free local completion only.
    If unavailable: pause. Never call disabled/paid providers as fallback.
    """
    cfg = load_config()
    requested = str(cfg.get("ai", {}).get("provider", "ollama_local"))
    base_for_gate, _ = _active_base_url()

    gate = authorize(
        "inference",
        requested,
        endpoint=base_for_gate,
        local=requested in ELIGIBLE_PROVIDERS,
        model_alias=requested if requested not in ELIGIBLE_PROVIDERS else None,
    )
    if not gate.allowed:
        return {
            "ok": False,
            "paused": True,
            "refused": True,
            "fallback_used": False,
            "cost_gate": gate.to_dict(),
            "prompt_preserved": prompt,
            "message": gate.reason,
        }

    # Auxiliary / retry path must also pass the gate (same rules).
    aux = authorize(
        "inference",
        requested,
        endpoint=base_for_gate,
        local=True,
        nested=True,
        auxiliary_kind="completion_dispatch",
    )
    if not aux.allowed:
        return {
            "ok": False,
            "paused": True,
            "refused": True,
            "fallback_used": False,
            "cost_gate": aux.to_dict(),
            "prompt_preserved": prompt,
            "message": aux.reason,
        }

    # If someone points config at a disabled provider, refuse — do not swap to paid.
    if requested not in ELIGIBLE_PROVIDERS:
        refused = invoke_disabled(requested)
        refused["prompt_preserved"] = prompt
        refused["cost_gate"] = gate.to_dict()
        return refused

    probe = probe_free_inference()
    if probe.status != "available":
        return {
            "ok": False,
            "paused": True,
            "fallback_used": False,
            "probe": probe.to_dict(),
            "cost_gate": gate.to_dict(),
            "prompt_preserved": prompt,
            "message": "AI step paused; no paid/trial/hosted fallback used.",
        }

    base, rewritten = _active_base_url()
    if rewritten:
        return {
            "ok": False,
            "paused": True,
            "refused": True,
            "fallback_used": False,
            "prompt_preserved": prompt,
            "message": "Non-loopback endpoint rejected; no fallback.",
        }

    tags = probe_ollama(base, timeout_s=1.5)
    models = tags.get("models") or []
    if not models:
        return {
            "ok": False,
            "paused": True,
            "fallback_used": False,
            "probe": probe.to_dict(),
            "prompt_preserved": prompt,
            "message": "No local model to run; AI step paused.",
        }

    model_name = str(models[0])
    alias_gate = authorize(
        "inference",
        "ollama_local",
        endpoint=base,
        local=True,
        model_alias=model_name,
    )
    # Local ollama model ids are not paid aliases; if catalog name collides, still require local.
    if not alias_gate.allowed and alias_gate.denied_code == "paid_model_alias":
        return {
            "ok": False,
            "paused": True,
            "refused": True,
            "fallback_used": False,
            "cost_gate": alias_gate.to_dict(),
            "prompt_preserved": prompt,
            "message": alias_gate.reason,
        }

    return generate_ollama(base, prompt, model=model_name)

def provider_audit() -> dict[str, Any]:
    """Visible catalog: eligible retained adapters + disabled routes (not hidden)."""
    base, rewritten = _active_base_url()
    return {
        "eligible_adapters": ELIGIBLE_PROVIDERS,
        "disabled_routes": list_disabled_routes(),
        "active_endpoint": base,
        "endpoint_rewritten_from_non_loopback": rewritten,
        "auto_fallback_policy": "none — pause instead of paid/trial/hosted",
    }


# Public re-export for explicit refuse tests / future wiring
__all__ = [
    "AiProbeResult",
    "invoke_disabled",
    "probe_free_inference",
    "provider_audit",
    "run_ai_step",
]
