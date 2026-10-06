"""Quota admission types."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Priority = Literal["interactive", "background"]
ReservationState = Literal["reserved", "reconciled", "released", "expired"]


@dataclass
class UsageEstimate:
    requests: int = 1
    tokens: int = 0
    context_tokens: int = 0
    # Overhead reserves (tool rounds / reasoning) — counted against token budget
    tool_overhead_tokens: int = 0
    reasoning_overhead_tokens: int = 0

    def total_tokens(self) -> int:
        return int(self.tokens) + int(self.context_tokens) + int(self.tool_overhead_tokens) + int(
            self.reasoning_overhead_tokens
        )

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "total_tokens": self.total_tokens()}


@dataclass
class ActualUsage:
    requests: int = 0
    tokens: int | None = None  # None = unknown
    context_tokens: int | None = None
    tool_overhead_tokens: int | None = None
    reasoning_overhead_tokens: int | None = None
    unknown: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AdmitDecision:
    allowed: bool
    reservation_id: str | None
    reason: str
    retry_after_s: float | None = None
    reset_unknown: bool = False
    priority: Priority = "interactive"
    ledger_snapshot: dict[str, Any] = field(default_factory=dict)
    denied_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
