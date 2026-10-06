"""Coding benchmark catalog — holdout disjoint from tune."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mainframe.config import ROOT

CATALOG_PATH = ROOT / "docs" / "eval" / "coding_benchmark" / "catalog.json"
FIXTURES_ROOT = ROOT / "docs" / "eval" / "coding_benchmark" / "fixtures"
KEYS_ROOT = ROOT / "docs" / "eval" / "coding_benchmark" / "keys"


def load_catalog(path: Path | None = None) -> dict[str, Any]:
    p = path or CATALOG_PATH
    return json.loads(p.read_text(encoding="utf-8"))


def list_tasks(*, split: str | None = None) -> list[dict[str, Any]]:
    cat = load_catalog()
    out: list[dict[str, Any]] = []
    for t in cat.get("tasks") or []:
        if split and t.get("split") != split:
            continue
        out.append(dict(t))
    return out


def holdout_ids() -> set[str]:
    return {t["id"] for t in list_tasks(split="holdout")}


def tune_ids() -> set[str]:
    return {t["id"] for t in list_tasks(split="tune")}


def budget_defaults() -> dict[str, Any]:
    return dict(load_catalog().get("budget_defaults") or {})
