"""Validate edit batches before any write; produce reviewable diffs."""

from __future__ import annotations

import difflib
import hashlib
from pathlib import Path
from typing import Any

from mainframe.patching.io_preserve import read_preserved
from mainframe.patching.snapshot import load_snapshot, verify_against_disk


def validate_batch(
    root: Path,
    edits: list[dict[str, Any]],
    *,
    snapshot_id: str,
    scope_paths: list[str] | None = None,
) -> dict[str, Any]:
    """
    Validate all edits against the base snapshot and current disk.

    Rejects: path escape, out-of-scope, stale hash, missing old, ambiguous
    (non-unique) replacements. Does not write.
    """
    root = root.resolve()
    snap = load_snapshot(snapshot_id)
    if not snap:
        return {"ok": False, "error": "unknown_snapshot", "snapshot_id": snapshot_id}

    drift = verify_against_disk(root, snap)
    if not drift["ok"]:
        return {
            "ok": False,
            "error": "stale_patch_or_concurrent_edit",
            "detail": drift,
            "hint": "Files changed after inspection; refusing to guess",
        }

    scope = set(p.replace("\\", "/") for p in (scope_paths or snap.get("paths") or []))
    planned: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for i, edit in enumerate(edits):
        rel = str(edit.get("path", "")).replace("\\", "/")
        old = edit.get("old")
        new = edit.get("new")
        expect = edit.get("content_sha256") or (snap.get("files") or {}).get(rel, {}).get("sha256")

        if not rel or old is None or new is None:
            errors.append({"index": i, "error": "missing_path_or_old_or_new"})
            continue
        if scope and rel not in scope:
            errors.append({"index": i, "path": rel, "error": "path_out_of_scope"})
            continue
        path = (root / rel).resolve()
        if not str(path).startswith(str(root)):
            errors.append({"index": i, "path": rel, "error": "path_escape"})
            continue
        if not path.is_file():
            errors.append({"index": i, "path": rel, "error": "missing_file"})
            continue

        fb = read_preserved(path)
        actual = hashlib.sha256(fb.raw).hexdigest()
        if expect and actual != expect:
            errors.append(
                {
                    "index": i,
                    "path": rel,
                    "error": "stale_hash",
                    "expected": expect,
                    "actual": actual,
                }
            )
            continue

        count = fb.text.count(old)
        if count == 0:
            errors.append({"index": i, "path": rel, "error": "old_text_not_found"})
            continue
        if count > 1:
            errors.append(
                {
                    "index": i,
                    "path": rel,
                    "error": "ambiguous_replacement",
                    "matches": count,
                    "hint": "Duplicate code blocks — refuse guessing; narrow old text",
                }
            )
            continue

        after = fb.text.replace(old, new, 1)
        diff = "".join(
            difflib.unified_diff(
                fb.text.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=f"a/{rel}",
                tofile=f"b/{rel}",
            )
        )
        planned.append(
            {
                "index": i,
                "path": rel,
                "content_sha256": actual,
                "encoding": fb.encoding,
                "newline": fb.newline,
                "unified_diff": diff,
                "old": old,
                "new": new,
            }
        )

    return {
        "ok": len(errors) == 0,
        "snapshot_id": snapshot_id,
        "planned": planned,
        "errors": errors,
        "filesystem_atomicity_claimed": False,
        "writes_executed": False,
    }
