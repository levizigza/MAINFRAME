"""Task contract shape — desired behavior, scope, checks, side effects, questions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

RequestKind = Literal[
    "explanation",
    "repair",
    "feature",
    "refactor",
    "ui",
    "automation",
    "unknown",
]


@dataclass
class TaskContract:
    """Machine-usable contract with retained natural-language intent for humans."""

    intent_natural_language: str
    kind: RequestKind
    desired_behavior: str
    scope: dict[str, Any]
    constraints: list[str] = field(default_factory=list)
    invariants: list[dict[str, Any]] = field(default_factory=list)
    acceptance_checks: list[dict[str, Any]] = field(default_factory=list)
    permitted_side_effects: list[str] = field(default_factory=list)
    unresolved_questions: list[dict[str, Any]] = field(default_factory=list)
    assumptions: list[dict[str, Any]] = field(default_factory=list)
    classification: dict[str, Any] = field(default_factory=dict)
    workflow_id: str | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    executable_assertions: list[dict[str, Any]] = field(default_factory=list)
    status: str = "ready"  # ready | needs_clarification | blocked
    model_service_used: bool = False
    separate_label_call: bool = False  # must remain False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


CONTRACT_FIELDS = (
    "desired_behavior",
    "scope",
    "constraints",
    "invariants",
    "acceptance_checks",
    "permitted_side_effects",
    "unresolved_questions",
)
