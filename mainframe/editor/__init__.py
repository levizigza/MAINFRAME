"""Editor ↔ CLI shared task bridge (maintained extension preferred over Void fork)."""

from __future__ import annotations

from mainframe.editor.accept import run_editor_accept
from mainframe.editor.agent import run_agent_turn
from mainframe.editor.agent_accept import run_agent_ux_accept
from mainframe.editor.bridge import (
    apply_verified_patch,
    attach_selection,
    attach_unsaved_buffer,
    cancel_task,
    chat_to_task,
    propose_reviewable_diffs,
    reject_proposal,
    resume_task,
)
from mainframe.editor.eval_void import void_evaluation_summary
from mainframe.editor.until_green import run_until_green
from mainframe.editor.until_green_accept import run_until_green_accept

__all__ = [
    "apply_verified_patch",
    "attach_selection",
    "attach_unsaved_buffer",
    "cancel_task",
    "chat_to_task",
    "propose_reviewable_diffs",
    "reject_proposal",
    "resume_task",
    "run_agent_turn",
    "run_agent_ux_accept",
    "run_editor_accept",
    "run_until_green",
    "run_until_green_accept",
    "void_evaluation_summary",
]
