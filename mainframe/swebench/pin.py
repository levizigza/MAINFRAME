"""Pinned SWE-bench-style protocol metadata (no leaderboard numbers copied)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mainframe.config import ROOT

PIN_PATH = ROOT / "docs" / "eval" / "swe" / "PIN.json"
FIXTURES = ROOT / "docs" / "eval" / "swe" / "fixtures"


def load_pin() -> dict[str, Any]:
    if not PIN_PATH.is_file():
        return {}
    return json.loads(PIN_PATH.read_text(encoding="utf-8"))


def list_local_instances() -> list[dict[str, Any]]:
    pin = load_pin()
    return list(pin.get("local_instances") or [])
