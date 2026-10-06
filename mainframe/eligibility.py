"""Strict free-only eligibility gate.

Nonqualifying providers are listed and refuse invocation — they are not
merely omitted from settings. Compatible local adapters pass only when
the endpoint is loopback and no credentials are required.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any
from urllib.parse import urlparse

# Hosts allowed for optional free local inference (no account, no hosted SaaS).
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

# Adapters that may run when the gate passes.
ELIGIBLE_PROVIDERS: dict[str, dict[str, str]] = {
    "ollama_local": {
        "purpose": "Optional local CPU/GPU inference via Ollama native /api/chat on loopback",
        "license": "Ollama MIT; model weights vary by model (verify via /api/show)",
        "cost_conditions": (
            "No account required for local use. Software is free. "
            "Models downloaded explicitly by the user; no MAINFRAME-required fee. "
            "Not required for core automation. Cloud/:cloud models refused."
        ),
        "replacement": "n/a (eligible)",
        "affected_behavior": (
            "ai probe / ai ask / local-model when loopback Ollama + local model present; "
            "OpenClaw-aligned native route (no /v1)"
        ),
    },
    "llamacpp_local": {
        "purpose": "Optional local llama.cpp server on loopback (/health, /completion)",
        "license": "MIT (llama.cpp); GGUF weight licenses vary",
        "cost_conditions": (
            "Optional; user-supplied GGUF; no MAINFRAME-required fee. "
            "Not required for core automation."
        ),
        "replacement": "n/a (eligible) or pause",
        "affected_behavior": "local-model status/bench when llama-server on loopback",
    },
}

# Explicitly nonqualifying — disabled in code, not just hidden from UI.
# Attempting to select these must refuse; there is no automatic fallback.
DISABLED_PROVIDERS: dict[str, dict[str, str]] = {
    "openai_api": {
        "purpose": "Hosted chat/completions",
        "license": "Proprietary service",
        "cost_conditions": "Paid account / API billing; free tiers are promotional/trial",
        "replacement": "ollama_local (optional) or pause AI steps",
        "affected_behavior": "No remote OpenAI calls; AI pauses if local unavailable",
    },
    "anthropic_api": {
        "purpose": "Hosted Claude API",
        "license": "Proprietary service",
        "cost_conditions": "Paid account / usage billing; trials excluded",
        "replacement": "ollama_local (optional) or pause AI steps",
        "affected_behavior": "Adapter refuses; no Anthropic fallback",
    },
    "azure_openai": {
        "purpose": "Proprietary hosted OpenAI on Azure",
        "license": "Proprietary / cloud contract",
        "cost_conditions": "Azure billing",
        "replacement": "ollama_local (optional) or pause",
        "affected_behavior": "Disabled; no cloud LLM route",
    },
    "google_gemini_api": {
        "purpose": "Hosted Gemini API (investigated candidate — not preapproved)",
        "license": "Proprietary service / Google AI terms",
        "cost_conditions": (
            "Free unpaid quota uses Unpaid Services data terms; Paid Tier requires "
            "Cloud Billing; auto tier upgrades. Unverifiable recurring free entitlement."
        ),
        "replacement": "ollama_local (optional) or pause",
        "affected_behavior": "Fixture adapter only; live disabled (unverified_live)",
    },
    "aws_bedrock": {
        "purpose": "Hosted foundation models",
        "license": "AWS proprietary service",
        "cost_conditions": "AWS account billing",
        "replacement": "ollama_local (optional) or pause",
        "affected_behavior": "Disabled",
    },
    "groq_cloud": {
        "purpose": "Hosted GroqCloud inference (investigated candidate — not preapproved)",
        "license": "Proprietary service",
        "cost_conditions": (
            "Rate limits with Developer plan upgrade path; published token prices. "
            "Unverifiable recurring free without billing dependency."
        ),
        "replacement": "ollama_local (optional) or pause",
        "affected_behavior": "Fixture adapter only; live disabled (unverified_live)",
    },
    "mistral_api": {
        "purpose": "Mistral La Plateforme API (investigated candidate — not preapproved)",
        "license": "Proprietary service / model licenses vary",
        "cost_conditions": (
            "Free mode for eval/prototype; pay-as-you-go extends usage and unlocks tiers. "
            "Unverifiable billing-independent recurring free access."
        ),
        "replacement": "ollama_local (optional) or pause",
        "affected_behavior": "Fixture adapter only; live disabled (unverified_live)",
    },
    "together_fireworks_replicate": {
        "purpose": "Hosted model marketplaces",
        "license": "Proprietary services",
        "cost_conditions": "Paid or trial credits",
        "replacement": "ollama_local (optional) or pause",
        "affected_behavior": "Disabled",
    },
    "hf_inference_api": {
        "purpose": "Hugging Face hosted inference",
        "license": "Service ToS; models vary",
        "cost_conditions": "Hosted endpoints may require paid plans / tokens",
        "replacement": "ollama_local with locally pulled weights",
        "affected_behavior": "Remote HF Inference API disabled; local weights via Ollama OK",
    },
    "cloud_databases": {
        "purpose": "Supabase / Firebase / Atlas / Neon / PlanetScale",
        "license": "Vendor proprietary SaaS",
        "cost_conditions": "Hosted DB; free tiers are promotional/limited",
        "replacement": "Local files under .mainframe/ (JSON, notes)",
        "affected_behavior": "No cloud DB clients; local state only",
    },
    "remote_execution": {
        "purpose": "Cloud CI runners / remote agents / hosted sandboxes",
        "license": "Vendor SaaS",
        "cost_conditions": "Often billed beyond free minutes",
        "replacement": "Local `python -m mainframe` on existing PC",
        "affected_behavior": "No remote execution hooks in core",
    },
    "analytics_telemetry": {
        "purpose": "Sentry / Segment / PostHog / Mixpanel / similar",
        "license": "Vendor SaaS",
        "cost_conditions": "Paid plans after trials",
        "replacement": "Local run logs in .mainframe/runs/",
        "affected_behavior": "No outbound analytics",
    },
    "hosted_search": {
        "purpose": "Algolia / Elastic Cloud / proprietary web search APIs",
        "license": "Vendor SaaS",
        "cost_conditions": "Paid or trial credits",
        "replacement": "Local workspace inspect / list-tree",
        "affected_behavior": "No hosted search clients",
    },
    "cloud_object_storage": {
        "purpose": "S3 / GCS / Azure Blob",
        "license": "Cloud vendor",
        "cost_conditions": "Storage + egress billing",
        "replacement": "Local filesystem under repo / .mainframe/",
        "affected_behavior": "No cloud storage SDKs",
    },
    "remote_vector_db": {
        "purpose": "Hosted vector databases / remote embedding search",
        "license": "Vendor SaaS",
        "cost_conditions": "Typically paid or trial credits",
        "replacement": "Local issue→code retrieve (exact + lexical ± measured FTS5)",
        "affected_behavior": "Not wired; retrieve refuses remote vectors",
    },
    "paid_embedding_api": {
        "purpose": "Cloud embedding endpoints",
        "license": "Vendor API",
        "cost_conditions": "Billed tokens / accounts",
        "replacement": "Exact identifiers/stack/error/import cues + optional local FTS5",
        "affected_behavior": "Not wired; no embedding client in retrieve",
    },
    "model_code_hypothesis": {
        "purpose": "LLM guesses treated as symbol/API facts",
        "license": "n/a",
        "cost_conditions": "Not a verified fact source",
        "replacement": "codeintel language_server_fact / parser_approximate / installed_api_fact",
        "affected_behavior": "codeintel never emits model_hypothesis evidence",
    },
}


@dataclass
class EligibilityDecision:
    eligible: bool
    provider_id: str
    reason: str
    endpoint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def is_loopback_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:  # noqa: BLE001
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").lower()
    return host in LOOPBACK_HOSTS


def sanitize_loopback_base(url: str, default: str = "http://127.0.0.1:11434") -> tuple[str, bool]:
    """Return (safe_url, was_rewritten). Non-loopback URLs are rejected, not used."""
    candidate = (url or default).rstrip("/")
    if is_loopback_url(candidate):
        return candidate, False
    return default.rstrip("/"), True


def decide_provider(provider_id: str, endpoint: str | None = None) -> EligibilityDecision:
    if provider_id in DISABLED_PROVIDERS:
        return EligibilityDecision(
            eligible=False,
            provider_id=provider_id,
            reason=(
                f"Provider '{provider_id}' is disabled under the free-only contract "
                f"({DISABLED_PROVIDERS[provider_id]['cost_conditions']}). "
                "No automatic paid/trial fallback."
            ),
            endpoint=endpoint,
        )
    if provider_id not in ELIGIBLE_PROVIDERS:
        return EligibilityDecision(
            eligible=False,
            provider_id=provider_id,
            reason=f"Unknown provider '{provider_id}' — refuse by default (fail closed).",
            endpoint=endpoint,
        )
    if endpoint is not None and not is_loopback_url(endpoint):
        return EligibilityDecision(
            eligible=False,
            provider_id=provider_id,
            reason=(
                f"Endpoint {endpoint!r} is not loopback. "
                "Remote/hosted inference is nonqualifying; refusing."
            ),
            endpoint=endpoint,
        )
    return EligibilityDecision(
        eligible=True,
        provider_id=provider_id,
        reason="Eligible: local free-only adapter on loopback; no credentials required.",
        endpoint=endpoint,
    )


def refuse_disabled(provider_id: str) -> dict[str, Any]:
    """Hard refuse for nonqualifying adapters (callable so routes are not merely hidden)."""
    decision = decide_provider(provider_id)
    return {
        "ok": False,
        "paused": True,
        "refused": True,
        "provider_id": provider_id,
        "eligibility": decision.to_dict(),
        "message": decision.reason,
        "fallback_used": False,
    }


def dependency_migration_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for pid, meta in ELIGIBLE_PROVIDERS.items():
        rows.append(
            {
                "component": pid,
                "status": "eligible",
                "purpose": meta["purpose"],
                "license": meta["license"],
                "cost_conditions": meta["cost_conditions"],
                "replacement": meta["replacement"],
                "affected_behavior": meta["affected_behavior"],
            }
        )
    for pid, meta in DISABLED_PROVIDERS.items():
        rows.append(
            {
                "component": pid,
                "status": "disabled",
                "purpose": meta["purpose"],
                "license": meta["license"],
                "cost_conditions": meta["cost_conditions"],
                "replacement": meta["replacement"],
                "affected_behavior": meta["affected_behavior"],
            }
        )
    # Core local components
    rows.extend(
        [
            {
                "component": "python_stdlib_cli",
                "status": "eligible",
                "purpose": "CLI, config, automation, inspect, accept",
                "license": "MIT (MAINFRAME) + Python PSF",
                "cost_conditions": "No fee; uses already-installed Python",
                "replacement": "n/a",
                "affected_behavior": "status/inspect/run/accept offline",
            },
            {
                "component": "local_state_files",
                "status": "eligible",
                "purpose": "Config, user notes, run logs under .mainframe/",
                "license": "User data + MIT code",
                "cost_conditions": "Local disk only",
                "replacement": "n/a (replaces cloud DB/storage)",
                "affected_behavior": "Persists without hosted services",
            },
            {
                "component": "pip_pypi_required_deps",
                "status": "disabled",
                "purpose": "Required third-party packages for core",
                "license": "n/a",
                "cost_conditions": "Core must not require paid or network installs",
                "replacement": "stdlib only for core paths",
                "affected_behavior": "No requirements.txt needed to launch",
            },
            {
                "component": "sqlite_fts5_local",
                "status": "eligible",
                "purpose": "Optional local FTS5 index for issue→code lexical search",
                "license": "SQLite (public domain)",
                "cost_conditions": "Free local; enabled only when accept measures improvement",
                "replacement": "n/a (exact/lexical path always available)",
                "affected_behavior": "retrieve may use FTS5 after measured ablation",
            },
            {
                "component": "issue_to_code_retrieval_local",
                "status": "eligible",
                "purpose": "Local issue→code retrieval with explainable signals",
                "license": "MIT (MAINFRAME)",
                "cost_conditions": "Local disk only; no embeddings required",
                "replacement": "n/a",
                "affected_behavior": "python -m mainframe retrieve search|accept",
            },
            {
                "component": "stdlib_ast_codeintel",
                "status": "eligible",
                "purpose": "Python symbol/caller/import analysis via ast",
                "license": "MIT + PSF",
                "cost_conditions": "Stdlib only; always available",
                "replacement": "n/a",
                "affected_behavior": "codeintel lookup/callers/imports without Jedi",
            },
            {
                "component": "jedi_optional",
                "status": "eligible",
                "purpose": "Optional goto/signatures when Jedi already installed",
                "license": "MIT",
                "cost_conditions": "Free local; not required to launch MAINFRAME",
                "replacement": "stdlib_ast_codeintel",
                "affected_behavior": "codeintel definition/signature when importable",
            },
            {
                "component": "pyright_optional",
                "status": "eligible",
                "purpose": "Optional diagnostics when pyright already available",
                "license": "Pyright license",
                "cost_conditions": "Free local; not required to launch",
                "replacement": "AST path without diagnostics",
                "affected_behavior": "codeintel diagnostics",
            },
        ]
    )
    return rows
