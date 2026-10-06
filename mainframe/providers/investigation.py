"""Investigation of Groq / Gemini / Mistral as free-API candidates — not entitlements.

Official docs reviewed 2026-09-29. Verdicts are fail-closed for live dispatch until
a human records a current, non-promo, non-billing entitlement that still passes
``cost_gate.authorize`` (default: none).
"""

from __future__ import annotations

from typing import Any

# Sources consulted (URLs only — no marketing copy treated as entitlement).
SOURCES = {
    "groq_rate_limits": "https://console.groq.com/docs/rate-limits",
    "groq_models": "https://console.groq.com/docs/models",
    "gemini_billing": "https://ai.google.dev/gemini-api/docs/billing",
    "gemini_rate_limits": "https://ai.google.dev/gemini-api/docs/rate-limits",
    "gemini_terms": "https://ai.google.dev/gemini-api/terms",
    "gemini_pricing": "https://ai.google.dev/gemini-api/docs/pricing",
    "mistral_usage_limits": "https://docs.mistral.ai/admin/billing-usage/usage-limits",
    "mistral_models": "https://docs.mistral.ai/getting-started/models/",
    "mistral_free_tier_announce": "https://mistral.ai/news/september-24-release/",
}

INVESTIGATIONS: dict[str, dict[str, Any]] = {
    "groq_cloud": {
        "candidate": True,
        "preapproved_entitlement": False,
        "live_dispatch": "disabled",
        "live_verified": False,
        "label": "unverified_live",
        "account_eligibility": (
            "Requires GroqCloud account + API key. Free/rate-limited access historically "
            "exists alongside Developer plan upgrades for higher limits (official rate-limits doc)."
        ),
        "intended_use": "Hosted inference; rate limits documented per model/org.",
        "data_handling": (
            "Hosted third-party inference — prompts leave the machine. "
            "Enterprise/data terms not verified as zero-retention free for MAINFRAME workloads."
        ),
        "model_ids_examples": [
            "llama-3.1-8b-instant",
            "openai/gpt-oss-20b",
            "openai/gpt-oss-120b",
        ],
        "quotas": (
            "RPM/RPD/TPM/TPD headers; 429 on exceed. Higher limits via Developer plan upgrade "
            "(official docs)."
        ),
        "billing_requirements": (
            "Published per-token/hour prices on models page; upgrade path for higher limits. "
            "Cannot verify recurring free access that is non-promotional and billing-independent."
        ),
        "protocol_notes": {
            "shape": "OpenAI-compatible Chat Completions surface at api.groq.com/openai/v1",
            "assume_full_openai_parity": False,
            "supports_tools": "partial — translate only documented tool_calls",
            "supports_streaming": True,
            "native_roles": ["system", "user", "assistant", "tool"],
        },
        "verdict_reason": (
            "Unverifiable as recurring free without billing/upgrade dependency under "
            "MAINFRAME cost posture — disabled for live; fixtures only."
        ),
        "sources": ["groq_rate_limits", "groq_models"],
    },
    "google_gemini_api": {
        "candidate": True,
        "preapproved_entitlement": False,
        "live_dispatch": "disabled",
        "live_verified": False,
        "label": "unverified_live",
        "account_eligibility": (
            "Google AI Studio / Gemini API project; Free Tier for unpaid quota; "
            "Paid Tier when Cloud Billing is linked (official billing docs)."
        ),
        "intended_use": "Prototyping on Free Tier; production-scale on Paid Tier.",
        "data_handling": (
            "Unpaid Services: Google may use submitted content to improve products "
            "(Gemini API Additional Terms). Paid Services: different data terms. "
            "Free-tier data use is incompatible with assuming private local processing."
        ),
        "model_ids_examples": [
            "gemini-2.0-flash",
            "gemini-2.5-flash",
            "gemini-1.5-flash",
        ],
        "quotas": "RPM/TPM by model and usage tier; Free Tier N/A spend cap; view in AI Studio.",
        "billing_requirements": (
            "Free Tier → Tier 1 requires linking an active billing account. "
            "Automatic tier upgrades with spend. Not billing-independent recurring free."
        ),
        "protocol_notes": {
            "shape": "Native generateContent / streamGenerateContent (not OpenAI messages)",
            "assume_full_openai_parity": False,
            "supports_tools": "functionDeclarations → functionCall parts",
            "supports_streaming": True,
            "native_roles": ["user", "model"],  # system via systemInstruction
        },
        "verdict_reason": (
            "Free unpaid quota exists but is promotional/capped, uses unpaid data terms, "
            "and billing unlock upgrades limits — disabled for live; fixtures only."
        ),
        "sources": [
            "gemini_billing",
            "gemini_rate_limits",
            "gemini_terms",
            "gemini_pricing",
        ],
    },
    "mistral_api": {
        "candidate": True,
        "preapproved_entitlement": False,
        "live_dispatch": "disabled",
        "live_verified": False,
        "label": "unverified_live",
        "account_eligibility": (
            "La Plateforme account; Free mode creates keys with included monthly usage "
            "(official usage/limits docs). Pay-as-you-go extends beyond included usage."
        ),
        "intended_use": "Evaluation / prototyping on Free mode; higher tiers via pay-as-you-go.",
        "data_handling": (
            "Commercial tier advertises data isolation / zero-retention options; "
            "free-tier isolation not verified for MAINFRAME as default."
        ),
        "model_ids_examples": [
            "mistral-small-latest",
            "mistral-medium-2508",
            "open-mistral-nemo",
            "codestral-latest",
        ],
        "quotas": "Per-model TPM/RPS on Admin Limits page; Free mode has lowest limits.",
        "billing_requirements": (
            "Free mode included usage; pay-as-you-go unlocks Tier 1+ and extends usage. "
            "Automatic tier upgrades tied to cumulative billed amount — not billing-independent."
        ),
        "protocol_notes": {
            "shape": "Chat Completions-style /v1/chat/completions with Mistral tool schema",
            "assume_full_openai_parity": False,
            "supports_tools": True,
            "supports_streaming": True,
            "native_roles": ["system", "user", "assistant", "tool"],
        },
        "verdict_reason": (
            "Free mode is eval/prototype oriented with pay-as-you-go upgrade path — "
            "unverifiable recurring free entitlement; disabled for live; fixtures only."
        ),
        "sources": [
            "mistral_usage_limits",
            "mistral_models",
            "mistral_free_tier_announce",
        ],
    },
}


def investigation_report() -> dict[str, Any]:
    return {
        "investigated_at_note": "2026-09-29 — candidates only, not preapproved entitlements",
        "sources": SOURCES,
        "candidates": INVESTIGATIONS,
        "eligible_for_live_dispatch": [
            pid for pid, meta in INVESTIGATIONS.items() if meta.get("live_dispatch") == "enabled"
        ],
        "disabled_unverified": [
            pid for pid, meta in INVESTIGATIONS.items() if meta.get("live_dispatch") == "disabled"
        ],
        "policy": (
            "Only currently verified recurring free API access may go live. "
            "Marketing free tiers / unpaid quotas with billing upgrade paths stay disabled."
        ),
    }


def is_live_allowed(provider_id: str) -> bool:
    meta = INVESTIGATIONS.get(provider_id)
    return bool(meta and meta.get("live_dispatch") == "enabled")
