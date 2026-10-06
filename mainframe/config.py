"""Paths, cost posture, and local state — stdlib only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mainframe.eligibility import sanitize_loopback_base, ELIGIBLE_PROVIDERS

# Repo root: .../MAINFRAME (parent of package)
ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / ".mainframe"
CONFIG_PATH = STATE_DIR / "config.json"
RUNS_DIR = STATE_DIR / "runs"
USER_NOTES = STATE_DIR / "user_notes.md"

COST_POSTURE = {
    "required_fees": False,
    "required_api_keys": False,
    "required_subscriptions": False,
    "required_hosting": False,
    "required_gpu": False,
    "paid_accounts_allowed": False,
    "trials_allowed": False,
    "promotional_credits_allowed": False,
    "paid_fallbacks_allowed": False,
    "hosted_engines_allowed": False,
    "cloud_databases_allowed": False,
    "remote_execution_allowed": False,
    "analytics_allowed": False,
    "hosted_search_allowed": False,
    "cloud_storage_allowed": False,
    "local_llm_required": False,
    "deterministic_without_ai": True,
}

# Keys that must never remain true after load (fail closed).
_FORCE_FALSE = (
    "required_fees",
    "paid_accounts_allowed",
    "trials_allowed",
    "promotional_credits_allowed",
    "paid_fallbacks_allowed",
    "hosted_engines_allowed",
    "cloud_databases_allowed",
    "remote_execution_allowed",
    "analytics_allowed",
    "hosted_search_allowed",
    "cloud_storage_allowed",
)


def _mkdirs() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / "cache").mkdir(exist_ok=True)
    (STATE_DIR / "tmp").mkdir(exist_ok=True)


def _write_config(data: dict[str, Any]) -> None:
    _mkdirs()
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def ensure_state() -> None:
    """Create local state dirs without touching existing user notes content."""
    _mkdirs()
    if not USER_NOTES.exists():
        USER_NOTES.write_text(
            "# User notes\n\nPreserved across MAINFRAME increments. Edit freely.\n",
            encoding="utf-8",
        )
    if not CONFIG_PATH.exists():
        _write_config(default_config())


def default_config() -> dict[str, Any]:
    return {
        "cost_posture": dict(COST_POSTURE),
        "ai": {
            "enabled": True,
            "mode": "optional_free_only",
            "provider": "ollama_local",
            "ollama_base_url": "http://127.0.0.1:11434",
            "pause_when_unavailable": True,
            # Disabled providers are not selectable; listed for audit visibility only.
            "disabled_providers_note": "See python -m mainframe audit — cannot enable paid routes via config",
        },
        "automation": {
            "require_ai": False,
        },
    }


def _enforce_free_only(data: dict[str, Any]) -> dict[str, Any]:
    """Strip nonqualifying config; do not leave paid routes activatable via JSON."""
    data["cost_posture"] = {**COST_POSTURE, **data.get("cost_posture", {})}
    for key in _FORCE_FALSE:
        data["cost_posture"][key] = False
    data["cost_posture"]["local_llm_required"] = False
    data["cost_posture"]["deterministic_without_ai"] = True

    ai = dict(data.get("ai") or {})
    provider = str(ai.get("provider", "ollama_local"))
    if provider not in ELIGIBLE_PROVIDERS:
        # Do not keep a nonqualifying provider as the active route.
        ai["provider_refused"] = provider
        ai["provider"] = "ollama_local"
    else:
        ai["provider"] = provider
        ai.pop("provider_refused", None)

    raw_url = str(ai.get("ollama_base_url", "http://127.0.0.1:11434"))
    safe_url, rewritten = sanitize_loopback_base(raw_url)
    if rewritten:
        ai["ollama_base_url_rejected"] = raw_url
    else:
        ai.pop("ollama_base_url_rejected", None)
    ai["ollama_base_url"] = safe_url
    ai["mode"] = "optional_free_only"
    ai["pause_when_unavailable"] = True
    # Remove any credential-shaped keys so launch never depends on them.
    for secret_key in (
        "api_key",
        "api_keys",
        "openai_api_key",
        "anthropic_api_key",
        "bearer_token",
        "access_token",
        "cloud_project",
    ):
        ai.pop(secret_key, None)
    data["ai"] = ai

    automation = dict(data.get("automation") or {})
    automation["require_ai"] = False
    data["automation"] = automation
    return data


def load_config() -> dict[str, Any]:
    ensure_state()
    with CONFIG_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    return _enforce_free_only(data)


def save_config(data: dict[str, Any]) -> None:
    _write_config(_enforce_free_only(data))
