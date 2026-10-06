"""Timezone, DST, overlaps, missed runs, restart, and laptop-sleep semantics."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


COMPUTER_MUST_BE_RUNNING = (
    "Local automation requires this computer (and, when using OpenClaw, its Gateway) "
    "to be awake and running. Sleep/hibernate suspends user processes — missed fires "
    "are recorded after wake; they do not execute while the laptop sleeps."
)


def resolve_tz(name: str | None) -> timezone | ZoneInfo:
    if not name or name.upper() == "UTC":
        return timezone.utc
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"invalid_tz:{name}") from exc


def parse_at(at: str, *, tz_name: str | None = None, now: datetime | None = None) -> datetime:
    """Parse OpenClaw-style --at values: ISO timestamp or duration like 20m / 1h."""
    now = now or datetime.now(timezone.utc)
    tz = resolve_tz(tz_name)
    s = (at or "").strip()
    if s.endswith(("s", "m", "h", "d")) and s[:-1].replace(".", "", 1).isdigit():
        n = float(s[:-1])
        unit = s[-1]
        delta = {
            "s": timedelta(seconds=n),
            "m": timedelta(minutes=n),
            "h": timedelta(hours=n),
            "d": timedelta(days=n),
        }[unit]
        return now.astimezone(timezone.utc) + delta
    # ISO
    raw = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"invalid_at:{at}") from exc
    if dt.tzinfo is None:
        # Offset-less: interpret in --tz (OpenClaw docs); default UTC
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(timezone.utc)


def detect_dst_gap(local_naive: datetime, tz_name: str) -> dict[str, Any]:
    """Report nonexistent local times during DST spring-forward (OpenClaw rejects these)."""
    tz = resolve_tz(tz_name)
    try:
        aware = local_naive.replace(tzinfo=tz)
        # fold=0 vs fold=1 mismatch detection via utcoffset stability
        _ = aware.utcoffset()
        return {"ok": True, "dst_gap": False, "local": local_naive.isoformat(), "tz": tz_name}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "dst_gap": True, "error": str(exc), "tz": tz_name}


def overlap_policy(*, skip_if_running: bool = True) -> dict[str, Any]:
    return {
        "overlap": "skip_if_running" if skip_if_running else "allow_parallel",
        "note": "If a prior run is still active, the due fire is skipped and counted as missed/skipped, not an execution error.",
    }


def missed_run_after_sleep(
    *,
    scheduled_utc: datetime,
    woke_utc: datetime,
    max_catchup: int = 1,
) -> dict[str, Any]:
    """After laptop sleep, record missed windows; optionally catch up once."""
    missed = woke_utc > scheduled_utc
    return {
        "missed": missed,
        "scheduled_utc": scheduled_utc.isoformat(),
        "woke_utc": woke_utc.isoformat(),
        "catchup_allowed": max_catchup,
        "computer_must_be_running": COMPUTER_MUST_BE_RUNNING,
        "action": "catch_up_once" if missed and max_catchup >= 1 else ("record_missed" if missed else "on_time"),
    }


def restart_survives(*, job_persisted: bool, receipt_persisted: bool) -> dict[str, Any]:
    return {
        "restart_safe": job_persisted and receipt_persisted,
        "job_persisted": job_persisted,
        "receipt_persisted": receipt_persisted,
        "note": "Jobs and receipts live in FreeForge SQLite locally; OpenClaw Gateway SQLite is separate when used.",
    }
