"""OpenClaw v2026.9.6 automation command payload schema (documented).

Sources (observed 2026-09-29):
  https://docs.openclaw.ai/cli/cron
  https://docs.openclaw.ai/automation

Key facts from docs:
  - CLI registers as ``openclaw cron`` with alias ``openclaw automations``.
  - ``--command <str>`` stores argv ``["sh","-lc", <str>]`` (shell) — avoid on Windows.
  - ``--command-argv '<json-array>'`` is exact argv execution (preferred).
  - Command jobs run in the Gateway process and do **not** start an agent turn.
  - ``tools.exec.*`` / model-tool approvals do **not** govern scheduler command jobs.
  - Delivery: ``--announce`` / ``--webhook`` / ``--no-deliver`` (none).
"""

from __future__ import annotations

import json
from typing import Any

OPENCLAW_AUTOMATION_PIN = {
    "ref": "v2026.9.6",
    "commit": "eb377ac59e6c9fd6c7705028034812becf00271b",
    "docs": [
        "https://docs.openclaw.ai/cli/cron",
        "https://docs.openclaw.ai/automation",
    ],
    "cli_primary": "automations",
    "cli_alias": "cron",
}

# Sole scheduler owner — FreeForge must not invent a competing Gateway cron.
SCHEDULER_OWNER = "openclaw_gateway"

# FreeForge owns command cost/permission policy + workflow entry payloads.
COMMAND_POLICY_OWNER = "freeforge"


def prefer_argv_over_shell(command: str | None, argv: list[str] | None) -> dict[str, Any]:
    """Prefer exact argument arrays; refuse shell-interpolated strings when argv available."""
    if argv:
        if not isinstance(argv, list) or not all(isinstance(a, str) and a for a in argv):
            return {"ok": False, "error": "command_argv_must_be_nonempty_string_array"}
        return {
            "ok": True,
            "payload_kind": "command",
            "argv": list(argv),
            "shell_form": False,
            "windows_safe": True,
            "note": "Uses OpenClaw --command-argv exact array (preferred over --command).",
        }
    if command:
        return {
            "ok": False,
            "error": "shell_command_refused_prefer_command_argv",
            "detail": (
                "OpenClaw --command stores argv ['sh','-lc', <str>], which is fragile on Windows. "
                "Pass command_argv as a JSON string array instead."
            ),
            "would_store_as": ["sh", "-lc", command],
        }
    return {"ok": False, "error": "missing_command_or_argv"}


def build_command_payload(
    *,
    name: str,
    argv: list[str],
    cwd: str | None = None,
    schedule: dict[str, Any] | None = None,
    timeout_seconds: int | None = 120,
    delivery: str = "none",
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build an OpenClaw-compatible automation command job payload."""
    pref = prefer_argv_over_shell(None, argv)
    if not pref.get("ok"):
        return pref
    if delivery not in {"none", "announce", "webhook"}:
        return {"ok": False, "error": "invalid_delivery", "delivery": delivery}
    payload = {
        "ok": True,
        "format": "openclaw_automations_command_v2026_9_6",
        "scheduler_owner": SCHEDULER_OWNER,
        "command_policy_owner": COMMAND_POLICY_OWNER,
        "name": name,
        "payload": {
            "kind": "command",
            "argv": list(argv),
            "cwd": cwd,
            "env": dict(env or {}),
            "timeout_seconds": timeout_seconds,
        },
        "schedule": schedule or {"kind": "at", "at": "immediate"},
        "delivery": {
            "mode": delivery,
            # FreeForge default: no outbound channel/webhook unless explicitly set.
            "outbound_enabled": delivery != "none",
        },
        "execution": {
            "starts_agent_turn": False,
            "governed_by_model_tool_approvals": False,
            "note": (
                "Documented: command-payload runs execute directly in the Gateway process, "
                "not as an agent tools.exec tool call."
            ),
        },
        "openclaw_cli": openclaw_create_argv(
            name=name,
            argv=argv,
            cwd=cwd,
            schedule=schedule,
            timeout_seconds=timeout_seconds,
            delivery=delivery,
        ),
    }
    return payload


def openclaw_create_argv(
    *,
    name: str,
    argv: list[str],
    cwd: str | None,
    schedule: dict[str, Any] | None,
    timeout_seconds: int | None,
    delivery: str,
) -> list[str]:
    """Exact argv to invoke OpenClaw CLI (no shell interpolation)."""
    cmd = ["openclaw", "automations", "create"]
    sched = schedule or {"kind": "at", "at": "immediate"}
    kind = sched.get("kind")
    if kind == "cron":
        cmd.append(str(sched.get("cron") or "0 9 * * *"))
        if sched.get("tz"):
            cmd.extend(["--tz", str(sched["tz"])])
    elif kind == "every":
        cmd.extend(["--every", str(sched.get("every") or "1h")])
    elif kind == "at":
        at = sched.get("at") or "1m"
        if at != "immediate":
            cmd.extend(["--at", str(at)])
            if sched.get("tz"):
                cmd.extend(["--tz", str(sched["tz"])])
        else:
            # One-shot near-term for registration; local dispatcher also supports immediate fire.
            cmd.extend(["--at", "1m"])
    cmd.extend(["--name", name])
    cmd.extend(["--command-argv", json.dumps(argv, separators=(",", ":"))])
    if cwd:
        cmd.extend(["--command-cwd", cwd])
    if timeout_seconds is not None:
        cmd.extend(["--timeout-seconds", str(int(timeout_seconds))])
    if delivery == "none":
        cmd.append("--no-deliver")
    elif delivery == "announce":
        cmd.append("--announce")
    return cmd
