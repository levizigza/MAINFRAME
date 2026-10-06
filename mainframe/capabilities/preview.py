"""Concrete previews before asking for external or irreversible actions."""

from __future__ import annotations

from typing import Any


def build_preview(
    *,
    hold_reason: str,
    capability: str,
    operation: str,
    destination: str | None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = payload or {}
    lines = [
        f"Capability: {capability}",
        f"Operation: {operation}",
        f"Destination: {destination or '(none)'}",
    ]
    if payload.get("paths"):
        lines.append(f"Paths: {payload['paths']}")
    if payload.get("subject"):
        lines.append(f"Subject: {payload['subject']}")
    if payload.get("body"):
        body = str(payload["body"])
        lines.append(f"Body preview: {body[:200]}{'…' if len(body) > 200 else ''}")

    return {
        "concrete": True,
        "hold_reason": hold_reason,
        "summary_text": "\n".join(lines),
        "decision_options": ["allow_once", "allow_and_add_destination", "deny"],
        "payload": payload,
    }
