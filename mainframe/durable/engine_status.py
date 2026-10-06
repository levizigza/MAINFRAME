"""Selected-engine status API — supported polling; WebSocket is not a replay log."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.config import STATE_DIR, ensure_state
from mainframe.freeforge import SELECTED_ENGINE

# In-memory + durable engine status ledger used as the *supported status API*
# stand-in for openclaw_embedded_agent_runtime in offline acceptance.
ENGINE_STATUS_DB = STATE_DIR / "durable_engine_status.json"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> dict[str, Any]:
    ensure_state()
    if not ENGINE_STATUS_DB.is_file():
        return {"engine": SELECTED_ENGINE, "operations": {}}
    return json.loads(ENGINE_STATUS_DB.read_text(encoding="utf-8"))


def _save(data: dict[str, Any]) -> None:
    ensure_state()
    ENGINE_STATUS_DB.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def websocket_policy() -> dict[str, Any]:
    return {
        "assume_websocket_replays_missed_events": False,
        "reason": (
            "Do not assume a WebSocket event stream replays missed events after "
            "restart or connection gaps. Reconcile via supported status APIs."
        ),
        "supported_recovery": "status_api_poll",
    }


def publish_engine_status(
    operation_id: str,
    *,
    status: str,
    effect_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Engine-side status record (what a status API would return)."""
    data = _load()
    ops = data.setdefault("operations", {})
    ops[operation_id] = {
        "operation_id": operation_id,
        "engine": SELECTED_ENGINE,
        "status": status,
        "effect_id": effect_id,
        "detail": detail or {},
        "updated_at": _utc(),
    }
    _save(data)
    return ops[operation_id]


def query_engine_status(operation_id: str) -> dict[str, Any]:
    """Supported status API — poll after restart / timeout / connection gap."""
    data = _load()
    row = (data.get("operations") or {}).get(operation_id)
    if not row:
        return {
            "ok": True,
            "found": False,
            "operation_id": operation_id,
            "engine": SELECTED_ENGINE,
            "status": "unknown",
            "websocket_assumed": False,
            "policy": websocket_policy(),
        }
    return {
        "ok": True,
        "found": True,
        "engine": SELECTED_ENGINE,
        "websocket_assumed": False,
        "policy": websocket_policy(),
        **row,
    }


def clear_engine_status_for_tests() -> None:
    if ENGINE_STATUS_DB.is_file():
        ENGINE_STATUS_DB.unlink()
