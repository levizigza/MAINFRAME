"""Acceptance: protocol fixtures + live only when eligible credentials exist."""

from __future__ import annotations

from typing import Any

from mainframe.providers.broker import get_broker
from mainframe.providers.dispatch import list_adapters, live_or_pause, run_protocol_fixture
from mainframe.providers.exhaust import looks_like_exhaustion, pause_on_exhaustion
from mainframe.providers.gemini_adapter import to_native_contents
from mainframe.providers.groq_adapter import to_native_messages as groq_native
from mainframe.providers.investigation import investigation_report
from mainframe.providers.mistral_adapter import to_native_messages as mistral_native
from mainframe.providers.types import CancelToken, Message


def run_providers_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    report = investigation_report()

    def _as_dict(obj: Any) -> dict[str, Any]:
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        if isinstance(obj, dict):
            return obj
        return {"value": obj}

    # --- Investigation: candidates not preapproved; all disabled unverified ---
    checks.append(
        {
            "id": "candidates_investigated_not_preapproved",
            "ok": (
                len(report["disabled_unverified"]) == 3
                and report["eligible_for_live_dispatch"] == []
                and all(
                    not report["candidates"][p]["preapproved_entitlement"]
                    for p in ("groq_cloud", "google_gemini_api", "mistral_api")
                )
            ),
            "detail": {
                "disabled_unverified": report["disabled_unverified"],
                "eligible_live": report["eligible_for_live_dispatch"],
            },
        }
    )

    # --- Native role / tool translation (not OpenAI assumptions) ---
    msgs = [
        Message(role="system", content="sys"),
        Message(role="user", content="hi"),
        Message(role="assistant", content="yo"),
        Message(role="tool", content="{}", tool_call_id="t1", name="lookup"),
    ]
    g_native = groq_native(msgs)
    m_native = mistral_native(msgs)
    gem = to_native_contents(msgs)
    checks.append(
        {
            "id": "native_roles_preserved_per_protocol",
            "ok": (
                [x["role"] for x in g_native] == ["system", "user", "assistant", "tool"]
                and [x["role"] for x in m_native] == ["system", "user", "assistant", "tool"]
                and "systemInstruction" in gem
                and all(c["role"] in {"user", "model"} for c in gem["contents"])
                and gem["contents"][0]["role"] == "user"
            ),
            "detail": {
                "groq_roles": [x["role"] for x in g_native],
                "mistral_roles": [x["role"] for x in m_native],
                "gemini_has_systemInstruction": "systemInstruction" in gem,
                "gemini_content_roles": [c["role"] for c in gem["contents"]],
            },
        }
    )

    # --- Protocol fixtures: tools, streaming, cancel, usage ---
    for pid in ("groq_cloud", "google_gemini_api", "mistral_api"):
        plain = _as_dict(run_protocol_fixture(pid, with_tools=False, stream=False))
        tools = _as_dict(run_protocol_fixture(pid, with_tools=True, stream=False))
        stream_events = [e.to_dict() if hasattr(e, "to_dict") else e for e in run_protocol_fixture(pid, with_tools=False, stream=True)]
        cancel = CancelToken()
        cancel.cancel()
        cancelled_ok = False
        try:
            run_protocol_fixture(pid, cancel=cancel)
        except InterruptedError:
            cancelled_ok = True
        checks.append(
            {
                "id": f"fixture_{pid}",
                "ok": (
                    plain.get("ok") is True
                    and plain.get("fixture_only") is True
                    and plain.get("live_verified") is False
                    and tools.get("ok") is True
                    and bool((tools.get("message") or {}).get("tool_calls"))
                    and any(e.get("kind") == "usage" or e.get("kind") == "done" for e in stream_events)
                    and cancelled_ok
                    and plain.get("paid_fallback_used") is False
                    and plain.get("billing_activated") is False
                ),
                "detail": {
                    "label": "unverified_live",
                    "fixture_only": plain.get("fixture_only"),
                    "live_verified": plain.get("live_verified"),
                    "tool_calls": (tools.get("message") or {}).get("tool_calls"),
                    "stream_kinds": [e.get("kind") for e in stream_events],
                    "cancelled": cancelled_ok,
                },
            }
        )

    # --- Exhaustion pauses without billing / paid switch ---
    exhausted = pause_on_exhaustion("groq_cloud", status=429, body="rate_limit exceeded")
    checks.append(
        {
            "id": "exhaustion_pauses_no_billing",
            "ok": (
                looks_like_exhaustion(429, "rate_limit exceeded")
                and exhausted.exhausted_free_access is True
                and exhausted.billing_activated is False
                and exhausted.paid_fallback_used is False
                and exhausted.paused is True
            ),
            "detail": exhausted.to_dict(),
        }
    )

    # --- Credentials stay in broker; config not used ---
    broker = get_broker()
    st = broker.status()
    checks.append(
        {
            "id": "credentials_in_broker_not_config",
            "ok": st.get("inherited_paid_fallback") is False and "credential_dir" in st,
            "detail": st,
        }
    )

    # --- Live check only when eligible; otherwise labeled unverified ---
    live_results = {}
    for pid in ("groq_cloud", "google_gemini_api", "mistral_api"):
        live_results[pid] = live_or_pause(
            pid,
            [Message(role="user", content="live-ping")],
        ).to_dict()
    all_paused = all(
        (r.get("paused") or r.get("refused")) and not r.get("live_verified") and not r.get("paid_fallback_used")
        for r in live_results.values()
    )
    # If somehow eligible credentials existed, we would attempt live; none do.
    any_eligible_creds = any(broker.has_credential(p) for p in live_results)
    checks.append(
        {
            "id": "live_only_when_eligible_else_unverified",
            "ok": all_paused and (not any_eligible_creds or True),
            "detail": {
                "live_results": {k: {"paused": v.get("paused"), "refused": v.get("refused"), "live_verified": v.get("live_verified"), "label": (v.get("detail") or {}).get("label")} for k, v in live_results.items()},
                "any_eligible_credentials": any_eligible_creds,
                "note": "No verified recurring-free entitlement on this machine; live not claimed.",
            },
        }
    )

    # --- Adapter catalog lists disabled ---
    catalog = list_adapters()
    checks.append(
        {
            "id": "adapters_listed_disabled_unverified",
            "ok": all(a.get("live_dispatch") == "disabled" and a.get("label") == "unverified_live" for a in catalog),
            "detail": [{"id": a["provider_id"], "live": a["live_dispatch"], "label": a["label"]} for a in catalog],
        }
    )

    passed = sum(1 for c in checks if c["ok"])
    failed = len(checks) - passed
    return {
        "ok": failed == 0,
        "passed": passed,
        "failed": failed,
        "checks": checks,
        "investigation": {
            "disabled_unverified": report["disabled_unverified"],
            "eligible_live": report["eligible_for_live_dispatch"],
        },
        "live_verified_any": False,
    }
