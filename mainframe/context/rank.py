"""Evidence items with criticality, relevance, and novelty ranking."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

CriticalKind = Literal[
    "contract",
    "signature",
    "invariant",
    "source_pointer",
    "diagnostic",
    "normal",
]


@dataclass
class EvidenceItem:
    id: str
    kind: str  # contract|overview|symbol|range|diagnostic|docs|log
    critical: CriticalKind
    path: str | None
    start_line: int | None
    end_line: int | None
    signature: str | None
    content: str
    pointers: list[str] = field(default_factory=list)
    relevance: float = 0.0
    novelty: float = 1.0
    tokens_est: int = 0
    trust: str = "local"  # local|installed_types|untrusted_fetched
    attribution: str | None = None

    def score(self) -> float:
        # Critical items sort first regardless of soft score
        crit_boost = {
            "contract": 1000,
            "signature": 900,
            "invariant": 850,
            "source_pointer": 800,
            "diagnostic": 750,
            "normal": 0,
        }[self.critical]
        return crit_boost + self.relevance * 10 + self.novelty * 5

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["score"] = self.score()
        return d


def content_fingerprint(text: str) -> str:
    import hashlib

    # Normalize repeated log noise
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # Collapse consecutive duplicates
    collapsed: list[str] = []
    for ln in lines:
        if collapsed and collapsed[-1] == ln:
            continue
        collapsed.append(ln)
    blob = "\n".join(collapsed[:50])
    return hashlib.sha256(blob.encode("utf-8", errors="replace")).hexdigest()[:16]


def apply_novelty(items: list[EvidenceItem]) -> list[EvidenceItem]:
    seen: dict[str, int] = {}
    for it in items:
        fp = content_fingerprint(it.content)
        count = seen.get(fp, 0)
        seen[fp] = count + 1
        if count == 0:
            it.novelty = 1.0
        else:
            # Repeated logs / duplicate ranges → low novelty
            it.novelty = max(0.05, 1.0 / (count + 1))
            if it.kind == "log":
                it.novelty = min(it.novelty, 0.1)
    return items


def rank_items(items: list[EvidenceItem]) -> list[EvidenceItem]:
    apply_novelty(items)
    return sorted(items, key=lambda x: (-x.score(), x.id))
