"""Adaptive controller types — modes, budgets, evidence (no hidden CoT)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Mode = Literal["deterministic_tools", "direct_model", "plan_review"]
StopReason = Literal[
    "accepted",
    "budget_turns",
    "budget_tokens",
    "budget_tools",
    "budget_elapsed",
    "no_progress",
    "unavailable_information",
    "unavailable_capacity",
    "cancelled",
]


@dataclass
class Budgets:
    max_turns: int = 8
    max_tokens: int = 4000
    max_tool_calls: int = 12
    max_elapsed_ms: int = 30_000

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceItem:
    kind: str  # verification_failure | unresolved_dependency | conflicting_requirement | invalid_action | observation | accept_pass
    detail: str
    turn: int
    observable: bool = True  # never a model confidence score alone

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Journal:
    """Concise hypotheses, decisions, evidence — not a CoT transcript."""

    hypotheses: list[str] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[EvidenceItem] = field(default_factory=list)

    def add_hypothesis(self, text: str) -> None:
        h = text.strip()
        if h and h not in self.hypotheses:
            self.hypotheses.append(h)
            # Keep concise
            self.hypotheses = self.hypotheses[-8:]

    def decide(self, decision: str, reason: str, mode: Mode) -> None:
        self.decisions.append({"decision": decision, "reason": reason, "mode": mode})
        self.decisions = self.decisions[-16:]

    def note(self, item: EvidenceItem) -> None:
        self.evidence.append(item)
        self.evidence = self.evidence[-32:]

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypotheses": list(self.hypotheses),
            "decisions": list(self.decisions),
            "evidence": [e.to_dict() for e in self.evidence],
            "chain_of_thought_required": False,
        }


@dataclass
class ControllerResult:
    ok: bool
    mode_final: Mode
    stop_reason: StopReason
    turns_used: int
    tokens_used: int
    tool_calls_used: int
    elapsed_ms: int
    ceremony: list[str]  # which agent steps ran
    journal: dict[str, Any]
    checkpoint: dict[str, Any] | None
    output: dict[str, Any]
    budgets: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
