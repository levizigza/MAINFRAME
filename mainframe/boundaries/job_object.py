"""Windows Job Object helpers — zero-fee OS process isolation when available."""

from __future__ import annotations

import ctypes
import sys
from ctypes import POINTER, Structure, byref, c_size_t, c_ulonglong, sizeof
from ctypes import wintypes as w
from typing import Any

JobObjectExtendedLimitInformation = 9
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_LIMIT_JOB_TIME = 0x00000004
JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
JOB_OBJECT_LIMIT_WORKINGSET = 0x00000001


class IO_COUNTERS(Structure):
    _fields_ = [
        ("ReadOperationCount", c_ulonglong),
        ("WriteOperationCount", c_ulonglong),
        ("OtherOperationCount", c_ulonglong),
        ("ReadTransferCount", c_ulonglong),
        ("WriteTransferCount", c_ulonglong),
        ("OtherTransferCount", c_ulonglong),
    ]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", w.LARGE_INTEGER),
        ("PerJobUserTimeLimit", w.LARGE_INTEGER),
        ("LimitFlags", w.DWORD),
        ("MinimumWorkingSetSize", c_size_t),
        ("MaximumWorkingSetSize", c_size_t),
        ("ActiveProcessLimit", w.DWORD),
        ("Affinity", c_size_t),
        ("PriorityClass", w.DWORD),
        ("SchedulingClass", w.DWORD),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", c_size_t),
        ("JobMemoryLimit", c_size_t),
        ("PeakProcessMemoryUsed", c_size_t),
        ("PeakJobMemoryUsed", c_size_t),
    ]


def job_object_available() -> bool:
    return sys.platform == "win32"


def create_limited_job(
    *,
    active_process_limit: int = 4,
    job_memory_bytes: int | None = 256 * 1024 * 1024,
    per_job_user_time_100ns: int | None = None,
    kill_on_close: bool = True,
) -> dict[str, Any]:
    """
    Create a Windows Job Object with resource limits (zero-fee OS mechanism).

    Returns handle info or error. Caller must close the handle.
    """
    if not job_object_available():
        return {"ok": False, "error": "not_windows", "mechanism": None}

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    CreateJobObjectW = kernel32.CreateJobObjectW
    CreateJobObjectW.restype = w.HANDLE
    CreateJobObjectW.argtypes = [w.LPVOID, w.LPCWSTR]
    SetInformationJobObject = kernel32.SetInformationJobObject
    SetInformationJobObject.argtypes = [w.HANDLE, w.INT, w.LPVOID, w.DWORD]
    SetInformationJobObject.restype = w.BOOL

    handle = CreateJobObjectW(None, None)
    if not handle:
        return {
            "ok": False,
            "error": f"CreateJobObjectW failed ({ctypes.get_last_error()})",
            "mechanism": "windows_job_object",
        }

    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    flags = 0
    if kill_on_close:
        flags |= JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    flags |= JOB_OBJECT_LIMIT_ACTIVE_PROCESS
    info.BasicLimitInformation.ActiveProcessLimit = max(1, int(active_process_limit))
    if job_memory_bytes:
        flags |= JOB_OBJECT_LIMIT_PROCESS_MEMORY | JOB_OBJECT_LIMIT_JOB_MEMORY
        info.ProcessMemoryLimit = int(job_memory_bytes)
        info.JobMemoryLimit = int(job_memory_bytes)
    if per_job_user_time_100ns:
        flags |= JOB_OBJECT_LIMIT_JOB_TIME
        info.BasicLimitInformation.PerJobUserTimeLimit = int(per_job_user_time_100ns)
    info.BasicLimitInformation.LimitFlags = flags

    ok = SetInformationJobObject(
        handle, JobObjectExtendedLimitInformation, byref(info), sizeof(info)
    )
    if not ok:
        err = ctypes.get_last_error()
        kernel32.CloseHandle(handle)
        return {
            "ok": False,
            "error": f"SetInformationJobObject failed ({err})",
            "mechanism": "windows_job_object",
        }

    return {
        "ok": True,
        "mechanism": "windows_job_object",
        "handle": int(handle),
        "limits": {
            "active_process_limit": active_process_limit,
            "job_memory_bytes": job_memory_bytes,
            "per_job_user_time_100ns": per_job_user_time_100ns,
            "kill_on_close": kill_on_close,
            "limit_flags": flags,
        },
        "zero_fee": True,
    }


def assign_pid_to_job(job_handle: int, process_handle: int) -> dict[str, Any]:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    ok = kernel32.AssignProcessToJobObject(w.HANDLE(job_handle), w.HANDLE(process_handle))
    return {
        "ok": bool(ok),
        "error": None if ok else f"AssignProcessToJobObject failed ({ctypes.get_last_error()})",
    }


def terminate_job(job_handle: int, exit_code: int = 1) -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.TerminateJobObject(w.HANDLE(job_handle), w.UINT(exit_code))


def close_job(job_handle: int) -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CloseHandle(w.HANDLE(job_handle))
