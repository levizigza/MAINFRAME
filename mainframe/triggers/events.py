"""Typed trigger event records — source, timestamp, dedupe key, permission scope."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

EventSource = Literal[
    "file_change",
    "repository_change",
    "local_webhook",
    "bounded_poll",
    "manual",
]

TRIGGER_SOURCES: tuple[str, ...] = (
    "file_change",
    "repository_change",
    "local_webhook",
    "bounded_poll",
    "manual",
)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_dedupe_key(*, source: str, identity: str, content_fingerprint: str = "") -> str:
    raw = f"{source}|{identity}|{content_fingerprint}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def normalize_event(
    *,
    source: EventSource | str,
    identity: str,
    permission_scope: str,
    payload: dict[str, Any] | None = None,
    content_fingerprint: str = "",
    timestamp: str | None = None,
    binding_id: str | None = None,
) -> dict[str, Any]:
    """Normalize an inbound signal into a typed event record."""
    if source not in TRIGGER_SOURCES:
        raise ValueError(f"unknown_event_source:{source}")
    payload = dict(payload or {})
    # Events never carry an executable command — only binding_id may select work.
    payload.pop("command", None)
    payload.pop("argv", None)
    payload.pop("command_argv", None)
    dedupe = make_dedupe_key(
        source=source,
        identity=identity,
        content_fingerprint=content_fingerprint or json.dumps(payload, sort_keys=True)[:200],
    )
    return {
        "event_id": f"evt_{dedupe[:12]}",
        "source": source,
        "timestamp": timestamp or _utc(),
        "dedupe_key": dedupe,
        "permission_scope": permission_scope,
        "identity": identity,
        "binding_id": binding_id,
        "payload": payload,
        "content_fingerprint": content_fingerprint,
    }
