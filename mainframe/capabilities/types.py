"""Scoped capability kinds and operation labels."""

from __future__ import annotations

from typing import Literal

CapabilityKind = Literal[
    "reading",
    "editing",
    "running_tests",
    "browsing",
    "sending_messages",
    "publishing",
    "deletion",
]

ALL_CAPABILITIES: tuple[str, ...] = (
    "reading",
    "editing",
    "running_tests",
    "browsing",
    "sending_messages",
    "publishing",
    "deletion",
)

# Local reversible operations — no repeated confirmation when in grant scope.
LOCAL_REVERSIBLE_OPS: frozenset[str] = frozenset(
    {
        "read_file",
        "edit_file",
        "run_tests",
        "browse_local",
    }
)

DESTRUCTIVE_OPS: frozenset[str] = frozenset(
    {
        "delete_paths",
        "delete_all",
        "wipe",
    }
)

EXTERNAL_OPS: frozenset[str] = frozenset(
    {
        "send_report",
        "send_message",
        "publish",
        "publish_all",
    }
)
