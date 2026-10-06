"""Cross-project isolation — retrieval, browser sessions, paths, tokens."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mainframe.boundaries.paths import resolve_under_root
from mainframe.projects.registry import get_project, project_home, safe_project_id


def refuse_cross_project_retrieval(
    *,
    requester_project_id: str,
    resource_project_id: str,
    resource_kind: str = "memory",
) -> dict[str, Any]:
    try:
        a = safe_project_id(requester_project_id)
        b = safe_project_id(resource_project_id)
    except ValueError as exc:
        return {"ok": False, "allowed": False, "error": str(exc), "exposed": False}
    if a != b:
        return {
            "ok": True,
            "allowed": False,
            "exposed": False,
            "error": "cross_project_retrieval_denied",
            "requester_project_id": a,
            "resource_project_id": b,
            "resource_kind": resource_kind,
            "data_returned": None,
        }
    return {
        "ok": True,
        "allowed": True,
        "exposed": False,
        "requester_project_id": a,
        "resource_project_id": b,
        "resource_kind": resource_kind,
    }


def refuse_reused_browser_session(
    *,
    session_project_id: str | None,
    requester_project_id: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    """A browser session owned by project A must not be usable by project B."""
    if not session_project_id:
        return {
            "ok": True,
            "allowed": False,
            "exposed": False,
            "error": "session_missing_project_binding",
            "session_id": session_id,
        }
    gate = refuse_cross_project_retrieval(
        requester_project_id=requester_project_id,
        resource_project_id=session_project_id,
        resource_kind="browser_session",
    )
    if not gate.get("allowed"):
        return {
            **gate,
            "error": "reused_browser_session_denied",
            "session_id": session_id,
            "cookies_or_storage_exposed": False,
        }
    return {**gate, "session_id": session_id, "cookies_or_storage_exposed": False}


def resolve_project_path(
    project_id: str,
    user_path: str | Path,
    *,
    area: str = "artifacts",
) -> dict[str, Any]:
    """
    Resolve a path under the project's area. Malicious references
    (``..``, absolute escapes, other project homes) are denied.
    """
    rec = get_project(project_id)
    if not rec:
        return {"ok": False, "allowed": False, "error": "project_not_found", "exposed": False}

    home = project_home(project_id)
    area_root = Path(rec.get("paths", {}).get(area) or (home / area))
    # Also refuse paths that target another project's home even if somehow joined
    result = resolve_under_root(area_root, user_path)
    if not result.get("allowed"):
        return {
            **result,
            "exposed": False,
            "error": result.get("error") or "malicious_path_reference_denied",
            "project_id": rec["project_id"],
            "area": area,
        }

    # Extra: deny if resolved path sits under a different project home
    projects_parent = home.parent
    resolved = Path(result["resolved"])
    try:
        rel = resolved.relative_to(projects_parent)
        other = rel.parts[0] if rel.parts else ""
        if other and other != rec["project_id"]:
            return {
                "ok": False,
                "allowed": False,
                "exposed": False,
                "error": "path_targets_other_project",
                "project_id": rec["project_id"],
                "other_project": other,
            }
    except ValueError:
        # Outside projects tree entirely — already should have been denied by area root
        if not str(resolved).startswith(str(area_root.resolve())):
            return {
                "ok": False,
                "allowed": False,
                "exposed": False,
                "error": "path_outside_project_area",
                "project_id": rec["project_id"],
            }

    return {
        **result,
        "exposed": False,
        "project_id": rec["project_id"],
        "area": area,
    }


def isolate_memory_put_get(
    *,
    project_id: str,
    other_project_id: str,
    secret_body: str,
) -> dict[str, Any]:
    """Demonstrate memory keyed by project cannot be read cross-project."""
    from mainframe.memory.store import remember, retrieve
    from mainframe.projects.registry import project_home

    home_a = project_home(project_id)
    ws_a = Path((get_project(project_id) or {}).get("workspace") or (home_a / "workspace"))
    ws_a.mkdir(parents=True, exist_ok=True)
    # Store under A's workspace key
    put = remember(
        ws_a,
        kind="note",
        source_class="user",
        title="project_secret_marker",
        body=secret_body,
        verification_status="verified",
    )
    # Retrieve as B
    home_b = project_home(other_project_id)
    ws_b = Path((get_project(other_project_id) or {}).get("workspace") or (home_b / "workspace"))
    ws_b.mkdir(parents=True, exist_ok=True)
    got = retrieve(ws_b, query="project_secret_marker", limit=20)
    entries = got.get("items") or []
    leaked = any(secret_body in str(e.get("body") or "") or secret_body in str(e) for e in entries)
    cross = refuse_cross_project_retrieval(
        requester_project_id=other_project_id,
        resource_project_id=project_id,
        resource_kind="memory",
    )
    return {
        "ok": True,
        "put_ok": bool(put.get("ok")),
        "cross_allowed": bool(cross.get("allowed")),
        "leaked": leaked,
        "exposed": leaked,
        "entries_seen_by_other": len(entries),
    }
