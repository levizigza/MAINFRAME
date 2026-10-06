"""Types for task traces and promoted deterministic programs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

TrustState = Literal["untrusted", "reviewed", "tested", "accepted"]
StepKind = Literal["deterministic", "ai", "human"]


@dataclass
class TraceStep:
    id: str
    kind: StepKind
    handler: str
    args: dict[str, Any] = field(default_factory=dict)
    parameters_frozen: dict[str, Any] = field(default_factory=dict)
    model_calls: int = 0
    removable: bool = False  # unnecessary model decision removable on promote
    genuinely_semantic: bool = False  # must remain AI or human
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TaskTrace:
    """Accepted task trace — evidence of one successful run, not generality."""

    trace_id: str
    source: str
    accepted: bool
    version: str
    steps: list[TraceStep]
    permissions: list[str]
    example_input: dict[str, Any]
    example_output: dict[str, Any]
    supported_conditions_hint: dict[str, Any] = field(default_factory=dict)
    model_calls_total: int = 0
    note: str = "One accepted run is insufficient evidence of generality."

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "source": self.source,
            "accepted": self.accepted,
            "version": self.version,
            "steps": [s.to_dict() for s in self.steps],
            "permissions": list(self.permissions),
            "example_input": self.example_input,
            "example_output": self.example_output,
            "supported_conditions_hint": self.supported_conditions_hint,
            "model_calls_total": self.model_calls_total,
            "note": self.note,
        }


@dataclass
class PromotedProgram:
    """Generated deterministic program — untrusted until reviewed and tested."""

    program_id: str
    version: str
    trust: TrustState
    source_trace_id: str
    source: str
    permissions: list[str]
    supported_conditions: dict[str, Any]
    steps: list[dict[str, Any]]  # deterministic (+ explicit ai/human semantic)
    frozen_parameters: dict[str, Any]
    model_calls_in_source: int
    model_calls_in_program: int
    model_calls_avoided: int
    rollback_path: str | None
    previous_version: str | None
    program_path: str | None = None
    metadata_path: str | None = None
    review_notes: list[str] = field(default_factory=list)
    test_results: list[dict[str, Any]] = field(default_factory=list)
    generality_claim: bool = False  # always false; one example ≠ generality

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
