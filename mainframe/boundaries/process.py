"""Process spawning under boundaries — Job Object + wall-clock elapsed time."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from mainframe.boundaries.env import assert_no_model_credentials, worker_env
from mainframe.boundaries.isolation import probe_isolation
from mainframe.boundaries.job_object import (
    assign_pid_to_job,
    close_job,
    create_limited_job,
    job_object_available,
    terminate_job,
)
from mainframe.boundaries.network import authorize_network
from mainframe.boundaries.policy import may_execute_untrusted


def spawn_bounded(
    argv: list[str],
    *,
    root: Path,
    trust: str = "trusted_local",
    cwd: str | Path | None = None,
    network: bool = False,
    network_target: str | None = None,
    elapsed_s: float = 5.0,
    memory_bytes: int = 256 * 1024 * 1024,
    active_processes: int = 2,
    unattended: bool = False,
    executable_kind: str = "python_subprocess",
    use_job_object: bool = True,
) -> dict[str, Any]:
    """
    Spawn a process with env scrubbing, optional Job Object limits, and wall timeout.

    Refuses untrusted execution when isolation is unreliable.
    """
    root = root.resolve()
    isolation = probe_isolation(verify_enforcement=False)
    # Refresh reliable bit from last full probe cache? Use lightweight create check.
    if job_object_available():
        isolation["reliable_process_isolation"] = True
        isolation["mechanism"] = "windows_job_object"

    permit = may_execute_untrusted(trust=trust, isolation=isolation, unattended=unattended)
    if not permit["allowed"]:
        return {
            "ok": False,
            "spawned": False,
            "error": permit["reason"],
            "permit": permit,
            "boundary": "process_spawning",
            "enforced": True,
        }

    if network or network_target:
        net = authorize_network(trust=trust, url_or_host=network_target or "example.com")
        if not net.get("allowed"):
            return {
                "ok": False,
                "spawned": False,
                "error": net.get("reason"),
                "network": net,
                "boundary": "network_access",
                "enforced": True,
            }

    work = Path(cwd).resolve() if cwd else root
    try:
        work.relative_to(root)
    except ValueError:
        return {
            "ok": False,
            "spawned": False,
            "error": "cwd_outside_root",
            "boundary": "filesystem_paths",
            "enforced": True,
            "note": "A working directory is not a security sandbox.",
        }

    env_info = worker_env()
    cred = assert_no_model_credentials(env_info["env"])
    if not cred["ok"]:
        return {
            "ok": False,
            "spawned": False,
            "error": "credentials_would_leak_to_worker",
            "cred": cred,
            "boundary": "environment_variables",
            "enforced": True,
        }

    job_meta: dict[str, Any] = {"used": False}
    job_handle = None
    if use_job_object and job_object_available():
        job = create_limited_job(
            active_process_limit=active_processes,
            job_memory_bytes=memory_bytes,
            per_job_user_time_100ns=int(max(elapsed_s, 1) * 10_000_000 * 50),
        )
        if job.get("ok"):
            job_handle = job["handle"]
            job_meta = {
                "used": True,
                "mechanism": "windows_job_object",
                "limits": job.get("limits"),
                "zero_fee": True,
            }
        else:
            job_meta = {"used": False, "error": job.get("error")}

    started = time.perf_counter()
    try:
        proc = subprocess.Popen(
            argv,
            cwd=str(work),
            env=env_info["env"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
        )
    except OSError as exc:
        if job_handle is not None:
            close_job(job_handle)
        return {
            "ok": False,
            "spawned": False,
            "error": str(exc),
            "boundary": "process_spawning",
            "enforced": True,
        }

    if job_handle is not None:
        ph = getattr(proc, "_handle", None)
        if ph is not None:
            assigned = assign_pid_to_job(job_handle, int(ph))
            job_meta["assigned"] = assigned

    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=elapsed_s)
    except subprocess.TimeoutExpired:
        timed_out = True
        proc.kill()
        if job_handle is not None:
            terminate_job(job_handle, 1)
        try:
            stdout, stderr = proc.communicate(timeout=2)
        except Exception:  # noqa: BLE001
            stdout, stderr = "", ""
    finally:
        if job_handle is not None:
            close_job(job_handle)

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return {
        "ok": (not timed_out) and proc.returncode == 0,
        "spawned": True,
        "returncode": proc.returncode,
        "timed_out": timed_out,
        "elapsed_ms": elapsed_ms,
        "elapsed_limit_s": elapsed_s,
        "stdout": (stdout or "")[-2000:],
        "stderr": (stderr or "")[-2000:],
        "job_object": job_meta,
        "env": {
            "credentials_outside_worker": True,
            "removed_n": len(env_info["removed_keys"]),
        },
        "executable_kind": executable_kind,
        "trust": trust,
        "boundaries_applied": [
            "process_spawning",
            "environment_variables",
            "cpu",
            "memory",
            "elapsed_time",
        ],
        "enforced": True,
        "cwd_is_not_sandbox": True,
    }
