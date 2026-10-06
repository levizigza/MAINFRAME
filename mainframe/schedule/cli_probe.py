"""Verify installed OpenClaw CLI version and documented automation surface."""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any

from mainframe.schedule.openclaw_payload import OPENCLAW_AUTOMATION_PIN


def probe_openclaw_automations_cli() -> dict[str, Any]:
    """
    Inspect the installed OpenClaw binary (if any). Never invent availability.

    When absent, schema remains documentation-derived from the pinned release notes.
    """
    path = shutil.which("openclaw")
    out: dict[str, Any] = {
        "cli_present": bool(path),
        "cli_path": path,
        "cli_version": None,
        "pin": OPENCLAW_AUTOMATION_PIN,
        "subcommand_primary": "automations",
        "subcommand_alias": "cron",
        "command_argv_flag": "--command-argv",
        "command_shell_flag": "--command",
        "no_deliver_flag": "--no-deliver",
        "schema_source": "docs.openclaw.ai/cli/cron (pin v2026.9.6)",
        "verified_live": False,
        "gateway_required_for_mutations": True,
    }
    if not path:
        out["status"] = "deferred_openclaw_not_installed"
        out["detail"] = (
            "openclaw CLI absent — FreeForge builds documented payloads and can "
            "dispatch deterministic command argv locally; OpenClaw remains sole scheduler owner when installed."
        )
        return out

    try:
        ver = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=8,
            shell=False,
        )
        out["cli_version"] = (ver.stdout or ver.stderr or "").strip().splitlines()[0] if ver.returncode == 0 or ver.stdout or ver.stderr else None
    except Exception as exc:  # noqa: BLE001
        out["cli_version_error"] = f"{type(exc).__name__}: {exc}"

    # Prefer automations --help; fall back to cron --help (alias).
    help_text = ""
    for sub in ("automations", "cron"):
        try:
            h = subprocess.run(
                [path, sub, "--help"],
                capture_output=True,
                text=True,
                timeout=10,
                shell=False,
            )
            text = (h.stdout or "") + (h.stderr or "")
            if text.strip():
                help_text = text
                out["help_subcommand"] = sub
                break
        except Exception as exc:  # noqa: BLE001
            out[f"help_{sub}_error"] = f"{type(exc).__name__}: {exc}"

    flags = {
        "has_command_argv": "--command-argv" in help_text,
        "has_command": "--command" in help_text,
        "has_no_deliver": "--no-deliver" in help_text,
        "has_command_cwd": "--command-cwd" in help_text,
        "mentions_automations_or_cron": ("automation" in help_text.lower()) or ("cron" in help_text.lower()),
    }
    out["flags_observed"] = flags
    out["verified_live"] = bool(help_text.strip())
    out["status"] = "available" if out["verified_live"] else "present_but_help_unavailable"
    out["help_excerpt"] = help_text[:800] if help_text else None
    return out


def schema_summary_json() -> str:
    return json.dumps(probe_openclaw_automations_cli(), indent=2)
