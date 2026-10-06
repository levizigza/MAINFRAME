"""Clean-install smoke test against a packaged release tree."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from mainframe.release.pins import RELEASE_VERSION


def _run_in_tree(tree: Path, args: list[str], timeout: float = 60.0) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tree) + os.pathsep + env.get("PYTHONPATH", "")
    cmd = [sys.executable, "-m", "mainframe", *args]
    try:
        p = subprocess.run(
            cmd,
            cwd=str(tree),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
        return {
            "ok": p.returncode == 0,
            "exit_code": p.returncode,
            "stdout": (p.stdout or "").strip(),
            "stderr": (p.stderr or "").strip(),
            "cmd": cmd,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout", "cmd": cmd}


def clean_install_smoke(tree: Path | str) -> dict[str, Any]:
    root = Path(tree)
    if not (root / "mainframe").is_dir():
        return {"ok": False, "error": "not_a_release_tree", "tree": str(root)}
    for req in ("LICENSE", "PINNED_DEPENDENCIES.json", "SETUP.md", "UNINSTALL.md"):
        if not (root / req).is_file():
            return {"ok": False, "error": f"missing_{req}", "tree": str(root)}

    checks: list[dict[str, Any]] = []

    status = _run_in_tree(root, ["status"])
    checks.append({"id": "status", "ok": status["ok"], "detail": status.get("exit_code")})

    echo = _run_in_tree(root, ["run", "echo", "--param", "message=release-smoke"])
    echo_ok = bool(echo.get("ok"))
    if echo_ok and echo.get("stdout"):
        try:
            payload = json.loads(echo["stdout"])
            echo_ok = bool(payload.get("ok", True)) or "release-smoke" in echo["stdout"]
        except json.JSONDecodeError:
            echo_ok = "release-smoke" in echo["stdout"]
    checks.append({"id": "echo", "ok": echo_ok, "detail": echo.get("exit_code")})

    fix = _run_in_tree(
        root,
        [
            "connectors",
            "call",
            "--connector",
            "dog_ceo",
            "--op",
            "list_breeds",
            "--mode",
            "fixture",
        ],
        timeout=90.0,
    )
    checks.append(
        {
            "id": "offline_fixture",
            "ok": fix["ok"],
            "detail": fix.get("exit_code"),
            "stderr_tail": (fix.get("stderr") or "")[-200:],
        }
    )

    passed = sum(1 for c in checks if c["ok"])
    return {
        "ok": passed == len(checks),
        "release_version": RELEASE_VERSION,
        "tree": str(root),
        "passed": passed,
        "total": len(checks),
        "checks": checks,
        "pip_install_used": False,
        "hosted_ci_used": False,
    }
