"""Token budget: reserve room for output, reasoning, and tool-protocol overhead."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class TokenBudget:
    """Total context window budget with reserved non-evidence slices."""

    total: int = 8000
    reserve_output: int = 1500
    reserve_reasoning: int = 800
    reserve_tool_protocol: int = 400

    @property
    def evidence_capacity(self) -> int:
        used = self.reserve_output + self.reserve_reasoning + self.reserve_tool_protocol
        return max(256, self.total - used)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["evidence_capacity"] = self.evidence_capacity
        return d


def default_budget(*, total: int | None = None, constrained: bool = False) -> TokenBudget:
    if constrained:
        # Tight fixture budget — still reserves output/reasoning/tools
        return TokenBudget(
            total=total or 1200,
            reserve_output=300,
            reserve_reasoning=150,
            reserve_tool_protocol=100,
        )
    return TokenBudget(total=total or 8000)
