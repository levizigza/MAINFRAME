"""Static outbound request inventory — OpenClaw, coding engine, plugins, workers."""

from __future__ import annotations

from typing import Any

from mainframe.cost_gate import authorize
from mainframe.costaudit.boundary import gate_url, network_enforcement_status
from mainframe.dashboard.notify import notify_policy, refuse_openclaw_outbound
from mainframe.eligibility import DISABLED_PROVIDERS, ELIGIBLE_PROVIDERS
from mainframe.schedule.openclaw_payload import SCHEDULER_OWNER, build_command_payload


# Catalog of known outbound-capable paths in this tree (not a network sniffer).
OUTBOUND_PATHS: list[dict[str, Any]] = [
    {
        "component": "openclaw_scheduler",
        "owner": SCHEDULER_OWNER,
        "path": "schedule → openclaw --command-argv + --no-deliver",
        "default_destination": "none",
        "control": "freeforge_schedule_policy + --no-deliver",
        "may_reach_internet": False,
        "note": "Command jobs do not start agent turns; delivery defaults to none",
    },
    {
        "component": "openclaw_messaging",
        "owner": "dashboard.notify",
        "path": "announce/webhook channels",
        "default_destination": "disabled",
        "control": "refuse_openclaw_outbound until fee/connector/recipient/disclosure verified",
        "may_reach_internet": False,
    },
    {
        "component": "coding_engine",
        "owner": "local_model / ai / workflows.ai_runtime",
        "path": "loopback Ollama / llama.cpp only",
        "default_destination": "127.0.0.1",
        "control": "eligibility + cost_gate.authorize(inference)",
        "may_reach_internet": False,
    },
    {
        "component": "connectors_live",
        "owner": "connectors.http_client.LiveTransport",
        "path": "allowlisted free APIs (dog.ceo, open-meteo, frankfurter)",
        "default_destination": "fixture mode",
        "control": "host allowlist + costaudit.boundary.gate_url",
        "may_reach_internet": True,
        "note": "Live mode refused when OS network isolation unavailable",
    },
    {
        "component": "plugins_mcp",
        "owner": "tools.mcp_bridge",
        "path": "optional MCP registration",
        "default_destination": "none until fingerprint+fee re-eval",
        "control": "fee_or_permission_changed refuse",
        "may_reach_internet": False,
    },
    {
        "component": "workers_browser",
        "owner": "browser.session",
        "path": "local Chromium user-data profiles",
        "default_destination": "user-navigated URLs",
        "control": "per-project profile; submit_guard holds external posts",
        "may_reach_internet": True,
        "note": "Browser can reach internet if user/page navigates — not an OS jail",
    },
    {
        "component": "visual_bridge",
        "owner": "visual.server",
        "path": "loopback HTTP form",
        "default_destination": "127.0.0.1",
        "control": "loopback_only host check",
        "may_reach_internet": False,
    },
    {
        "component": "dashboard",
        "owner": "dashboard.server",
        "path": "loopback HTML + local inbox",
        "default_destination": "127.0.0.1 / .mainframe/notifications",
        "control": "loopback_only; OpenClaw notify refused",
        "may_reach_internet": False,
    },
]


def prove_controls() -> list[dict[str, Any]]:
    """Exercise gates that outbound paths must pass — real function calls."""
    proofs: list[dict[str, Any]] = []

    # Inference: hosted refused
    for pid in ("openai_api", "anthropic_api", "groq_cloud"):
        g = authorize("inference", pid, local=False)
        proofs.append(
            {
                "path": f"inference:{pid}",
                "passed_control": not g.allowed,
                "detail": g.to_dict() if hasattr(g, "to_dict") else str(g),
            }
        )

    # OpenClaw messaging refused
    refused = refuse_openclaw_outbound(destination="billing@example.com")
    proofs.append(
        {
            "path": "openclaw_messaging",
            "passed_control": bool(refused.get("refused")) and not refused.get("outbound_attempted"),
            "detail": refused,
        }
    )

    # Schedule payload prefers --no-deliver
    payload = build_command_payload(
        name="cost_audit_probe",
        argv=["python", "-m", "mainframe", "status"],
        delivery="none",
    )
    cli = payload.get("openclaw_cli") or []
    delivery = payload.get("delivery") or {}
    proofs.append(
        {
            "path": "openclaw_command_payload",
            "passed_control": bool(payload.get("ok"))
            and delivery.get("mode") == "none"
            and delivery.get("outbound_enabled") is False
            and "--no-deliver" in cli
            and payload.get("shell_form") is not True,
            "detail": {
                "ok": payload.get("ok"),
                "delivery": delivery,
                "has_no_deliver": "--no-deliver" in cli,
            },
        }
    )

    # Non-loopback live gate
    gated = gate_url("https://api.openai.com/v1/chat", purpose="cost_audit_probe")
    proofs.append(
        {
            "path": "non_loopback_live",
            "passed_control": gated.get("allowed") is False,
            "detail": gated,
        }
    )

    # Loopback allowed for local inference shape
    loop = gate_url("http://127.0.0.1:11434/api/chat", purpose="ollama_local")
    proofs.append(
        {
            "path": "loopback_inference",
            "passed_control": loop.get("allowed") is True,
            "detail": loop,
        }
    )

    # Notify policy
    pol = notify_policy()
    proofs.append(
        {
            "path": "notification_defaults",
            "passed_control": pol.get("automatic_outbound_delivery") is False
            and pol.get("openclaw_messaging_enabled") is False,
            "detail": pol,
        }
    )

    return proofs


def outbound_inventory() -> dict[str, Any]:
    return {
        "paths": OUTBOUND_PATHS,
        "network_enforcement": network_enforcement_status(),
        "eligible_inference": sorted(ELIGIBLE_PROVIDERS.keys()),
        "disabled_hosted": sorted(DISABLED_PROVIDERS.keys()),
        "control_proofs": prove_controls(),
        "limitation": (
            "This inventory is a code-path catalog plus gate proofs. It is not a kernel "
            "packet filter. Arbitrary OS processes with network rights are outside "
            "application policy."
        ),
    }
