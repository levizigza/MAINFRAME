"""Versioned workflow format — step kinds and JSON Schema-ish types."""

from __future__ import annotations

from typing import Any, Literal

FORMAT_VERSION = "1.0"

StepKind = Literal["deterministic", "ai", "human"]

STEP_KINDS: tuple[str, ...] = ("deterministic", "ai", "human")

AI_STEP_TYPES: tuple[str, ...] = ("extract", "classify", "summarize", "propose_code")

# Capabilities a step may declare — must be available at validation time.
KNOWN_CAPABILITIES: frozenset[str] = frozenset(
    {
        "local.read",
        "local.write",
        "local.exec_test",
        "local.artifact",
        "ai.infer",
        "human.decide",
        "network.denied",  # explicit denial is fine offline
    }
)


def empty_schema() -> dict[str, Any]:
    return {"type": "object", "properties": {}, "additionalProperties": True}


def normalize_workflow(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow-normalized copy with defaults applied."""
    wf = dict(raw)
    wf.setdefault("format_version", FORMAT_VERSION)
    wf.setdefault("id", "unnamed")
    wf.setdefault("inputs", empty_schema())
    wf.setdefault("outputs", empty_schema())
    wf.setdefault("permissions", [])
    wf.setdefault("artifacts", [])
    steps = []
    for s in wf.get("steps") or []:
        step = dict(s)
        step.setdefault("kind", "deterministic")
        step.setdefault("depends_on", [])
        step.setdefault("inputs", empty_schema())
        step.setdefault("outputs", empty_schema())
        step.setdefault("effects", [])
        step.setdefault("permissions", [])
        step.setdefault("retries", {"max": 0, "backoff_ms": 0})
        step.setdefault("timeout_ms", 30_000)
        step.setdefault("condition", None)
        step.setdefault("loop", None)
        if step.get("kind") == "ai":
            step.setdefault("ai_type", step.get("ai_type") or _infer_ai_type(step))
        steps.append(step)
    wf["steps"] = steps
    return wf


def _infer_ai_type(step: dict[str, Any]) -> str | None:
    handler = str(step.get("handler") or "")
    mapping = {
        "ai_extract": "extract",
        "ai_classify": "classify",
        "ai_summarize": "summarize",
        "ai_propose_code": "propose_code",
    }
    return mapping.get(handler)