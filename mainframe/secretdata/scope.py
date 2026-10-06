"""Per-adapter credential scopes — each adapter gets only what it needs."""

from __future__ import annotations

from typing import Any

from mainframe.secretdata.facility import get_facility

# Adapter → allowed secret scopes (narrow).
ADAPTER_SCOPES: dict[str, list[str]] = {
    "ollama_local": [],  # no cloud credential
    "llamacpp_local": [],
    "openai_api": ["openai_api"],
    "anthropic_api": ["anthropic_api"],
    "google_gemini_api": ["google_gemini_api"],
    "groq_cloud": ["groq_cloud"],
    "mistral_api": ["mistral_api"],
    "generic_http": [],  # must not inherit model keys
    "mcp_bridge": [],
}


def scope_for_adapter(adapter_id: str) -> list[str]:
    return list(ADAPTER_SCOPES.get(adapter_id, []))


def credential_for_adapter(adapter_id: str, secret_id: str) -> dict[str, Any]:
    """
    Return a secret only if ``secret_id`` is in the adapter's required scope list.
    Adapters with empty scope never receive secrets.
    """
    scopes = scope_for_adapter(adapter_id)
    if not scopes:
        return {
            "ok": False,
            "error": "adapter_has_no_credential_scope",
            "adapter_id": adapter_id,
            "value": None,
        }
    if secret_id not in scopes:
        return {
            "ok": False,
            "error": "secret_outside_adapter_scope",
            "adapter_id": adapter_id,
            "secret_id": secret_id,
            "allowed_scopes": scopes,
            "value": None,
        }
    # requester_scope must match one of the secret's stored scopes; we store secrets
    # under the same id as scope name.
    return get_facility().get(secret_id, requester_scope=secret_id)
