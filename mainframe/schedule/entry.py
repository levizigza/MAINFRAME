"""FreeForge workflow entry → OpenClaw automation command payload."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.config import ROOT
from mainframe.schedule.cli_probe import probe_openclaw_automations_cli
from mainframe.schedule.openclaw_payload import (
    SCHEDULER_OWNER,
    build_command_payload,
    prefer_argv_over_shell,
)
from mainframe.schedule.policy import authorize_scheduler_command
from mainframe.schedule.store import ScheduleStore
from mainframe.schedule.timing import COMPUTER_MUST_BE_RUNNING, parse_at


def schedule_local_report(
    store: ScheduleStore,
    *,
    name: str = "local-report",
    title: str = "Scheduled local report",
    at: str = "immediate",
    tz: str | None = None,
    work_dir: Path | None = None,
) -> dict[str, Any]:
    """
    Schedule a deterministic local report via OpenClaw-compatible command-argv.

    Does not start an agent turn. Delivery defaults to none (no outbound).
    """
    work = work_dir or (ROOT / ".mainframe" / "schedule_work" / "local_report")
    work.mkdir(parents=True, exist_ok=True)
    # Exact argv array — never a shell-interpolated string
    argv = [
        sys.executable,
        "-m",
        "mainframe",
        "automation-report",
        "--title",
        title,
        "--out",
        str(work / "report.json"),
    ]
    pref = prefer_argv_over_shell(None, argv)
    if not pref.get("ok"):
        return pref

    auth = authorize_scheduler_command(argv, local=True)
    if not auth.get("allowed"):
        return {"ok": False, "error": "cost_policy_denied", "auth": auth}

    if at == "immediate":
        next_run = datetime.now(timezone.utc).isoformat()
        schedule = {"kind": "at", "at": "immediate"}
    else:
        when = parse_at(at, tz_name=tz)
        next_run = when.isoformat()
        schedule = {"kind": "at", "at": at, "tz": tz}

    built = build_command_payload(
        name=name,
        argv=argv,
        cwd=str(ROOT),
        schedule=schedule,
        timeout_seconds=120,
        delivery="none",
    )
    if not built.get("ok"):
        return built

    job = store.upsert_job(name=name, payload=built, next_run_at=next_run)
    probe = probe_openclaw_automations_cli()
    return {
        "ok": True,
        "job": job,
        "openclaw_cli_argv": built.get("openclaw_cli"),
        "openclaw_probe": {
            "status": probe.get("status"),
            "cli_present": probe.get("cli_present"),
            "verified_live": probe.get("verified_live"),
            "cli_version": probe.get("cli_version"),
        },
        "scheduler_owner": SCHEDULER_OWNER,
        "local_dispatcher": "freeforge_deterministic_command_runner",
        "computer_must_be_running": COMPUTER_MUST_BE_RUNNING,
        "starts_agent_turn": False,
        "shell_form": False,
        "auth": auth,
    }
