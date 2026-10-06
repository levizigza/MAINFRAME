"""Retention controls — expire/list candidates; no false secure-erase claims."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from mainframe.projects.registry import get_project, project_home, update_retention


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def set_retention(project_id: str, *, retention_days: int | None) -> dict[str, Any]:
    """
    retention_days=None means retain until explicit delete.
    Does not claim cryptographic wipe of prior copies.
    """
    if retention_days is not None and retention_days < 0:
        return {"ok": False, "error": "invalid_retention_days"}
    return update_retention(project_id, retention_days=retention_days)


def list_retention_candidates(project_id: str, *, now: datetime | None = None) -> dict[str, Any]:
    rec = get_project(project_id)
    if not rec:
        return {"ok": False, "error": "project_not_found"}
    days = rec.get("retention_days")
    if days is None:
        return {
            "ok": True,
            "project_id": rec["project_id"],
            "retention_days": None,
            "candidates": [],
            "note": "No automatic retention expiry; explicit delete required.",
        }

    stamp = now or _utc()
    cutoff = stamp - timedelta(days=int(days))
    home = project_home(project_id)
    candidates: list[dict[str, Any]] = []
    for area in ("artifacts", "exports", "cache", "memory"):
        root = home / area
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            try:
                mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
            except OSError:
                continue
            if mtime < cutoff:
                candidates.append(
                    {
                        "path": str(p.relative_to(home)).replace("\\", "/"),
                        "area": area,
                        "mtime": mtime.isoformat(),
                    }
                )
    return {
        "ok": True,
        "project_id": rec["project_id"],
        "retention_days": days,
        "cutoff": cutoff.isoformat(),
        "candidates": candidates,
        "secure_erasure_guaranteed": False,
        "note": "Candidates listed for review; applying retention deletes files best-effort only.",
    }


def apply_retention(project_id: str, *, dry_run: bool = True) -> dict[str, Any]:
    listed = list_retention_candidates(project_id)
    if not listed.get("ok"):
        return listed
    home = project_home(project_id)
    removed: list[str] = []
    if not dry_run:
        for c in listed.get("candidates") or []:
            path = home / c["path"]
            try:
                path.unlink(missing_ok=True)  # type: ignore[call-arg]
                removed.append(c["path"])
            except TypeError:
                # Python <3.8 missing_ok — we are on modern Windows Python
                if path.is_file():
                    path.unlink()
                    removed.append(c["path"])
            except OSError:
                pass
    return {
        "ok": True,
        "dry_run": dry_run,
        "would_remove": [c["path"] for c in listed.get("candidates") or []],
        "removed": removed,
        "secure_erasure_guaranteed": False,
        "erasure_disclaimer": (
            "Deletion is best-effort unlink of project files FreeForge manages. "
            "This storage system cannot guarantee secure erasure against backups, "
            "shadow copies, SSD wear-leveling, or OneDrive/cloud replicas."
        ),
    }
