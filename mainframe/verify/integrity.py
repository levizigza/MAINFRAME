"""Detect weakened assertions / deleted tests; require spec trace for legit changes."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from typing import Any


def _test_metrics(source: str) -> dict[str, Any]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {"parse_error": True, "assert_count": 0, "test_fns": [], "sha256": None}
    asserts = 0
    tests: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            asserts += 1
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr.startswith("assert"):
                asserts += 1
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                tests.append(node.name)
    return {
        "parse_error": False,
        "assert_count": asserts,
        "test_fns": tests,
        "sha256": hashlib.sha256(source.encode("utf-8", errors="replace")).hexdigest(),
    }


def snapshot_tests(test_root: Path) -> dict[str, dict[str, Any]]:
    """Fingerprint evaluator or workspace tests."""
    out: dict[str, dict[str, Any]] = {}
    if not test_root.exists():
        return out
    for path in sorted(test_root.rglob("test_*.py")):
        rel = path.relative_to(test_root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        m = _test_metrics(text)
        m["path"] = rel
        out[rel] = m
    return out


def detect_integrity_violations(
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]],
    *,
    spec_traces: list[str] | None = None,
) -> dict[str, Any]:
    """
    Flag deleted tests or reduced assertion counts unless traced to user specification.
    """
    spec_traces = [s.casefold() for s in (spec_traces or [])]
    violations: list[dict[str, Any]] = []

    for path, meta in before.items():
        if path not in after:
            traced = any(path.casefold() in s or "delete test" in s for s in spec_traces)
            violations.append(
                {
                    "kind": "test_deleted",
                    "path": path,
                    "allowed_by_spec": traced,
                    "violation": not traced,
                }
            )
            continue
        b_asserts = int(meta.get("assert_count") or 0)
        a_asserts = int(after[path].get("assert_count") or 0)
        if a_asserts < b_asserts:
            traced = any(
                "weaken" in s or "relax assert" in s or "change behavior" in s for s in spec_traces
            )
            violations.append(
                {
                    "kind": "assertions_weakened",
                    "path": path,
                    "before": b_asserts,
                    "after": a_asserts,
                    "allowed_by_spec": traced,
                    "violation": not traced,
                }
            )
        # Deleted individual test functions
        lost = set(meta.get("test_fns") or []) - set(after[path].get("test_fns") or [])
        for name in sorted(lost):
            traced = any(
                name.casefold() in s or "delete test" in s or "remove test" in s for s in spec_traces
            )
            violations.append(
                {
                    "kind": "test_function_deleted",
                    "path": path,
                    "name": name,
                    "allowed_by_spec": traced,
                    "violation": not traced,
                }
            )

    bad = [v for v in violations if v.get("violation")]
    return {
        "ok": len(bad) == 0,
        "violations": violations,
        "blocking": bad,
    }
