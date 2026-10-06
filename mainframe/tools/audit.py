"""Auditable tool-call log — preserves call IDs; detects duplicates."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.config import STATE_DIR, ensure_state


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class CallAudit:
    """In-process + optional append-only audit for a session/project."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root
        self._seen_ids: set[str] = set()
        self.entries: list[dict[str, Any]] = []
        ensure_state()
        self._path = STATE_DIR / "runs" / "tool_audit.jsonl"

    def check_duplicate(self, call_id: str) -> bool:
        """Return True if call_id already used (duplicate)."""
        if not call_id:
            return False
        if call_id in self._seen_ids:
            return True
        return False

    def remember_id(self, call_id: str) -> None:
        if call_id:
            self._seen_ids.add(call_id)

    def record(self, entry: dict[str, Any]) -> None:
        entry = {**entry, "recorded_at": _utc()}
        self.entries.append(entry)
        try:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        except OSError:
            pass
