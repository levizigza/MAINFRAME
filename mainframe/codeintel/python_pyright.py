"""Optional Pyright diagnostics — when pyright is already on PATH / importable."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from mainframe.codeintel.provenance import evidence
from mainframe.cost_gate import scrub_env_for_child


def pyright_available() -> bool:
    if shutil.which("pyright"):
        return True
    try:
        import pyright  # noqa: F401

        return True
    except ImportError:
        return False


def run_diagnostics(root: Path, *, paths: list[str] | None = None) -> dict[str, Any]:
    """Return Pyright diagnostics as language_server_fact, or limitation if missing."""
    if not pyright_available():
        return {
            "ok": False,
            "limitation": "pyright_not_available",
            "diagnostics": [],
            "evidence": evidence(
                "lexical_fallback",
                tool="none",
                limitation="pyright_not_available",
                detail="AST/Jedi path still available; diagnostics skipped",
            ),
            "model_service_used": False,
        }

    root = root.resolve()
    cmd = ["pyright", "--outputjson"]
    if paths:
        cmd.extend(paths)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
            env=scrub_env_for_child(),
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": str(exc),
            "diagnostics": [],
            "evidence": evidence("language_server_fact", tool="pyright", detail=str(exc)),
            "model_service_used": False,
        }

    raw = proc.stdout or ""
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return {
            "ok": False,
            "error": "pyright_json_parse_failed",
            "stdout_head": raw[:500],
            "diagnostics": [],
            "evidence": evidence("language_server_fact", tool="pyright", detail="bad json"),
            "model_service_used": False,
        }

    diags = []
    for g in payload.get("generalDiagnostics") or []:
        fr = g.get("file") or ""
        rng = g.get("range") or {}
        start = rng.get("start") or {}
        end = rng.get("end") or {}
        diags.append(
            {
                "path": str(fr).replace("\\", "/"),
                "severity": g.get("severity"),
                "message": g.get("message"),
                "rule": g.get("rule"),
                "start_line": (start.get("line") or 0) + 1,
                "start_col": start.get("character") or 0,
                "end_line": (end.get("line") or 0) + 1,
                "end_col": end.get("character") or 0,
                "evidence": evidence(
                    "language_server_fact",
                    tool="pyright",
                    detail=g.get("rule"),
                ),
            }
        )
    return {
        "ok": True,
        "diagnostics": diags,
        "summary": payload.get("summary"),
        "evidence": evidence("language_server_fact", tool="pyright", detail="--outputjson"),
        "model_service_used": False,
        "exit_code": proc.returncode,
    }
