"""Optional Jedi adapter — language-tool facts when already installed."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mainframe.codeintel.provenance import evidence
from mainframe.codeintel.versions import content_version, range_dict


def jedi_available() -> bool:
    try:
        import jedi  # noqa: F401

        return True
    except ImportError:
        return False


def jedi_goto(
    path: Path,
    line: int,
    column: int,
    *,
    project_root: Path | None = None,
) -> dict[str, Any]:
    if not jedi_available():
        return {
            "ok": False,
            "limitation": "jedi_not_installed",
            "evidence": evidence(
                "lexical_fallback",
                tool="none",
                limitation="jedi_not_installed",
                detail="Install optional free Jedi locally to enable goto; AST fallback used elsewhere",
            ),
            "model_service_used": False,
        }
    import jedi

    path = path.resolve()
    text = path.read_text(encoding="utf-8", errors="replace")
    project = None
    if project_root is not None:
        project = jedi.Project(path=str(project_root.resolve()))
    script = jedi.Script(code=text, path=str(path), project=project)
    try:
        defs = script.goto(line, column, follow_imports=True)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": str(exc),
            "evidence": evidence("language_server_fact", tool="jedi", detail=str(exc)),
            "model_service_used": False,
        }
    ver = content_version(path)
    results = []
    for d in defs:
        mpath = d.module_path
        full = Path(mpath) if mpath else path
        results.append(
            {
                "name": d.name,
                "type": d.type,
                "description": d.description,
                "range": range_dict(
                    full,
                    d.line or 1,
                    d.column or 0,
                    d.line or 1,
                    (d.column or 0) + len(d.name or ""),
                    version=content_version(full) if full.is_file() else ver,
                ),
                "evidence": evidence(
                    "language_server_fact",
                    tool="jedi",
                    detail="jedi.Script.goto",
                ),
            }
        )
    return {
        "ok": True,
        "results": results,
        "query_version": ver,
        "model_service_used": False,
    }


def jedi_signatures(
    path: Path,
    line: int,
    column: int,
    *,
    project_root: Path | None = None,
) -> dict[str, Any]:
    if not jedi_available():
        return {
            "ok": False,
            "limitation": "jedi_not_installed",
            "evidence": evidence(
                "lexical_fallback",
                tool="none",
                limitation="jedi_not_installed",
            ),
            "model_service_used": False,
        }
    import jedi

    path = path.resolve()
    text = path.read_text(encoding="utf-8", errors="replace")
    project = jedi.Project(path=str(project_root.resolve())) if project_root else None
    script = jedi.Script(code=text, path=str(path), project=project)
    try:
        sigs = script.get_signatures(line, column)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "model_service_used": False}
    return {
        "ok": True,
        "signatures": [
            {
                "name": s.name,
                "description": str(s),
                "params": [p.to_string() for p in s.params],
                "evidence": evidence(
                    "language_server_fact",
                    tool="jedi",
                    detail="jedi.Script.get_signatures",
                ),
            }
            for s in sigs
        ],
        "query_version": content_version(path),
        "model_service_used": False,
    }
