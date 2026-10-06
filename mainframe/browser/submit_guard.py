"""Hold external form submissions until capability authorization."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from mainframe.capabilities.authorize import authorize_action
from mainframe.capabilities.store import CapabilityStore


def guard_external_submission(
    store: CapabilityStore,
    *,
    project_id: str,
    form_action: str,
    capability: str = "sending_messages",
    operation: str = "send_report",
) -> dict[str, Any]:
    parsed = urlparse(form_action)
    if parsed.scheme in ("file", "") or parsed.hostname in (None, "localhost", "127.0.0.1"):
        return {"allowed": True, "external": False, "paused": False}
    destination = form_action
    decision = authorize_action(
        store,
        project_id=project_id,
        capability=capability,
        operation=operation,
        destination=destination,
        payload={"form_action": form_action},
    )
    return {
        "external": True,
        "allowed": bool(decision.get("allowed")),
        "paused": bool(decision.get("held") or decision.get("prompt")),
        "held": bool(decision.get("held")),
        "requires_specific_decision": bool(decision.get("requires_specific_decision")),
        "preview": decision.get("preview"),
        "decision": decision,
    }
