"""Deterministic pre-review checks — always run before any model review call."""

from __future__ import annotations

import ast
import os
import py_compile
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def run_deterministic_checks(
    workspace: Path,
    *,
    changed_paths: list[str] | None = None,
    test_target: str | None = "tests",
) -> dict[str, Any]:
    """
    Compile/syntax + optional pytest. No model. Findings are reproducible evidence.
    """
    workspace = workspace.resolve()
    findings: list[dict[str, Any]] = []
    paths = changed_paths or [
        str(p.relative_to(workspace)).replace("\\", "/")
        for p in workspace.rglob("*.py")
        if ".mainframe" not in p.parts and "worktree" not in p.parts
    ]

    for rel in paths:
        path = workspace / rel
        if not path.is_file() or path.suffix != ".py":
            continue
        try:
            src = path.read_text(encoding="utf-8")
        except OSError as exc:
            findings.append({"kind": "read_error", "path": rel, "detail": str(exc)})
            continue
        try:
            ast.parse(src, filename=rel)
        except SyntaxError as exc:
            findings.append(
                {
                    "kind": "syntax_error",
                    "path": rel,
                    "lineno": exc.lineno,
                    "detail": exc.msg,
                    "reproducible": True,
                }
            )
            continue
        try:
            with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as tmp:
                tmp.write(src.encode("utf-8"))
                tmp_path = tmp.name
            py_compile.compile(tmp_path, doraise=True)
        except py_compile.PyCompileError as exc:
            findings.append(
                {
                    "kind": "compile_error",
                    "path": rel,
                    "detail": str(exc),
                    "reproducible": True,
                }
            )
        finally:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:  # noqa: BLE001
                pass

        # Static smell: bare except / eval / assert True as security theater
        if "eval(" in src:
            findings.append(
                {
                    "kind": "dangerous_eval",
                    "path": rel,
                    "detail": "Use of eval() in changed file",
                    "reproducible": True,
                }
            )

    test_run: dict[str, Any] | None = None
    if test_target:
        tests = workspace / test_target if not Path(test_target).is_absolute() else Path(test_target)
        if tests.exists():
            env = dict(os.environ)
            env["PYTHONPATH"] = str(workspace)
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", str(tests), "-q", "--tb=short"],
                cwd=str(workspace),
                capture_output=True,
                text=True,
                env=env,
                timeout=60,
            )
            test_run = {
                "ok": proc.returncode == 0,
                "exit_code": proc.returncode,
                "stdout": (proc.stdout or "")[-2000:],
                "stderr": (proc.stderr or "")[-1000:],
            }
            if proc.returncode != 0:
                findings.append(
                    {
                        "kind": "test_failure",
                        "detail": "pytest failed",
                        "exit_code": proc.returncode,
                        "reproducible": True,
                    }
                )

    return {
        "ok": len(findings) == 0 and (test_run is None or test_run.get("ok")),
        "phase": "deterministic_pre_review",
        "paths_checked": paths,
        "findings": findings,
        "test_run": test_run,
        "model_used": False,
    }
