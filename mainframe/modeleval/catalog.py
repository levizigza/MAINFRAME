"""Task catalog loader — tune vs holdout splits."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mainframe.config import ROOT

CATALOG_PATH = ROOT / "docs" / "eval" / "model_tasks" / "catalog.json"


def load_catalog(path: Path | None = None) -> dict[str, Any]:
    p = path or CATALOG_PATH
    data = json.loads(p.read_text(encoding="utf-8"))
    return data


def tasks(
    *,
    split: str | None = None,
    task_class: str | None = None,
    include_optional_vision: bool = True,
) -> list[dict[str, Any]]:
    cat = load_catalog()
    out = []
    for t in cat.get("tasks") or []:
        if split and t.get("split") != split:
            continue
        if task_class and t.get("class") != task_class:
            continue
        if not include_optional_vision and t.get("vision"):
            continue
        out.append(dict(t))
    return out


def holdout_ids() -> set[str]:
    return {t["id"] for t in tasks(split="holdout")}


def tune_ids() -> set[str]:
    return {t["id"] for t in tasks(split="tune")}
