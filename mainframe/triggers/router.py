"""Route normalized events → bound jobs (one run per dedupe key)."""

from __future__ import annotations

from typing import Any

from mainframe.schedule.dispatcher import fire_job
from mainframe.schedule.store import ScheduleStore
from mainframe.triggers.bindings import resolve_binding_for_event
from mainframe.triggers.store import TriggerStore


def handle_event(
    trigger_store: TriggerStore,
    schedule_store: ScheduleStore,
    event: dict[str, Any],
    *,
    force_fire: bool = True,
) -> dict[str, Any]:
    """
    Deduplicate, resolve fixed binding → job_id, fire once.
    Events cannot select arbitrary commands.
    """
    resolved = resolve_binding_for_event(trigger_store, event)
    if not resolved.get("ok"):
        return {
            "ok": False,
            "ran": False,
            "reason": resolved.get("error"),
            "detail": resolved,
        }

    claim = trigger_store.claim_event(event)
    if claim.get("duplicate"):
        return {
            "ok": True,
            "ran": False,
            "reason": "duplicate_suppressed",
            "dedupe_key": claim.get("dedupe_key"),
            "prior_run_id": claim.get("prior_run_id"),
            "intended_runs": 0,
        }

    job_id = resolved["job_id"]
    fired = fire_job(schedule_store, job_id, force=force_fire)
    run_id = (fired.get("receipt") or {}).get("run_id")
    # Update claim with run_id if we stored null — optional; claim already inserted
    return {
        "ok": bool(fired.get("ok")),
        "ran": bool(fired.get("ok")),
        "reason": "fired" if fired.get("ok") else fired.get("status") or "fire_failed",
        "job_id": job_id,
        "binding_id": event.get("binding_id"),
        "dedupe_key": event.get("dedupe_key"),
        "run_id": run_id,
        "fire": fired,
        "intended_runs": 1 if fired.get("ok") else 0,
        "command_from_event": False,
    }
