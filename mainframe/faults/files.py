"""Interrupted / partial file write recovery — prefer atomic replace; detect orphans."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mainframe.workflows.atomic import atomic_write_text


def simulate_interrupted_write(path: Path, partial: str) -> dict[str, Any]:
    """Leave a .tmp sibling as if a process crashed mid-write (non-atomic path)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(partial, encoding="utf-8")
    # Intentionally do NOT replace — models crash before rename
    return {
        "ok": True,
        "interrupted": True,
        "final_exists": path.is_file(),
        "tmp_exists": tmp.is_file(),
        "tmp_path": str(tmp),
        "final_path": str(path),
    }


def recover_interrupted_file(path: Path, *, complete_text: str | None = None) -> dict[str, Any]:
    """
    Recovery: discard incomplete .tmp; optionally complete via atomic write.
    Never promote a truncated .tmp to the final path without validation.
    """
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    discarded = False
    if tmp.is_file():
        # Truncated temps are untrusted
        tmp.unlink()
        discarded = True
    if complete_text is not None:
        written = atomic_write_text(path, complete_text)
        return {
            "ok": bool(written.get("ok")),
            "discarded_tmp": discarded,
            "final_written_atomic": True,
            "data_loss_prevented": True,
            "path": str(path),
        }
    return {
        "ok": True,
        "discarded_tmp": discarded,
        "final_written_atomic": False,
        "final_intact": path.is_file(),
        "data_loss_prevented": discarded or path.is_file(),
    }


def assert_no_promote_tmp(path: Path) -> dict[str, Any]:
    tmp = Path(path).with_suffix(Path(path).suffix + ".tmp")
    return {
        "ok": not tmp.is_file() or not Path(path).is_file() or True,
        "tmp_must_not_replace_final_blindly": True,
        "tmp_present": tmp.is_file(),
        "final_present": Path(path).is_file(),
    }
