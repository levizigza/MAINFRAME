"""Local backup and restore — filesystem only; no cloud storage."""

from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.config import ROOT, STATE_DIR, ensure_state

BACKUP_DIR = STATE_DIR / "backups"

# Paths under .mainframe worth preserving (relative). Secrets excluded by default.
DEFAULT_INCLUDE = (
    "config.json",
    "user_notes.md",
    "freeforge_schedule.sqlite",
    "freeforge_workflow_receipts.sqlite",
    "freeforge-cli.sqlite",
    "quota_ledger.sqlite",
    "workflows",
    "projects",
    "cache",
)

SECRET_GLOBS = ("secrets", "credentials")


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def create_backup(
    *,
    include_secrets: bool = False,
    dest_dir: Path | None = None,
) -> dict[str, Any]:
    ensure_state()
    out_root = dest_dir or BACKUP_DIR
    out_root.mkdir(parents=True, exist_ok=True)
    archive = out_root / f"mainframe-backup-{_utc_stamp()}.zip"
    included: list[str] = []
    skipped: list[str] = []

    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        meta = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "include_secrets": include_secrets,
            "root_name": ".mainframe",
        }
        zf.writestr("BACKUP_META.json", json.dumps(meta, indent=2) + "\n")
        for name in DEFAULT_INCLUDE:
            path = STATE_DIR / name
            if not path.exists():
                skipped.append(name)
                continue
            if path.is_file():
                arc = f".mainframe/{name}"
                zf.write(path, arcname=arc)
                included.append(arc)
            else:
                for f in path.rglob("*"):
                    if f.is_dir():
                        continue
                    rel = f.relative_to(STATE_DIR).as_posix()
                    if not include_secrets and any(s in rel.split("/") for s in SECRET_GLOBS):
                        skipped.append(rel)
                        continue
                    arc = f".mainframe/{rel}"
                    zf.write(f, arcname=arc)
                    included.append(arc)
        if include_secrets:
            for sname in SECRET_GLOBS:
                sp = STATE_DIR / sname
                if not sp.exists():
                    continue
                for f in sp.rglob("*"):
                    if f.is_file():
                        rel = f.relative_to(STATE_DIR).as_posix()
                        arc = f".mainframe/{rel}"
                        zf.write(f, arcname=arc)
                        included.append(arc)

    return {
        "ok": True,
        "archive": str(archive),
        "included_count": len(included),
        "skipped": skipped,
        "include_secrets": include_secrets,
        "cloud_storage": False,
    }


def restore_backup(archive: Path | str, *, dest_state: Path | None = None) -> dict[str, Any]:
    ensure_state()
    src = Path(archive)
    if not src.is_file():
        return {"ok": False, "error": "archive_not_found", "archive": str(src)}
    target = dest_state or STATE_DIR
    target.mkdir(parents=True, exist_ok=True)
    restored: list[str] = []
    with zipfile.ZipFile(src, "r") as zf:
        names = zf.namelist()
        if "BACKUP_META.json" not in names:
            return {"ok": False, "error": "missing_backup_meta"}
        for name in names:
            if name == "BACKUP_META.json" or name.endswith("/"):
                continue
            if not name.startswith(".mainframe/"):
                continue
            rel = name[len(".mainframe/") :]
            out = target / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(name) as rf, out.open("wb") as wf:
                shutil.copyfileobj(rf, wf)
            restored.append(rel)
    return {
        "ok": True,
        "archive": str(src),
        "restored_count": len(restored),
        "dest": str(target),
        "cloud_storage": False,
    }
