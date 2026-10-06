"""Editor ↔ CLI shared task bridge (maintained extension preferred over Void fork)."""

from __future__ import annotations

from mainframe.editor.accept import run_editor_accept
from mainframe.editor.bridge import (
    apply_verified_patch,
    attach_selection,
    attach_unsaved_buffer,
    cancel_task,
    chat_to_task,
    propose_reviewable_diffs,
    resume_task,
)
from mainframe.editor.eval_void import void_evaluation_summary

__all__ = [
    "apply_verified_patch",
    "attach_selection",
    "attach_unsaved_buffer",
    "cancel_task",
    "chat_to_task",
    "propose_reviewable_diffs",
    "resume_task",
    "run_editor_accept",
    "void_evaluation_summary",
]
