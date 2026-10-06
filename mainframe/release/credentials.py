"""Credential setup status for optional eligible APIs — refuse paid/hosted paths."""

from __future__ import annotations

from typing import Any

from mainframe.config import ensure_state
from mainframe.connectors import list_connectors
from mainframe.eligibility import ELIGIBLE_PROVIDERS
from mainframe.secretdata import get_facility


def credentials_status() -> dict[str, Any]:
    """
    Eligible connector APIs used by FreeForge are no-key read-only endpoints.
    Optional local secret facility (DPAPI) exists for future eligible adapters —
    hosted providers remain refused and must not receive stored credentials.
    """
    ensure_state()
    facility = get_facility()
    connectors = list_connectors()
    no_key = []
    key_optional = []
    for c in connectors:
        auth = (c.get("auth") if isinstance(c, dict) else {}) or {}
        kind = auth.get("kind") or auth.get("type") or "none"
        entry = {"id": c.get("connector_id") or c.get("id"), "auth_kind": kind}
        if kind in ("none", "no_key", ""):
            no_key.append(entry)
        else:
            key_optional.append(entry)

    return {
        "ok": True,
        "credentials_required_for_core": False,
        "eligible_inference_providers": sorted(ELIGIBLE_PROVIDERS),
        "eligible_inference_credentials": "none — loopback Ollama/llama.cpp; no API key",
        "connectors_no_key": no_key,
        "connectors_with_auth_fields": key_optional,
        "secret_facility": {
            "available": True,
            "mechanism_preferred": "windows_dpapi",
            "path_hint": ".mainframe/secrets/",
            "never_in_config_json": True,
        },
        "facility_status": facility.status() if hasattr(facility, "status") else str(type(facility)),
        "setup_steps": [
            "Core: no credentials to configure.",
            "Optional local model: install Ollama yourself; no MAINFRAME account.",
            "Optional secrets: use secretdata facility only for eligible local adapters.",
            "Hosted OpenAI/Anthropic/Groq/etc.: refused — do not store keys for them.",
        ],
        "paid_hosted_credential_setup": False,
    }
