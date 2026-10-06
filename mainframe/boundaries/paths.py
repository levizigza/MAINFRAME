"""Filesystem path boundaries — traversal and symlink escape denied."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_under_root(
    root: Path,
    user_path: str | Path,
    *,
    follow_symlinks: bool = True,
) -> dict[str, Any]:
    """
    Resolve a user-supplied path and require the final target stay under root.

    Path traversal (``..``) and symlink escapes that land outside root are denied.
    """
    root = root.resolve()
    raw = Path(user_path)
    # Join then resolve — catches .. and symlink targets when follow_symlinks
    candidate = (root / raw).resolve() if not raw.is_absolute() else raw.resolve()

    if follow_symlinks:
        final = candidate
        # If the path itself is a symlink, resolve again
        try:
            if (root / raw).exists() or candidate.exists():
                final = Path(os.path.realpath(candidate))
        except OSError as exc:
            return {
                "ok": False,
                "allowed": False,
                "error": "resolve_failed",
                "detail": str(exc),
                "boundary": "filesystem_paths",
            }
    else:
        final = candidate

    allowed = _is_relative_to(final, root)
    return {
        "ok": allowed,
        "allowed": allowed,
        "root": str(root),
        "requested": str(user_path).replace("\\", "/"),
        "resolved": str(final),
        "boundary": "filesystem_paths",
        "enforced": True,
        "error": None if allowed else "path_outside_root_or_escape",
    }


def assert_no_symlink_escape(root: Path, link_path: Path) -> dict[str, Any]:
    """If link_path is a symlink, its real target must remain under root."""
    root = root.resolve()
    link_path = Path(link_path)
    if not link_path.exists() and not link_path.is_symlink():
        return {"ok": False, "allowed": False, "error": "missing", "boundary": "filesystem_paths"}
    if not link_path.is_symlink():
        return {
            "ok": True,
            "allowed": True,
            "symlink": False,
            "boundary": "filesystem_paths",
            "enforced": True,
        }
    target = Path(os.path.realpath(link_path))
    allowed = _is_relative_to(target, root)
    return {
        "ok": allowed,
        "allowed": allowed,
        "symlink": True,
        "link": str(link_path),
        "target": str(target),
        "root": str(root),
        "boundary": "filesystem_paths",
        "enforced": True,
        "error": None if allowed else "symlink_escape",
    }
