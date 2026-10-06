"""Local notifications by default; OpenClaw messaging channels gated off."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.config import STATE_DIR, ensure_state
from mainframe.schedule.openclaw_payload import SCHEDULER_OWNER


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def notify_policy() -> dict[str, Any]:
    return {
        "default_channel": "local_inbox",
        "openclaw_messaging_enabled": False,
        "automatic_outbound_delivery": False,
        "inherited_auto_deliver_disabled": True,
        "scheduler_owner": SCHEDULER_OWNER,
        "openclaw_channel_requirements": [
            "verify_account_fees_zero_or_eligible",
            "verify_connector_behavior",
            "verify_recipient_authorization",
            "verify_disclosure_scope",
        ],
        "note": (
            "OpenClaw announce/webhook channels stay disabled until fees, connector "
            "behavior, recipient authorization, and disclosure scope are verified. "
            "Schedule payloads continue to use --no-deliver by default."
        ),
    }


def local_inbox_path() -> Path:
    ensure_state()
    p = STATE_DIR / "notifications" / "inbox.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def send_local_notification(
    *,
    title: str,
    body: str,
    task_id: str | None = None,
    kind: str = "info",
) -> dict[str, Any]:
    """Append to local inbox only — never triggers work re-execution or outbound send."""
    policy = notify_policy()
    entry = {
        "at": _utc(),
        "title": title,
        "body": body,
        "task_id": task_id,
        "kind": kind,
        "channel": "local_inbox",
        "outbound": False,
        "rerun_work": False,
    }
    path = local_inbox_path()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    return {
        "ok": True,
        "delivered": True,
        "channel": "local_inbox",
        "path": str(path),
        "entry": entry,
        "policy": policy,
        "side_effects": {"work_rerun": False, "outbound_message": False},
    }


def refuse_openclaw_outbound(
    *,
    destination: str | None = None,
    reason: str = "openclaw_messaging_not_verified",
) -> dict[str, Any]:
    return {
        "ok": False,
        "refused": True,
        "error": reason,
        "destination": destination,
        "outbound_attempted": False,
        "work_rerun": False,
        "policy": notify_policy(),
        "note": "Notification failure or refusal must not rerun completed work or retarget delivery.",
    }


def notify_failure_safe(*, task_id: str | None, prior_apply_ok: bool) -> dict[str, Any]:
    """Simulate notification channel failure — must not rerun work or change destination."""
    local = send_local_notification(
        title="Notification channel unavailable",
        body="Kept local inbox only. Completed work was not re-run. No alternate destination used.",
        task_id=task_id,
        kind="notify_failure",
    )
    return {
        "ok": True,
        "notification_failed_externally": True,
        "fallback": "local_inbox",
        "work_rerun": False,
        "unintended_destination": False,
        "prior_apply_preserved": prior_apply_ok,
        "local": local,
        "openclaw_outbound": refuse_openclaw_outbound(destination="any"),
    }
