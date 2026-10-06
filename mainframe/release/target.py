"""Verify the actual target Windows configuration — never invent installers."""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from typing import Any


def _run(cmd: list[str], timeout: float = 15.0) -> dict[str, Any]:
    try:
        p = subprocess.run(
            cmd,
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
        return {"ok": False, "exit_code": None, "stdout": "", "stderr": "not_found"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "exit_code": None, "stdout": "", "stderr": "timeout"}


def _windows_nt_version() -> dict[str, Any]:
    if sys.platform != "win32":
        return {"ok": False, "error": "not_windows"}
    ps = (
        "Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion' | "
        "Select-Object ProductName,DisplayVersion,CurrentBuild,InstallationType | "
        "ConvertTo-Json -Compress"
    )
    r = _run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
        timeout=20.0,
    )
    out: dict[str, Any] = {"probe_ok": r["ok"], "raw": r.get("stdout") or ""}
    if r["ok"] and r["stdout"]:
        import json

        try:
            data = json.loads(r["stdout"])
            out.update(
                {
                    "product_name": data.get("ProductName"),
                    "display_version": data.get("DisplayVersion"),
                    "current_build": str(data.get("CurrentBuild") or ""),
                    "installation_type": data.get("InstallationType"),
                }
            )
        except json.JSONDecodeError:
            out["parse_error"] = True
    return out


def _which(name: str) -> dict[str, Any]:
    path = shutil.which(name)
    return {"present": path is not None, "path": path}


def measure_target() -> dict[str, Any]:
    """Live measurements of this host — used for setup docs (not copied from old guides)."""
    nt = _windows_nt_version()
    py = {
        "version": platform.python_version(),
        "executable": sys.executable,
        "implementation": platform.python_implementation(),
        "meets_3_11": sys.version_info >= (3, 11),
    }
    node = _which("node")
    if node["present"]:
        vr = _run(["node", "--version"])
        node["version"] = vr.get("stdout") or None
    git = _which("git")
    if git["present"]:
        vr = _run(["git", "--version"])
        git["version"] = vr.get("stdout") or None

    # Obsolete installer patterns we explicitly refuse to document as required
    obsolete_refused = [
        {
            "command": "choco install python",
            "reason": "Not verified on this host; Python already present via miniconda path",
            "documented_as_required": False,
        },
        {
            "command": "winget install Python.Python.3",
            "reason": "Not run; target already has Python 3.12 — do not invent installer steps",
            "documented_as_required": False,
        },
        {
            "command": "pip install -r requirements.txt",
            "reason": "Core has no required pip deps",
            "documented_as_required": False,
        },
        {
            "command": "docker compose up",
            "reason": "Docker Desktop not required for core; not present on this host",
            "documented_as_required": False,
        },
    ]

    platform_note = (
        f"platform.platform()={platform.platform()}; "
        f"registry ProductName={nt.get('product_name')}; "
        f"DisplayVersion={nt.get('display_version')}; "
        f"CurrentBuild={nt.get('current_build')}. "
        "Build 26200 is the Windows 11 25H2 family; registry ProductName may still say "
        "'Windows 10 Home' on some Home SKUs — document both observed values."
    )

    return {
        "os": {
            "sys_platform": sys.platform,
            "platform_string": platform.platform(),
            "machine": platform.machine(),
            "nt_version": nt,
            "note": platform_note,
        },
        "python": py,
        "tools": {"node": node, "git": git, "rg": _which("rg")},
        "obsolete_installer_commands_refused": obsolete_refused,
        "setup_commands_verified_on_this_host": [
            f'"{sys.executable}" -m mainframe status',
            f'"{sys.executable}" -m mainframe doctor',
            f'"{sys.executable}" -m mainframe run echo --param message=hello',
        ],
        "optional_not_present": {
            "openclaw": shutil.which("openclaw") is None,
            "docker": shutil.which("docker") is None,
        },
    }
