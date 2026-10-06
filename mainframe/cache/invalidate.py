"""Invalidate exact-cache entries on source, permission, or freshness changes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mainframe.cache import store
from mainframe.cache.keys import content_version, permission_version

CONTENT_BOUND_KINDS = (
    "repo_scan",
    "retrieval",
    "tool_output",
    "workflow_artifact",
    "model_response",
)


def invalidate_on_source_change(
    root: Path,
    *,
    previous_content_hash: str,
    kinds: list[str] | None = None,
) -> dict[str, Any]:
    """When sources change, drop content-bound exact entries for this project."""
    current = content_version(root)["content_hash"]
    changed = previous_content_hash != current
    removed = 0
    if changed:
        for kind in kinds or list(CONTENT_BOUND_KINDS):
            removed += store.delete_kind(root, kind)
    return {
        "ok": True,
        "reason": "source_change",
        "previous_content_hash": previous_content_hash,
        "current_content_hash": current,
        "changed": changed,
        "removed": removed,
    }


def invalidate_on_permission_change(
    root: Path,
    *,
    previous_permission_ver: str,
    new_permissions: dict[str, Any] | None = None,
    kinds: list[str] | None = None,
) -> dict[str, Any]:
    """Permission posture change invalidates entries keyed to the old version."""
    current = permission_version(new_permissions)
    changed = previous_permission_ver != current
    removed = 0
    if changed:
        target = kinds or list(CONTENT_BOUND_KINDS)
        for kind in target:
            for row in store.list_entries(root, kind=kind):
                if row["permission_ver"] == previous_permission_ver:
                    removed += store.delete_keys(root, [row["cache_key"]])
            # If nothing matched by ver (edge), clear kind
        if removed == 0:
            for kind in target:
                removed += store.delete_kind(root, kind)
    return {
        "ok": True,
        "reason": "permission_change",
        "previous_permission_ver": previous_permission_ver,
        "current_permission_ver": current,
        "changed": changed,
        "removed": removed,
    }


def invalidate_for_freshness(root: Path, *, kind: str | None = None) -> dict[str, Any]:
    """Freshness requirement: drop entries rather than treat them as current."""
    if kind:
        n = store.delete_kind(root, kind)
    else:
        n = store.delete_project(root)
    return {
        "ok": True,
        "reason": "freshness_required",
        "removed": n,
        "note": "Time-sensitive / freshness-required answers are never reused as current.",
    }
