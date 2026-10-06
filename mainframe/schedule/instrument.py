"""Instrumentation — prove zero model requests and no unintended outbound delivery."""

from __future__ import annotations

from typing import Any


def new_instrument(*, delivery_mode: str = "none") -> dict[str, Any]:
    return {
        "model_requests": 0,
        "agent_turn_started": False,
        "outbound_delivery_attempted": False,
        "outbound_delivery_mode": delivery_mode,
        "unintended_outbound": False,
        "governed_by_model_tool_approvals": False,
        "execution_path": "deterministic_command_payload",
    }


def assert_clean(instrument: dict[str, Any]) -> dict[str, Any]:
    ok = (
        instrument.get("model_requests", 1) == 0
        and instrument.get("agent_turn_started") is False
        and instrument.get("outbound_delivery_attempted") is False
        and instrument.get("unintended_outbound") is False
    )
    return {"ok": ok, "instrument": instrument}
