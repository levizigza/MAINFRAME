"""Extract stable steps/parameters; drop removable model decisions; keep semantic AI/human."""

from __future__ import annotations

from typing import Any

from mainframe.promote.types import PromotedProgram, TaskTrace, TraceStep


def extract_promotion(trace: TaskTrace) -> dict[str, Any]:
    if not trace.accepted:
        return {"ok": False, "error": "trace_not_accepted"}

    kept: list[dict[str, Any]] = []
    frozen: dict[str, Any] = {}
    removed: list[dict[str, Any]] = []
    model_remaining = 0

    for step in trace.steps:
        # Fold removable AI parameters into frozen set, then skip the AI step
        if step.kind == "ai" and step.removable and not step.genuinely_semantic:
            frozen.update(step.parameters_frozen)
            removed.append(
                {
                    "id": step.id,
                    "handler": step.handler,
                    "model_calls_removed": step.model_calls,
                    "reason": step.note or "unnecessary_model_decision",
                }
            )
            continue

        entry = {
            "id": step.id,
            "kind": step.kind,
            "handler": step.handler,
            "args": {**step.args, **step.parameters_frozen},
            "genuinely_semantic": step.genuinely_semantic,
            "model_calls": 0 if step.removable else step.model_calls,
        }
        if step.kind == "ai" and step.genuinely_semantic:
            entry["model_calls"] = step.model_calls
            model_remaining += step.model_calls
            entry["note"] = "Kept as explicit AI step — genuine semantic decision."
        if step.kind == "human":
            entry["note"] = step.note or "Explicit human step."
        frozen.update(step.parameters_frozen)
        kept.append(entry)

    # Apply frozen title etc. into deterministic step args
    if "title" in frozen:
        for s in kept:
            if s["handler"] == "transform_report":
                s["args"]["title"] = frozen["title"]

    avoided = trace.model_calls_total - model_remaining
    return {
        "ok": True,
        "steps": kept,
        "removed_steps": removed,
        "frozen_parameters": frozen,
        "model_calls_in_source": trace.model_calls_total,
        "model_calls_in_program": model_remaining,
        "model_calls_avoided": avoided,
        "supported_conditions": dict(trace.supported_conditions_hint),
        "permissions": list(trace.permissions),
    }
