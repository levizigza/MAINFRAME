"""Dispatch — fixtures always; live only when investigation + entitlement + broker allow."""

from __future__ import annotations

from typing import Any

from mainframe.cost_gate import authorize
from mainframe.eligibility import DISABLED_PROVIDERS
from mainframe.providers.broker import get_broker
from mainframe.providers.exhaust import refuse_disabled
from mainframe.providers import gemini_adapter, groq_adapter, mistral_adapter
from mainframe.providers.investigation import INVESTIGATIONS, is_live_allowed
from mainframe.providers.types import CancelToken, ChatResult, Message, ToolSpec

ADAPTERS = {
    "groq_cloud": groq_adapter,
    "google_gemini_api": gemini_adapter,
    "mistral_api": mistral_adapter,
}


def list_adapters() -> list[dict[str, Any]]:
    rows = []
    for pid, mod in ADAPTERS.items():
        inv = INVESTIGATIONS[pid]
        rows.append(
            {
                **mod.features(),
                "investigation_verdict": inv["verdict_reason"],
                "credential_present": get_broker().has_credential(pid),
                "in_disabled_providers": pid in DISABLED_PROVIDERS,
            }
        )
    return rows


def run_protocol_fixture(
    provider_id: str,
    *,
    with_tools: bool = False,
    stream: bool = False,
    cancel: CancelToken | None = None,
) -> Any:
    mod = ADAPTERS.get(provider_id)
    if not mod:
        return refuse_disabled(provider_id, "Unknown provider adapter.")
    messages = [
        Message(role="system", content="You are a test fixture."),
        Message(role="user", content="ping"),
    ]
    tools = None
    if with_tools:
        tools = [
            ToolSpec(
                name="lookup",
                description="Lookup a symbol",
                parameters={"type": "object", "properties": {"query": {"type": "string"}}},
            )
        ]
    return mod.run_fixture(messages, tools, stream=stream, cancel=cancel or CancelToken())


def live_or_pause(provider_id: str, messages: list[Message], **kwargs: Any) -> ChatResult:
    """
    Attempt live chat only when:
    - investigation marks live_dispatch enabled
    - cost_gate entitlement allows
    - credential exists in broker
    Otherwise pause/refuse — never paid fallback.
    """
    if provider_id not in ADAPTERS:
        return refuse_disabled(provider_id, "Unknown provider.")

    if not is_live_allowed(provider_id):
        # Still exercise refuse path; fixtures are separate.
        out = ADAPTERS[provider_id].live_chat(messages, **kwargs)
        out.detail = {
            **out.detail,
            "live_check_skipped": True,
            "reason": "investigation_disabled_unverified",
            "label": "unverified_live",
        }
        return out

    gate = authorize("inference", provider_id, local=False)
    if not gate.allowed:
        return refuse_disabled(
            provider_id,
            f"Cost gate denied live inference ({gate.denied_code}): {gate.reason}",
        )

    broker = get_broker()
    if not broker.has_credential(provider_id):
        return ChatResult(
            ok=False,
            provider_id=provider_id,
            paused=True,
            refused=False,
            live_verified=False,
            billing_activated=False,
            paid_fallback_used=False,
            detail={
                "message": "Eligible on paper but no credential in broker — paused.",
                "credentials_in_broker": False,
            },
        )

    # Investigation currently never enables live; this branch is for future verified access.
    return ADAPTERS[provider_id].live_chat(messages, **kwargs)


# Re-export ChatResult for typing convenience
from mainframe.providers.types import ChatResult as ChatResult  # noqa: E402
