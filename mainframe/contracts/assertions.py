"""Executable assertions for contracts (interface preserve, output fields, etc.)."""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path
from typing import Any

from mainframe.contracts.schema import validate_against_schema


def run_assertions(
    assertions: list[dict[str, Any]],
    *,
    output: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    output = output or {}
    context = context or {}
    for a in assertions:
        results.append(_run_one(a, output=output, context=context))
    ok = all(r.get("ok") for r in results)
    return {"ok": ok, "results": results}


def _run_one(a: dict[str, Any], *, output: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    aid = a.get("id") or a.get("type")
    typ = a.get("type")
    try:
        if typ == "output_field":
            field = a["field"]
            ok = field in output and output[field] is not None
            return {"id": aid, "ok": ok, "detail": {"field": field, "present": ok}}
        if typ == "regex":
            field = a["field"]
            val = str(output.get(field, ""))
            ok = re.fullmatch(a["pattern"], val) is not None
            return {"id": aid, "ok": ok, "detail": {"value": val[:80]}}
        if typ == "min":
            field = a["field"]
            ok = field in output and output[field] >= a["value"]
            return {"id": aid, "ok": ok, "detail": {"value": output.get(field)}}
        if typ == "output_schema":
            v = validate_against_schema(output, a.get("schema") or {})
            return {"id": aid, "ok": v["ok"], "detail": v}
        if typ == "preserve_interface":
            return _assert_preserve_interface(a, context)
        if typ == "equals":
            field = a["field"]
            ok = output.get(field) == a.get("value")
            return {"id": aid, "ok": ok, "detail": {"actual": output.get(field)}}
        return {"id": aid, "ok": False, "detail": f"unknown_assertion_type:{typ}"}
    except Exception as exc:  # noqa: BLE001
        return {"id": aid, "ok": False, "detail": f"{type(exc).__name__}: {exc}"}


def _assert_preserve_interface(a: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """
    Declared public names must still exist in module source with matching kinds.

    ``a['interface']``: {\"module_path\": \"pkg/mod.py\", \"symbols\": [{\"name\": \"f\", \"kind\": \"function\"}]}
    Optional ``before_source`` / ``after_source`` in context for comparing two trees.
    """
    iface = a.get("interface") or context.get("interface") or {}
    module_path = iface.get("module_path")
    symbols = iface.get("symbols") or []
    root = Path(context.get("root") or ".")
    after_text = context.get("after_source")
    if after_text is None and module_path:
        path = root / module_path
        if not path.is_file():
            return {
                "id": a.get("id"),
                "ok": False,
                "detail": {"error": "module_missing", "path": module_path},
            }
        after_text = path.read_text(encoding="utf-8", errors="replace")

    before_text = context.get("before_source")
    after_defs = _top_level_defs(after_text or "")
    missing: list[str] = []
    kind_mismatch: list[dict[str, Any]] = []
    for sym in symbols:
        name = sym["name"]
        kind = sym.get("kind", "function")
        if name not in after_defs:
            missing.append(name)
        elif after_defs[name] != kind:
            kind_mismatch.append({"name": name, "expected": kind, "actual": after_defs[name]})

    sig_breaks: list[str] = []
    if before_text is not None:
        before_sigs = _function_signatures(before_text)
        after_sigs = _function_signatures(after_text or "")
        for sym in symbols:
            if sym.get("kind") != "function":
                continue
            name = sym["name"]
            if name in before_sigs and name in after_sigs and before_sigs[name] != after_sigs[name]:
                sig_breaks.append(name)

    ok = not missing and not kind_mismatch and not sig_breaks
    return {
        "id": a.get("id") or "preserve_interface",
        "ok": ok,
        "detail": {
            "missing": missing,
            "kind_mismatch": kind_mismatch,
            "signature_breaks": sig_breaks,
            "preserved": ok,
        },
    }


def _top_level_defs(source: str) -> dict[str, str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    out: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            out[node.name] = "function"
        elif isinstance(node, ast.AsyncFunctionDef):
            out[node.name] = "async_function"
        elif isinstance(node, ast.ClassDef):
            out[node.name] = "class"
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    out[t.id] = "assign"
    return out


def _function_signatures(source: str) -> dict[str, str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    out: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            parts = [a.arg for a in args.args]
            out[node.name] = "(" + ", ".join(parts) + ")"
    return out
