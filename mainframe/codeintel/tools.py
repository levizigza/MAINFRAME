"""Narrow codeintel tools — no shell improvisation, no model service."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mainframe.codeintel.deps import check_callable, list_public_api, resolve_module
from mainframe.codeintel.provenance import evidence
from mainframe.codeintel.python_ast import (
    build_ast_index,
    def_to_result,
    find_callers,
    find_defs_by_name,
)
from mainframe.codeintel.python_jedi import jedi_available, jedi_goto, jedi_signatures
from mainframe.codeintel.python_pyright import pyright_available, run_diagnostics
from mainframe.codeintel.versions import content_version, range_dict
from mainframe.cost_gate import authorize

# Simple cache per root path string
_INDEX_CACHE: dict[str, Any] = {}


def _index(root: Path):
    key = str(root.resolve()).casefold()
    if key not in _INDEX_CACHE:
        _INDEX_CACHE[key] = build_ast_index(root.resolve())
    return _INDEX_CACHE[key]


def invalidate_index(root: Path | None = None) -> None:
    if root is None:
        _INDEX_CACHE.clear()
    else:
        _INDEX_CACHE.pop(str(root.resolve()).casefold(), None)


def _gate(tool_id: str) -> dict[str, Any] | None:
    g = authorize("tool", tool_id, local=True)
    if not g.allowed:
        return {"ok": False, "cost_gate": g.to_dict(), "model_service_used": False}
    return None


def tool_status() -> dict[str, Any]:
    denied = _gate("local.codeintel_status")
    if denied:
        return denied
    return {
        "ok": True,
        "primary_languages": ["python"],
        "adapters": {
            "stdlib_ast": True,
            "jedi": jedi_available(),
            "pyright": pyright_available(),
        },
        "model_service_used": False,
        "note": "Jedi/Pyright used only when already installed; otherwise AST + lexical with limitation.",
    }


def lookup_symbol(
    root: Path,
    name: str,
    *,
    module: str | None = None,
) -> dict[str, Any]:
    """Resolve symbol definitions; disambiguate duplicates via module hint."""
    denied = _gate("local.codeintel_lookup")
    if denied:
        return denied
    root = root.resolve()
    idx = _index(root)
    defs = find_defs_by_name(idx, name, module_hint=module)
    results = [def_to_result(idx, d) for d in defs]
    return {
        "ok": True,
        "name": name,
        "module_hint": module,
        "count": len(results),
        "definitions": results,
        "duplicate_names": len(results) > 1 and module is None,
        "disambiguated": module is not None and len(results) <= 1,
        "model_service_used": False,
    }


def definition_at(root: Path, rel_path: str, line: int, column: int) -> dict[str, Any]:
    """Goto-definition at position — Jedi when available, else AST nearest def."""
    denied = _gate("local.codeintel_definition")
    if denied:
        return denied
    root = root.resolve()
    path = (root / rel_path).resolve()
    if not str(path).startswith(str(root)):
        return {"ok": False, "error": "path_escape", "model_service_used": False}

    if jedi_available():
        out = jedi_goto(path, line, column, project_root=root)
        out["fallback"] = None
        return out

    # AST approximate: find enclosing / nearest def name under cursor line
    idx = _index(root)
    rel = path.relative_to(root).as_posix()
    lines = idx.files.get(rel) or []
    if not lines or line < 1 or line > len(lines):
        return {
            "ok": False,
            "limitation": "jedi_not_installed",
            "evidence": evidence(
                "lexical_fallback",
                tool="stdlib_ast",
                limitation="jedi_not_installed",
                detail="No line context for AST fallback",
            ),
            "model_service_used": False,
        }
    # Prefer defs whose lineno <= line in same file, pick closest
    file_defs = [d for d in idx.defs if d.path == rel and d.lineno <= line]
    if not file_defs:
        return {
            "ok": False,
            "limitation": "jedi_not_installed",
            "results": [],
            "evidence": evidence(
                "parser_approximate",
                tool="stdlib_ast",
                limitation="jedi_not_installed",
            ),
            "model_service_used": False,
        }
    best = max(file_defs, key=lambda d: d.lineno)
    return {
        "ok": True,
        "results": [def_to_result(idx, best)],
        "limitation": "jedi_not_installed",
        "evidence": evidence(
            "parser_approximate",
            tool="stdlib_ast",
            limitation="jedi_not_installed",
            detail="Nearest preceding definition in file",
        ),
        "query_version": content_version(path),
        "model_service_used": False,
    }


def references(root: Path, name: str, *, module: str | None = None) -> dict[str, Any]:
    denied = _gate("local.codeintel_references")
    if denied:
        return denied
    root = root.resolve()
    idx = _index(root)
    defs = find_defs_by_name(idx, name, module_hint=module)
    refs: list[dict[str, Any]] = []
    for d in defs:
        for c in find_callers(idx, d):
            full = root / c["path"]
            refs.append(
                {
                    "name": c["name"],
                    "target_qualname": d.qualname,
                    "range": range_dict(
                        full,
                        c["lineno"],
                        c["col"],
                        version=idx.versions.get(c["path"]),
                    ),
                    "evidence": evidence(
                        "parser_approximate",
                        tool="stdlib_ast",
                        detail="Import-aware call-site match",
                    ),
                }
            )
    return {
        "ok": True,
        "name": name,
        "module_hint": module,
        "references": refs,
        "definition_count": len(defs),
        "model_service_used": False,
    }


def callers(root: Path, name: str, *, module: str | None = None) -> dict[str, Any]:
    """Narrow tool: list actual callers of a (module-qualified) symbol."""
    denied = _gate("local.codeintel_callers")
    if denied:
        return denied
    root = root.resolve()
    idx = _index(root)
    defs = find_defs_by_name(idx, name, module_hint=module)
    if module is not None and len(defs) > 1:
        # Still ambiguous — require tighter module
        defs = [d for d in defs if d.module == module.replace("/", ".") or d.module.endswith("." + module.replace("/", "."))]
    groups = []
    for d in defs:
        calls = find_callers(idx, d)
        groups.append(
            {
                "definition": def_to_result(idx, d),
                "callers": [
                    {
                        "call_name": c["name"],
                        "range": range_dict(
                            root / c["path"],
                            c["lineno"],
                            c["col"],
                            version=idx.versions.get(c["path"]),
                        ),
                        "evidence": evidence(
                            "parser_approximate",
                            tool="stdlib_ast",
                            detail="caller resolved via imports",
                        ),
                    }
                    for c in calls
                ],
            }
        )
    return {
        "ok": True,
        "name": name,
        "module_hint": module,
        "groups": groups,
        "model_service_used": False,
    }


def signature(
    root: Path,
    *,
    rel_path: str | None = None,
    line: int | None = None,
    column: int | None = None,
    module: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """Narrow tool: inspect signature at cursor (Jedi) or of a named symbol (AST/inspect)."""
    denied = _gate("local.codeintel_signature")
    if denied:
        return denied
    root = root.resolve()

    if rel_path and line is not None and column is not None and jedi_available():
        path = (root / rel_path).resolve()
        return jedi_signatures(path, line, column, project_root=root)

    if name:
        idx = _index(root)
        defs = find_defs_by_name(idx, name, module_hint=module)
        sigs = []
        for d in defs:
            lines = idx.files.get(d.path) or []
            # Extract def line as approximate signature
            hdr = lines[d.lineno - 1] if 0 < d.lineno <= len(lines) else ""
            sigs.append(
                {
                    "name": d.name,
                    "qualname": d.qualname,
                    "header": hdr.strip(),
                    "range": def_to_result(idx, d)["range"],
                    "evidence": evidence(
                        "parser_approximate",
                        tool="stdlib_ast",
                        detail="Function header line",
                        limitation=None if jedi_available() else "jedi_not_installed_for_cursor_sigs",
                    ),
                }
            )
        return {
            "ok": True,
            "signatures": sigs,
            "limitation": None if jedi_available() else "jedi_not_used_for_named_lookup",
            "model_service_used": False,
        }

    return {
        "ok": False,
        "error": "provide_cursor_or_name",
        "limitation": None if jedi_available() else "jedi_not_installed",
        "model_service_used": False,
    }


def file_imports(root: Path, rel_path: str) -> dict[str, Any]:
    denied = _gate("local.codeintel_imports")
    if denied:
        return denied
    root = root.resolve()
    idx = _index(root)
    rel = rel_path.replace("\\", "/")
    imps = idx.imports.get(rel, [])
    full = root / rel
    return {
        "ok": True,
        "path": rel,
        "imports": imps,
        "content_version": idx.versions.get(rel) or content_version(full),
        "evidence": evidence("parser_approximate", tool="stdlib_ast", detail="ast Import/ImportFrom"),
        "model_service_used": False,
    }


def diagnostics(root: Path) -> dict[str, Any]:
    denied = _gate("local.codeintel_diagnostics")
    if denied:
        return denied
    return run_diagnostics(root.resolve())


def dependency_api(
    module: str,
    *,
    attr: str | None = None,
    extra_path: str | None = None,
) -> dict[str, Any]:
    """Resolve installed module / check proposed attribute call."""
    denied = _gate("local.codeintel_deps")
    if denied:
        return denied
    extra = [extra_path] if extra_path else None
    if attr:
        return check_callable(module, attr, extra_sys_path=extra)
    return list_public_api(module, extra_sys_path=extra)


def reject_absent_call(
    module: str,
    attr: str,
    *,
    extra_path: str | None = None,
) -> dict[str, Any]:
    """Explicit narrow tool: reject proposed calls absent from installed dependency."""
    out = dependency_api(module, attr=attr, extra_path=extra_path)
    out["tool"] = "reject_absent_call"
    return out
