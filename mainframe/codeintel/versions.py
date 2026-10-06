"""Attach file path, range, and content version to codeintel results."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def content_version(path: Path) -> dict[str, Any]:
    try:
        data = path.read_bytes()
        st = path.stat()
        return {
            "path": str(path).replace("\\", "/"),
            "sha256": hashlib.sha256(data).hexdigest(),
            "mtime_ns": getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)),
            "size_bytes": st.st_size,
        }
    except OSError as exc:
        return {
            "path": str(path).replace("\\", "/"),
            "sha256": None,
            "mtime_ns": None,
            "size_bytes": None,
            "error": str(exc),
        }


def range_dict(
    path: Path | str,
    start_line: int,
    start_col: int,
    end_line: int | None = None,
    end_col: int | None = None,
    *,
    version: dict[str, Any] | None = None,
) -> dict[str, Any]:
    p = Path(path)
    return {
        "path": str(p).replace("\\", "/"),
        "start_line": start_line,
        "start_col": start_col,
        "end_line": end_line if end_line is not None else start_line,
        "end_col": end_col if end_col is not None else start_col,
        "content_version": version or (content_version(p) if p.is_file() else None),
    }
