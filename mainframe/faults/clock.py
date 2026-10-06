"""Clock-skew / wall-clock jump detection for schedule safety (deterministic fixtures)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def detect_clock_change(
    *,
    last_known_utc: datetime,
    observed_utc: datetime,
    max_forward_skew: timedelta = timedelta(hours=2),
    max_backward_skew: timedelta = timedelta(minutes=15),
) -> dict[str, Any]:
    """
    Detect abrupt wall-clock changes that could cause duplicate or skipped fires.
    Does not invent schedule execution — reports the anomaly for the scheduler owner.
    """
    if last_known_utc.tzinfo is None:
        last_known_utc = last_known_utc.replace(tzinfo=timezone.utc)
    if observed_utc.tzinfo is None:
        observed_utc = observed_utc.replace(tzinfo=timezone.utc)

    delta = observed_utc - last_known_utc
    forward = delta > max_forward_skew
    backward = delta < -max_backward_skew
    jumped = forward or backward
    return {
        "ok": not jumped,
        "clock_change_detected": jumped,
        "direction": "forward" if forward else ("backward" if backward else "stable"),
        "delta_seconds": delta.total_seconds(),
        "last_known_utc": last_known_utc.isoformat(),
        "observed_utc": observed_utc.isoformat(),
        "recovery": (
            "record_anomaly_defer_catchup_to_scheduler_owner"
            if jumped
            else "continue"
        ),
        "blind_fire_forbidden": jumped,
        "note": (
            "On clock jump, do not blindly re-fire due jobs; reconcile with last receipt "
            "and OpenClaw/FreeForge schedule owner."
        ),
    }
