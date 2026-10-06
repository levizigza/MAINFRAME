"""Dispatch deterministic OpenClaw command payloads without an agent turn."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.config import ROOT
from mainframe.cost_gate import scrub_env_for_child
from mainframe.schedule.instrument import assert_clean, new_instrument
from mainframe.schedule.policy import authorize_scheduler_command
from mainframe.schedule.store import ScheduleStore
from mainframe.schedule.timing import COMPUTER_MUST_BE_RUNNING, overlap_policy


def fire_job(
    store: ScheduleStore,
    job_id: str,
    *,
    force: bool = False,
) -> dict[str, Any]:
    job = store.get_job(job_id)
    if not job:
        return {"ok": False, "error": "unknown_job"}
    if not job.get("enabled") and not force:
        return {"ok": False, "error": "job_disabled"}

    payload = job.get("payload") or {}
    cmd = (payload.get("payload") or {}) if "payload" in payload else payload
    # Support both nested build_command_payload shape and flat
    inner = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
    argv = list((inner or {}).get("argv") or [])
    cwd = (inner or {}).get("cwd") or str(ROOT)
    delivery = (payload.get("delivery") or {}).get("mode") or "none"

    instrument = new_instrument(delivery_mode=delivery)
    instrument["computer_must_be_running"] = COMPUTER_MUST_BE_RUNNING
    instrument["scheduler_owner"] = job.get("scheduler_owner")

    if job.get("running"):
        pol = overlap_policy(skip_if_running=True)
        receipt = store.record_receipt(
            job_id=job_id,
            status="skipped",
            instrument={**instrument, "overlap": pol},
            error="overlap_skip_if_running",
        )
        return {"ok": True, "status": "skipped", "receipt": receipt, "overlap": pol}

    auth = authorize_scheduler_command(argv, local=True)
    if not auth.get("allowed"):
        receipt = store.record_receipt(
            job_id=job_id,
            status="denied",
            instrument=instrument,
            error=auth.get("reason"),
        )
        return {"ok": False, "status": "denied", "receipt": receipt, "auth": auth}

    store.set_running(job_id, True)
    try:
        # Exact argv — never shell=True (Windows-safe)
        proc = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=int((inner or {}).get("timeout_seconds") or 120),
            env=scrub_env_for_child(),
            shell=False,
        )
        result = {
            "exit_code": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-1000:],
            "stderr_tail": (proc.stderr or "")[-1000:],
            "argv": argv,
            "shell": False,
        }
        status = "ok" if proc.returncode == 0 else "error"
        # Delivery none — never attempt outbound
        if delivery != "none":
            instrument["outbound_delivery_attempted"] = True
            instrument["unintended_outbound"] = True
        clean = assert_clean(instrument)
        receipt = store.record_receipt(
            job_id=job_id,
            status=status,
            instrument=instrument,
            result={**result, "clean": clean},
            error=None if status == "ok" else f"exit:{proc.returncode}",
        )
        return {
            "ok": status == "ok",
            "status": status,
            "receipt": receipt,
            "instrument": instrument,
            "clean": clean,
            "starts_agent_turn": False,
        }
    except Exception as exc:  # noqa: BLE001
        receipt = store.record_receipt(
            job_id=job_id,
            status="error",
            instrument=instrument,
            error=f"{type(exc).__name__}: {exc}",
        )
        return {"ok": False, "status": "error", "receipt": receipt, "instrument": instrument}
    finally:
        store.set_running(job_id, False)


def due_jobs(store: ScheduleStore, *, now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    out = []
    for job in store.list_jobs():
        if not job.get("enabled"):
            continue
        nxt = job.get("next_run_at")
        if not nxt:
            continue
        try:
            when = datetime.fromisoformat(nxt.replace("Z", "+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            if when <= now:
                out.append(job)
        except ValueError:
            continue
    return out
