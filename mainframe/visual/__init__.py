"""Optional removable visual bridge for FreeForge workflows (simple local form)."""

from __future__ import annotations

from mainframe.visual.accept import run_visual_accept
from mainframe.visual.bridge import bridge_status
from mainframe.visual.eval_nodered import evaluate_nodered_optional

__all__ = [
    "bridge_status",
    "evaluate_nodered_optional",
    "run_visual_accept",
]
