"""Explainable ranking, range expansion, deduplication."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Hit:
    path: str
    start_line: int
    end_line: int
    score: float = 0.0
    signals: list[dict[str, Any]] = field(default_factory=list)
    snippet: str = ""
    lines: list[str] = field(default_factory=list)

    def key(self) -> tuple[str, int, int]:
        return (self.path.casefold(), self.start_line, self.end_line)


SIGNAL_WEIGHTS = {
    "exact_filename": 8.0,
    "stack_frame_path": 10.0,
    "stack_frame_line": 12.0,
    "exact_identifier": 7.0,
    "error_message": 9.0,
    "quoted_string": 6.0,
    "import_from_stack": 11.0,  # bug often outside stack — follow imports
    "lexical_overlap": 2.0,
    "follow_up_term": 5.0,
    "fts5_bm25": 3.0,  # supplemental only
}


def add_signal(hit: Hit, kind: str, detail: Any, *, weight: float | None = None) -> None:
    w = weight if weight is not None else SIGNAL_WEIGHTS.get(kind, 1.0)
    hit.signals.append({"kind": kind, "weight": w, "detail": detail})
    hit.score += w


def merge_overlapping(hits: list[Hit], *, gap: int = 4) -> list[Hit]:
    """Deduplicate / merge overlapping or adjacent ranges in the same file."""
    by_path: dict[str, list[Hit]] = {}
    for h in hits:
        by_path.setdefault(h.path.replace("\\", "/"), []).append(h)

    merged: list[Hit] = []
    for path, group in by_path.items():
        group.sort(key=lambda x: (x.start_line, x.end_line))
        cur: Hit | None = None
        for h in group:
            if cur is None:
                cur = Hit(
                    path=path,
                    start_line=h.start_line,
                    end_line=h.end_line,
                    score=h.score,
                    signals=list(h.signals),
                    snippet=h.snippet,
                    lines=list(h.lines),
                )
                continue
            if h.start_line <= cur.end_line + gap:
                cur.end_line = max(cur.end_line, h.end_line)
                cur.score = max(cur.score, h.score) + 0.5 * min(h.score, cur.score)
                # Dedup signals by kind+detail string
                seen = {(s["kind"], str(s.get("detail"))) for s in cur.signals}
                for s in h.signals:
                    key = (s["kind"], str(s.get("detail")))
                    if key not in seen:
                        cur.signals.append(s)
                        seen.add(key)
                if len(h.snippet) > len(cur.snippet):
                    cur.snippet = h.snippet
            else:
                merged.append(cur)
                cur = Hit(
                    path=path,
                    start_line=h.start_line,
                    end_line=h.end_line,
                    score=h.score,
                    signals=list(h.signals),
                    snippet=h.snippet,
                    lines=list(h.lines),
                )
        if cur is not None:
            merged.append(cur)
    merged.sort(key=lambda h: (-h.score, h.path, h.start_line))
    return merged


def expand_range(
    total_lines: int,
    center_start: int,
    center_end: int,
    *,
    pad: int = 8,
    max_span: int = 40,
) -> tuple[int, int]:
    start = max(1, center_start - pad)
    end = min(total_lines, center_end + pad)
    if end - start + 1 > max_span:
        mid = (center_start + center_end) // 2
        start = max(1, mid - max_span // 2)
        end = min(total_lines, start + max_span - 1)
    return start, end


def context_char_count(hits: list[Hit]) -> int:
    return sum(len(h.snippet) + sum(len(ln) + 1 for ln in h.lines) for h in hits)
