"""Triggers — file/repo/webhook/poll via OpenClaw-compatible scheduler bindings."""

from __future__ import annotations

from mainframe.triggers.accept import run_triggers_accept

__all__ = ["run_triggers_accept"]
