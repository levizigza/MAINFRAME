"""Explicit, removable startup scheduling — local job always; OS logon when permitted."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from mainframe.config import STATE_DIR, ensure_state
from mainframe.schedule.openclaw_payload import build_command_payload
from mainframe.schedule.store import ScheduleStore

TASK_NAME = "MAINFRAME-LocalStatus"
LOCAL_JOB_ID = "startup_local_status"
MARKER = "startup_schedule.json"


def _marker_path() -> Path:
    return STATE_DIR / MARKER


def _schtasks(args: list[str], timeout: float = 30.0) -> dict[str, Any]:
    if sys.platform != "win32":
        return {"ok": False, "error": "not_windows", "stdout": "", "stderr": ""}
    try:
        p = subprocess.run(
            ["schtasks"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "ok": p.returncode == 0,
            "exit_code": p.returncode,
            "stdout": (p.stdout or "").strip(),
            "stderr": (p.stderr or "").strip(),
        }
    except FileNotFoundError:
        return {"ok": False, "error": "schtasks_not_found", "stdout": "", "stderr": ""}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout", "stdout": "", "stderr": ""}


def _local_status() -> dict[str, Any]:
    ensure_state()
    store = ScheduleStore()
    job = store.get_job(LOCAL_JOB_ID)
    marker = _marker_path()
    return {
        "registered": job is not None and bool(job.get("enabled")),
        "job": job,
        "marker_present": marker.is_file(),
        "marker": json.loads(marker.read_text(encoding="utf-8")) if marker.is_file() else None,
    }


def startup_status() -> dict[str, Any]:
    local = _local_status()
    os_q = _schtasks(["/Query", "/TN", TASK_NAME, "/V", "/FO", "LIST"])
    return {
        "task_name": TASK_NAME,
        "local_job_id": LOCAL_JOB_ID,
        "local_registered": local["registered"],
        "os_logon_registered": bool(os_q.get("ok")),
        "registered": local["registered"] or bool(os_q.get("ok")),
        "local": local,
        "os_query": os_q,
        "auto_enabled_by_install": False,
        "removable": True,
        "mechanism": "freeforge_schedule_job_plus_optional_schtasks",
    }


def startup_register(*, confirm: bool, python_exe: str | None = None) -> dict[str, Any]:
    if not confirm:
        return {
            "ok": False,
            "error": "confirm_required",
            "hint": "Pass --confirm; startup registration is never implicit.",
        }
    ensure_state()
    exe = python_exe or sys.executable
    payload = build_command_payload(
        name="startup_local_status",
        argv=[exe, "-m", "mainframe", "status"],
        delivery="none",
    )
    if not payload.get("ok", True) and payload.get("error"):
        return {"ok": False, "error": "payload_build_failed", "payload": payload}
    store = ScheduleStore()
    job = store.upsert_job(
        name="startup_local_status",
        payload=payload,
        next_run_at=None,
        job_id=LOCAL_JOB_ID,
    )
    marker = {
        "enabled": True,
        "job_id": LOCAL_JOB_ID,
        "explicit_confirm": True,
        "os_logon_attempted": sys.platform == "win32",
        "command": [exe, "-m", "mainframe", "status"],
        "note": "Install never enables this; remove with startup-remove.",
    }

    os_result: dict[str, Any] = {"attempted": False}
    if sys.platform == "win32":
        tr = f'"{exe}" -m mainframe status'
        create = _schtasks(
            [
                "/Create",
                "/TN",
                TASK_NAME,
                "/TR",
                tr,
                "/SC",
                "ONLOGON",
                "/RL",
                "LIMITED",
                "/F",
            ]
        )
        os_result = {
            "attempted": True,
            "ok": bool(create.get("ok")),
            "create": create,
            "access_denied": "Access is denied" in (create.get("stderr") or ""),
        }
        marker["os_logon_ok"] = os_result["ok"]
        marker["os_logon_error"] = create.get("stderr") or create.get("error")
        if os_result.get("access_denied"):
            marker["os_logon_label"] = "DOCUMENTED_NOT_TESTED"
            marker["os_logon_reason"] = (
                "schtasks ONLOGON returned Access is denied on this host "
                "(often needs elevation). Local removable FreeForge job is the enforceable path."
            )

    _marker_path().write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
    st = startup_status()
    return {
        "ok": bool(st.get("local_registered")),
        "task_name": TASK_NAME,
        "local_job": job,
        "os_logon": os_result,
        "status": st,
        "auto_enabled_by_install": False,
        "tested": ["local_register", "local_remove", "os_query"],
        "not_tested": (
            ["actual_logon_fire", "schtasks_create_elevated"]
            if not os_result.get("ok")
            else ["actual_logon_fire"]
        ),
    }


def startup_remove() -> dict[str, Any]:
    ensure_state()
    store = ScheduleStore()
    local_del = store.delete_job(LOCAL_JOB_ID)
    marker = _marker_path()
    if marker.is_file():
        marker.unlink()
    os_del = _schtasks(["/Delete", "/TN", TASK_NAME, "/F"])
    # Delete "not found" is fine
    os_gone = (not os_del.get("ok")) and (
        "cannot find" in (os_del.get("stderr") or "").lower()
        or "ERROR: The system cannot find" in (os_del.get("stderr") or "")
    )
    st = startup_status()
    return {
        "ok": not st.get("local_registered") and not st.get("os_logon_registered"),
        "local_delete": local_del,
        "marker_removed": not marker.is_file(),
        "os_delete": os_del,
        "os_already_absent": os_gone or not st.get("os_logon_registered"),
        "status_after": st,
        "removable": True,
    }
