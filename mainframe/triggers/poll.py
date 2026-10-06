"""Bounded polling + manual triggers when inbound internet is unavailable."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from mainframe.triggers.events import normalize_event
from mainframe.triggers.webhook import PUBLIC_TUNNEL_TRADEOFF


def explain_inbound_tradeoff(*, inbound_available: bool) -> dict[str, Any]:
    if inbound_available:
        return {
            "mode": "local_webhook_loopback",
            "publicly_reachable": False,
            "note": "Webhook remains loopback-bound even when the host has internet.",
            "tradeoff": PUBLIC_TUNNEL_TRADEOFF,
        }
    return {
        "mode": "bounded_poll_or_manual",
        "publicly_reachable": False,
        "paid_tunnel_required": False,
        "tradeoff": (
            "Inbound internet / public ingress unavailable or unused. "
            "FreeForge supports an eligible bounded poll of a local/loopback source, "
            "or a manual trigger. A loopback webhook is never claimed as public."
        ),
        "scheduler_mapping": {
            "bounded_poll": "openclaw automations --every <interval> + --command-argv",
            "manual": "openclaw automations run <job-id> or FreeForge schedule fire",
        },
    }


def bounded_poll_source(
    *,
    path: Path,
    binding_id: str,
    permission_scope: str,
    last_fingerprint: str | None = None,
    max_bytes: int = 64 * 1024,
) -> dict[str, Any]:
    """
    Poll a local eligible source (file on disk / loopback artifact).
    Bounded: size cap; no remote crawl.
    """
    if not path.is_file():
        return {"emitted": False, "reason": "source_missing", "tradeoff": explain_inbound_tradeoff(inbound_available=False)}
    size = path.stat().st_size
    if size > max_bytes:
        return {"emitted": False, "reason": "source_too_large", "bytes": size, "max": max_bytes}
    data = path.read_bytes()
    fp = hashlib.sha256(data).hexdigest()[:24]
    if last_fingerprint and fp == last_fingerprint:
        return {"emitted": False, "reason": "unchanged", "fingerprint": fp}
    event = normalize_event(
        source="bounded_poll",
        identity=str(path.name),
        permission_scope=permission_scope,
        content_fingerprint=fp,
        binding_id=binding_id,
        payload={"path": str(path), "bytes": size},
    )
    return {
        "emitted": True,
        "event": event,
        "fingerprint": fp,
        "tradeoff": explain_inbound_tradeoff(inbound_available=False),
    }


def manual_trigger(
    *,
    binding_id: str,
    permission_scope: str,
    note: str = "operator_manual",
) -> dict[str, Any]:
    event = normalize_event(
        source="manual",
        identity=note,
        permission_scope=permission_scope,
        content_fingerprint=hashlib.sha256(f"{binding_id}:{note}".encode()).hexdigest()[:24],
        binding_id=binding_id,
        payload={"note": note},
    )
    return {
        "emitted": True,
        "event": event,
        "tradeoff": explain_inbound_tradeoff(inbound_available=False),
    }
