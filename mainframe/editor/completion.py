"""Budgeted completion — only when an eligible local model is available."""

from __future__ import annotations

from typing import Any

from mainframe.ai import probe_free_inference
from mainframe.eligibility import decide_provider


def completion_gate(*, requested: bool = False) -> dict[str, Any]:
    if not requested:
        return {
            "enabled": False,
            "reason": "completion_not_requested",
            "eligible_model": False,
            "budgeted": True,
        }
    decision = decide_provider("ollama_local", endpoint="http://127.0.0.1:11434")
    probe = probe_free_inference()
    pd = probe.to_dict() if hasattr(probe, "to_dict") else {}
    model_ready = pd.get("status") == "available"
    if not decision.eligible or not model_ready:
        return {
            "enabled": False,
            "reason": "no_eligible_local_model" if decision.eligible else "provider_not_eligible",
            "eligible_model": False,
            "budgeted": True,
            "decision": decision.to_dict(),
            "probe": {"status": pd.get("status"), "detail": pd.get("detail")},
            "note": "Completion UX disabled until an eligible local model is present.",
        }
    return {
        "enabled": True,
        "reason": "eligible_local_model",
        "eligible_model": True,
        "budgeted": True,
        "max_tokens_default": 64,
    }
