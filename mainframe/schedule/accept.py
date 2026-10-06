"""Acceptance: schedule local report, restart, verify receipt; zero model/outbound."""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from mainframe.schedule.cli_probe import probe_openclaw_automations_cli
from mainframe.schedule.dispatcher import fire_job
from mainframe.schedule.entry import schedule_local_report
from mainframe.schedule.instrument import assert_clean
from mainframe.schedule.openclaw_payload import (
    SCHEDULER_OWNER,
    prefer_argv_over_shell,
)
from mainframe.schedule.store import ScheduleStore
from mainframe.schedule.timing import (
    COMPUTER_MUST_BE_RUNNING,
    missed_run_after_sleep,
    overlap_policy,
    parse_at,
    restart_survives,
)


def run_schedule_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    tmp = Path(tempfile.mkdtemp(prefix="mf-sched-"))
    store = ScheduleStore(tmp / "schedule.sqlite")

    # Prefer argv arrays over shell
    shell_refuse = prefer_argv_over_shell("echo hi", None)
    argv_ok = prefer_argv_over_shell(None, ["python", "-c", "print(1)"])
    checks.append(
        {
            "id": "prefer_command_argv_over_shell",
            "ok": shell_refuse.get("ok") is False and argv_ok.get("ok") is True and argv_ok.get("windows_safe") is True,
            "detail": {"shell": shell_refuse.get("error"), "argv": argv_ok.get("argv")},
        }
    )

    probe = probe_openclaw_automations_cli()
    checks.append(
        {
            "id": "verify_installed_cli_or_document_deferred",
            "ok": (
                probe.get("command_argv_flag") == "--command-argv"
                and probe.get("pin", {}).get("ref") == "v2026.9.6"
                and (
                    (not probe.get("cli_present") and probe.get("status") == "deferred_openclaw_not_installed")
                    or (probe.get("cli_present") and probe.get("verified_live") is not None)
                )
            ),
            "detail": {
                "status": probe.get("status"),
                "cli_present": probe.get("cli_present"),
                "cli_version": probe.get("cli_version"),
                "flags": probe.get("flags_observed"),
            },
        }
    )

    checks.append(
        {
            "id": "one_scheduler_owner_openclaw",
            "ok": SCHEDULER_OWNER == "openclaw_gateway",
            "detail": {"scheduler_owner": SCHEDULER_OWNER},
        }
    )

    # Schedule local report
    scheduled = schedule_local_report(
        store,
        name="accept-local-report",
        title="Accept Scheduled Report",
        at="immediate",
        work_dir=tmp / "report_work",
    )
    job_id = (scheduled.get("job") or {}).get("job_id")
    checks.append(
        {
            "id": "schedule_local_report_payload",
            "ok": (
                scheduled.get("ok")
                and scheduled.get("starts_agent_turn") is False
                and scheduled.get("shell_form") is False
                and "--command-argv" in " ".join(scheduled.get("openclaw_cli_argv") or [])
                and "--no-deliver" in (scheduled.get("openclaw_cli_argv") or [])
            ),
            "detail": {
                "job_id": job_id,
                "cli_argv_tail": (scheduled.get("openclaw_cli_argv") or [])[-6:],
            },
        }
    )

    # Simulate restart: new store handle on same DB path
    store2 = ScheduleStore(tmp / "schedule.sqlite")
    job_after = store2.get_job(job_id) if job_id else None
    checks.append(
        {
            "id": "restart_reloads_job",
            "ok": bool(job_after) and job_after.get("name") == "accept-local-report",
            "detail": restart_survives(job_persisted=bool(job_after), receipt_persisted=False),
        }
    )

    # Fire deterministic command — no agent turn
    fired = fire_job(store2, job_id, force=True) if job_id else {"ok": False}
    receipt = fired.get("receipt") or {}
    instrument = receipt.get("instrument") or fired.get("instrument") or {}
    clean = assert_clean(instrument)
    report_path = tmp / "report_work" / "report.json"
    checks.append(
        {
            "id": "fire_and_verify_receipt",
            "ok": (
                fired.get("ok") is True
                and receipt.get("status") == "ok"
                and report_path.is_file()
                and clean.get("ok") is True
                and instrument.get("model_requests") == 0
                and instrument.get("outbound_delivery_attempted") is False
                and fired.get("starts_agent_turn") is False
            ),
            "detail": {
                "receipt_id": receipt.get("run_id"),
                "instrument": instrument,
                "report_exists": report_path.is_file(),
                "clean": clean,
            },
        }
    )

    # Receipt survives second "restart"
    store3 = ScheduleStore(tmp / "schedule.sqlite")
    receipts = store3.list_receipts(job_id) if job_id else []
    checks.append(
        {
            "id": "receipt_survives_restart",
            "ok": len(receipts) >= 1 and receipts[-1].get("status") == "ok",
            "detail": restart_survives(job_persisted=True, receipt_persisted=len(receipts) >= 1),
        }
    )

    # Timing / sleep / overlap documentation checks
    now = datetime.now(timezone.utc)
    missed = missed_run_after_sleep(
        scheduled_utc=now - timedelta(minutes=30),
        woke_utc=now,
    )
    checks.append(
        {
            "id": "sleep_missed_run_and_computer_must_run",
            "ok": (
                missed.get("missed") is True
                and COMPUTER_MUST_BE_RUNNING in missed.get("computer_must_be_running", "")
            ),
            "detail": missed,
        }
    )

    # DST / tz parse
    try:
        parsed = parse_at("20m")
        tz_ok = isinstance(parsed, datetime)
    except ValueError:
        tz_ok = False
    checks.append(
        {
            "id": "timezone_duration_parse",
            "ok": tz_ok,
            "detail": {"parsed": parsed.isoformat() if tz_ok else None},
        }
    )

    checks.append(
        {
            "id": "overlap_policy_skip_if_running",
            "ok": overlap_policy()["overlap"] == "skip_if_running",
            "detail": overlap_policy(),
        }
    )

    # Model-tool approvals do not govern
    checks.append(
        {
            "id": "command_not_governed_by_model_tool_approvals",
            "ok": instrument.get("governed_by_model_tool_approvals") is False,
            "detail": {"instrument_flag": instrument.get("governed_by_model_tool_approvals")},
        }
    )

    passed = sum(1 for c in checks if c["ok"])
    failed = len(checks) - passed
    return {
        "ok": failed == 0,
        "passed": passed,
        "failed": failed,
        "checks": checks,
        "computer_must_be_running": COMPUTER_MUST_BE_RUNNING,
    }
