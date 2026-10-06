"""Three explicit FreeForge operating modes + unavailable-route behavior."""

from __future__ import annotations

from typing import Any

from mainframe.eligibility import ELIGIBLE_PROVIDERS, DISABLED_PROVIDERS

MODE_DETERMINISTIC = "deterministic_offline"
MODE_CPU_AI = "deterministic_plus_optional_cpu_ai"
MODE_HOSTED_FREE = "deterministic_plus_eligible_free_hosted_ai"


def currently_eligible_hosted_ai() -> list[dict[str, Any]]:
    """
    Hosted providers that are both eligible in code and verified recurring-free.
    As of the cost audit / PROVIDERS investigation: **none**.
    """
    out: list[dict[str, Any]] = []
    for pid, meta in ELIGIBLE_PROVIDERS.items():
        if pid in ("ollama_local", "llamacpp_local"):
            continue
        # Any future non-local eligible provider would appear here
        out.append(
            {
                "provider_id": pid,
                "eligible_for_live": True,
                "purpose": meta.get("purpose"),
            }
        )
    return out


def build_modes(*, ollama_reachable: bool, llamacpp_reachable: bool = False) -> dict[str, Any]:
    hosted_live = currently_eligible_hosted_ai()
    local_ai_available = bool(ollama_reachable or llamacpp_reachable)

    modes = {
        MODE_DETERMINISTIC: {
            "id": MODE_DETERMINISTIC,
            "title": "Deterministic offline automation",
            "default_recommended": True,
            "requires": ["Python 3.11+", "local disk"],
            "inference": "none",
            "uses_ai": False,
            "behavior": (
                "Workflows, connectors (fixtures), docreport, coding harness patches, "
                "schedule fire, dashboard, project isolation — all run without models."
            ),
            "when_inference_unavailable": (
                "N/A — this mode never calls inference. AI steps are not scheduled."
            ),
            "optimize_for": "correct completed work per CPU/disk/time — not agent count or model size",
            "frontier_claim": False,
        },
        MODE_CPU_AI: {
            "id": MODE_CPU_AI,
            "title": "Core + optional CPU AI (loopback)",
            "default_recommended": False,
            "requires": [
                "Mode A core",
                "optional Ollama or llama.cpp on loopback",
                "installed local weights fitting measured RAM budget",
            ],
            "inference": "ollama_local | llamacpp_local",
            "uses_ai": True,
            "available_now": local_ai_available,
            "behavior": (
                "Same deterministic core. Typed AI steps / coding completion only when "
                "an eligible loopback model answers; quota ledger admits requests."
            ),
            "when_inference_unavailable": (
                "AI-dependent steps pause (checkpoint). Deterministic predecessors/siblings continue. "
                "No automatic paid or hosted fallback. Progress preserved."
            ),
            "observed_on_this_host": {
                "ollama_reachable": ollama_reachable,
                "llamacpp_reachable": llamacpp_reachable,
                "recommendation": (
                    "Keep Mode A as daily driver until a fitted local model is measured available."
                    if not local_ai_available
                    else "Local AI available — use for AI steps within quota; still prefer deterministic first."
                ),
            },
            "optimize_for": "correct completions within RAM/CPU budget — not largest parameter count",
            "frontier_claim": False,
        },
        MODE_HOSTED_FREE: {
            "id": MODE_HOSTED_FREE,
            "title": "Core + currently eligible free hosted AI",
            "default_recommended": False,
            "requires": [
                "Mode A core",
                "a provider with verified recurring-free entitlement (none today)",
            ],
            "inference": "eligible_free_hosted_only",
            "uses_ai": True,
            "available_now": len(hosted_live) > 0,
            "currently_eligible_providers": hosted_live,
            "investigated_not_eligible": [
                "groq_cloud",
                "google_gemini_api",
                "mistral_api",
            ],
            "behavior": (
                "Same deterministic core. Hosted inference activates only after verification "
                "in eligibility.py — marketing free tiers are not entitlements."
            ),
            "when_inference_unavailable": (
                "Today: always unavailable (zero verified hosted entitlements). "
                "Behavior: refuse hosted routes; pause AI steps; continue deterministic work; "
                "no trial/promo/billing activation; no silent switch to paid endpoints."
            ),
            "optimize_for": "correct work under verified free quotas — never unlimited frontier claims",
            "frontier_claim": False,
        },
    }

    recommended_id = MODE_DETERMINISTIC
    if local_ai_available:
        recommended_id = MODE_CPU_AI

    return {
        "modes": modes,
        "recommended_mode_id": recommended_id,
        "rationale": (
            "Optimize correct completed work per available resource. "
            "On this host local Ollama is paused/unreachable, so Mode A is recommended. "
            "Mode C has no currently eligible free hosted providers."
            if not local_ai_available
            else "Local loopback AI is reachable — Mode B recommended for AI-augmented steps; Mode A remains the offline baseline."
        ),
        "unavailable_route_contract": {
            "deterministic": "always proceeds",
            "cpu_ai": "pause AI step; no paid fallback",
            "hosted_free": "refuse unless entitlement verified; pause; no paid fallback",
            "disabled_providers": sorted(DISABLED_PROVIDERS.keys()),
        },
    }
