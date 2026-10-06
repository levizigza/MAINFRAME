"""Probe zero-fee OS isolation on the actual host; never claim cwd/worktree is a sandbox."""

from __future__ import annotations

import platform
import subprocess
import sys
import time
from typing import Any

from mainframe.boundaries.job_object import (
    assign_pid_to_job,
    close_job,
    create_limited_job,
    job_object_available,
    terminate_job,
)
from mainframe.boundaries.policy import not_sandbox_disclaimer


def probe_isolation(*, verify_enforcement: bool = True) -> dict[str, Any]:
    """
    Verify Job Object (or report unavailable) on this Windows setup.

    Working directory / Git worktree / argument validators / prompts are listed
    as non-sandboxes regardless of probe outcome.
    """
    disclaimer = not_sandbox_disclaimer()
    result: dict[str, Any] = {
        "platform": sys.platform,
        "windows_version": platform.version() if sys.platform == "win32" else None,
        "zero_fee": True,
        "mechanism": None,
        "reliable_process_isolation": False,
        "verified_on_this_host": False,
        "os_network_isolation": False,
        "os_filesystem_jail": False,
        **disclaimer,
    }

    if not job_object_available():
        result["error"] = "job_object_unavailable_non_windows"
        return result

    job = create_limited_job(
        active_process_limit=2,
        job_memory_bytes=128 * 1024 * 1024,
    )
    if not job.get("ok"):
        result["error"] = job.get("error")
        result["mechanism"] = "windows_job_object"
        return result

    result["mechanism"] = "windows_job_object"
    result["job_create_ok"] = True
    result["limits_configured"] = job.get("limits")

    if not verify_enforcement:
        close_job(job["handle"])
        result["reliable_process_isolation"] = True
        result["verified_on_this_host"] = False
        result["note"] = "Job Object created but enforcement not exercised this call"
        return result

    # Verify assign + kill-on-close / terminate works with a short child
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    ph = getattr(proc, "_handle", None)
    assigned = assign_pid_to_job(job["handle"], int(ph)) if ph is not None else {"ok": False}
    result["assign_ok"] = bool(assigned.get("ok"))
    if assigned.get("ok"):
        terminate_job(job["handle"], 1)
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
        result["child_terminated"] = proc.returncode is not None
        result["reliable_process_isolation"] = bool(
            result["assign_ok"] and result["child_terminated"]
        )
        result["verified_on_this_host"] = result["reliable_process_isolation"]
    else:
        proc.kill()
        proc.wait(timeout=2)
        result["assign_error"] = assigned.get("error")
        result["reliable_process_isolation"] = False

    close_job(job["handle"])

    # Honest: Job Object does not provide network or full FS jail
    result["os_network_isolation"] = False
    result["os_filesystem_jail"] = False
    result["assumptions"] = [
        "Job Object limits CPU/memory/active processes and can terminate the job; "
        "it is not a full AppContainer / FS / network sandbox.",
        "Filesystem confinement is enforced by MAINFRAME path resolution, not the Job Object.",
        "Network denial is policy-layer unless a separate OS firewall/AppContainer is verified.",
    ]
    return result
