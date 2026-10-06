"""Surfaces audited for hidden paid dependencies."""

from __future__ import annotations

from typing import Any

# Each surface: what we check, free_only contract, physical vs fee distinction
SURFACES: list[dict[str, Any]] = [
    {
        "id": "installation",
        "checks": ["pip_required", "node_required_for_core", "account_signup"],
        "expected": "stdlib Python launch; no required pip/paid install",
    },
    {
        "id": "runtime",
        "checks": ["hosted_runtime", "cloud_minutes", "remote_exec"],
        "expected": "local python -m mainframe only",
    },
    {
        "id": "inference",
        "checks": ["hosted_llm", "auto_fallback_paid", "trial_unlock"],
        "expected": "loopback Ollama/llama.cpp optional; else pause",
    },
    {
        "id": "search",
        "checks": ["hosted_search", "paid_embeddings", "remote_vector_db"],
        "expected": "local retrieve / inspect only",
    },
    {
        "id": "models",
        "checks": ["cloud_model_aliases", "auto_pull_billing", "colon_cloud"],
        "expected": "explicit local pull; :cloud refused",
    },
    {
        "id": "plugins",
        "checks": ["marketplace_fees", "auto_install_network", "mcp_paid"],
        "expected": "no required paid plugins; MCP fee/permission re-eval",
    },
    {
        "id": "browser_use",
        "checks": ["cloud_browser", "hosted_playwright"],
        "expected": "local Playwright/Chromium optional",
    },
    {
        "id": "storage",
        "checks": ["cloud_db", "object_storage", "hosted_cache"],
        "expected": ".mainframe/ local files + SQLite",
    },
    {
        "id": "notifications",
        "checks": ["openclaw_announce_auto", "paid_webhook", "sms"],
        "expected": "local inbox default; OpenClaw deliver gated/--no-deliver",
    },
    {
        "id": "backups",
        "checks": ["cloud_backup_saas"],
        "expected": "no required hosted backup product",
    },
    {
        "id": "ci",
        "checks": ["hosted_ci_minutes", "required_github_actions_billing"],
        "expected": "local accept/faults; no required hosted CI",
    },
    {
        "id": "distribution",
        "checks": ["app_store_fees", "paid_installer"],
        "expected": "source tree + MIT; no paid distribution required",
    },
]


PHYSICAL_RESOURCES = (
    "electricity",
    "local_cpu_gpu_time",
    "local_disk",
    "local_ram",
    "user_internet_for_optional_free_apis",
    "optional_model_download_bandwidth",
)

ZERO_FEE_CLAIMS = (
    "no_required_software_subscription",
    "no_required_api_key_purchase",
    "no_required_hosted_runtime",
    "no_required_trial_or_promotional_credit",
    "no_automatic_paid_fallback",
)
