"""Run reproduction, targeted tests, type checks, risk-based regression."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from mainframe.cost_gate import scrub_env_for_child
from mainframe.verify.taxonomy import classify_run_failure


def _run(
    cmd: list[str],
    *,
    cwd: Path,
    timeout_s: float = 60,
    env_extra: dict[str, str] | None = None,
) -> dict[str, Any]:
    env = scrub_env_for_child()
    if env_extra:
        env.update(env_extra)
    try:
        p = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=env,
        )
        return {
            "ok": p.returncode == 0,
            "exit_code": p.returncode,
            "stdout": p.stdout or "",
            "stderr": p.stderr or "",
            "command": cmd,
            "error": None,
        }
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "command": cmd,
            "error": f"missing_dependency:{exc}",
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "command": cmd,
            "error": "timeout",
        }


def reproduce_failure(
    target_root: Path,
    *,
    test_target: str,
    pythonpath: str | None = None,
) -> dict[str, Any]:
    """Attempt to reproduce failure before repair (practical path: run failing test)."""
    env = {}
    if pythonpath:
        env["PYTHONPATH"] = pythonpath
    run = _run(
        [sys.executable, "-m", "pytest", test_target, "-q", "--tb=short"],
        cwd=target_root,
        env_extra=env,
    )
    kind = classify_run_failure(
        exit_code=run.get("exit_code"),
        stdout=run.get("stdout") or "",
        stderr=run.get("stderr") or "",
        error=run.get("error"),
        reproduced_before_repair=not run.get("ok"),
    )
    return {
        "phase": "reproduce_before_repair",
        "reproduced": not run.get("ok") and kind.get("product_defect"),
        "run": run,
        "classification": kind,
    }


def run_targeted(
    cwd: Path,
    test_paths: list[str],
    *,
    pythonpath: str | None = None,
) -> dict[str, Any]:
    env = {}
    if pythonpath:
        env["PYTHONPATH"] = pythonpath
    cmd = [sys.executable, "-m", "pytest", *test_paths, "-q", "--tb=short"]
    run = _run(cmd, cwd=cwd, env_extra=env)
    kind = classify_run_failure(
        exit_code=run.get("exit_code"),
        stdout=run.get("stdout") or "",
        stderr=run.get("stderr") or "",
        error=run.get("error"),
    )
    return {"phase": "targeted_tests", "run": run, "classification": kind}


def run_typecheck(target_root: Path, paths: list[str] | None = None) -> dict[str, Any]:
    """Optional pyright; classify unavailable separately from product defects."""
    cmd = [sys.executable, "-m", "pyright"]
    if paths:
        cmd.extend(paths)
    else:
        cmd.append(str(target_root))
    # Prefer pyright CLI if present
    which = _run(["pyright", "--version"], cwd=target_root, timeout_s=10)
    if which.get("ok"):
        cmd = ["pyright", "--outputjson"]
        if paths:
            cmd.extend(paths)
    run = _run(cmd, cwd=target_root, timeout_s=120)
    if run.get("error") and "missing_dependency" in str(run.get("error")):
        return {
            "phase": "typecheck",
            "run": run,
            "classification": {
                "kind": "missing_dependency",
                "product_defect": False,
                "detail": "type checker unavailable",
            },
            "skipped": True,
        }
    kind = classify_run_failure(
        exit_code=run.get("exit_code"),
        stdout=run.get("stdout") or "",
        stderr=run.get("stderr") or "",
        error=run.get("error"),
    )
    # Treat type errors as product_defect when checker ran
    if not run.get("ok") and not run.get("skipped"):
        if kind["kind"] == "environment_failure" and "error" in (run.get("stdout") or "").lower():
            kind = {
                "kind": "product_defect",
                "product_defect": True,
                "detail": "typecheck reported errors",
            }
    return {"phase": "typecheck", "run": run, "classification": kind, "skipped": False}


def run_regression(
    cwd: Path,
    *,
    risk: str,
    smoke_paths: list[str],
    full_paths: list[str] | None = None,
    pythonpath: str | None = None,
) -> dict[str, Any]:
    """
    Risk-based regression: low → smoke only; high → broader set.
    """
    paths = list(smoke_paths)
    if risk in {"high", "medium"} and full_paths:
        paths = list(dict.fromkeys(smoke_paths + full_paths))
    return {
        **run_targeted(cwd, paths, pythonpath=pythonpath),
        "phase": "risk_regression",
        "risk": risk,
        "paths": paths,
    }
