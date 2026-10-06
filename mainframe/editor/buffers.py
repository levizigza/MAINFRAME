"""Preserve unsaved editor buffers in task state — never clobber dirty user text."""

from __future__ import annotations

from typing import Any

from mainframe.editor.state import content_fingerprint


def upsert_buffer(
    task: dict[str, Any],
    *,
    path: str,
    text: str,
    dirty: bool,
    version: int | None = None,
) -> dict[str, Any]:
    ctx = dict(task.get("context") or {})
    buffers = dict(ctx.get("buffers") or {})
    buffers[path.replace("\\", "/")] = {
        "text": text,
        "dirty": bool(dirty),
        "version": version,
        "sha256": content_fingerprint(text),
        "preserved": True,
    }
    ctx["buffers"] = buffers
    task["context"] = ctx
    return task


def get_buffer_text(task: dict[str, Any], path: str) -> str | None:
    buffers = (task.get("context") or {}).get("buffers") or {}
    key = path.replace("\\", "/")
    entry = buffers.get(key)
    if not entry:
        return None
    return entry.get("text")


def dirty_paths(task: dict[str, Any]) -> list[str]:
    buffers = (task.get("context") or {}).get("buffers") or {}
    return [p for p, b in buffers.items() if b.get("dirty")]


def apply_uses_buffer_base(task: dict[str, Any], path: str, disk_text: str) -> dict[str, Any]:
    """
    When the editor has an unsaved buffer, patch validation/apply must use buffer
    text as the base — never overwrite unsaved user edits with disk-only apply.
    """
    buf = get_buffer_text(task, path)
    if buf is None:
        return {"base": disk_text, "source": "disk", "dirty": False}
    entry = ((task.get("context") or {}).get("buffers") or {}).get(path.replace("\\", "/")) or {}
    return {
        "base": buf,
        "source": "unsaved_buffer",
        "dirty": bool(entry.get("dirty")),
        "sha256": entry.get("sha256"),
        "disk_diverges": buf != disk_text,
    }
