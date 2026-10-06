"""Bounded agent tools: overview + file-range (no full-repo prompt dump)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mainframe.cost_gate import authorize
from mainframe.inventory.store import connect, load_summary, root_key

MAX_RANGE_LINES = 80
MAX_OVERVIEW_LIST = 40


def overview(root: Path) -> dict[str, Any]:
    """Bounded inventory overview for agents — hashes/provenance summaries only."""
    gate = authorize("tool", "local.inventory_overview", local=True)
    if not gate.allowed:
        return {"ok": False, "cost_gate": gate.to_dict()}

    root = root.resolve()
    conn = connect(root)
    summary = load_summary(conn, root_key(root))
    conn.close()
    if not summary:
        return {"ok": False, "error": "no_inventory_scan_yet", "hint": "run inventory scan first"}

    def bound(items: list[Any]) -> list[Any]:
        return items[:MAX_OVERVIEW_LIST]

    return {
        "ok": True,
        "bounded": True,
        "max_list": MAX_OVERVIEW_LIST,
        "file_count": summary.get("file_count"),
        "languages": summary.get("languages"),
        "kinds": summary.get("kinds"),
        "packages": bound(summary.get("packages") or []),
        "source_roots": summary.get("source_roots"),
        "entry_points": bound(summary.get("entry_points") or []),
        "tests": bound(summary.get("tests") or []),
        "generated": bound(summary.get("generated") or []),
        "dependencies": bound(summary.get("dependencies") or []),
        "build_config": bound(summary.get("build_config") or []),
        "privacy_excluded_count": summary.get("privacy_excluded_count"),
        "untracked_count": len(summary.get("untracked") or []),
        "embedding_service_used": summary.get("embedding_service_used", False),
        "model_request_used": summary.get("model_request_used", False),
        "note": "Overview omits file bodies; use file-range for bounded slices.",
    }


def file_range(root: Path, rel: str, start_line: int = 1, end_line: int | None = None) -> dict[str, Any]:
    """Return a bounded line range for one file (privacy excluded paths denied)."""
    gate = authorize("tool", "local.inventory_file_range", local=True)
    if not gate.allowed:
        return {"ok": False, "cost_gate": gate.to_dict()}

    from mainframe.inventory.ignore import is_privacy_excluded

    rel_posix = rel.replace("\\", "/")
    if is_privacy_excluded(rel_posix):
        return {"ok": False, "error": "privacy_excluded", "path": rel_posix}

    path = (root.resolve() / rel_posix).resolve()
    if not str(path).startswith(str(root.resolve())):
        return {"ok": False, "error": "path_escape"}
    if not path.is_file():
        return {"ok": False, "error": "not_found", "path": rel_posix}
    if path.is_symlink():
        return {"ok": False, "error": "symlink_not_inlined", "path": rel_posix}

    start_line = max(1, int(start_line))
    if end_line is None:
        end_line = start_line + MAX_RANGE_LINES - 1
    end_line = int(end_line)
    if end_line < start_line:
        return {"ok": False, "error": "invalid_range"}
    if end_line - start_line + 1 > MAX_RANGE_LINES:
        end_line = start_line + MAX_RANGE_LINES - 1

    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    slice_lines = lines[start_line - 1 : end_line]
    return {
        "ok": True,
        "path": rel_posix,
        "start_line": start_line,
        "end_line": start_line + len(slice_lines) - 1 if slice_lines else start_line - 1,
        "max_range_lines": MAX_RANGE_LINES,
        "lines": slice_lines,
        "truncated": len(lines) > end_line,
        "total_lines": len(lines),
        "duplicated_whole_repo": False,
    }
