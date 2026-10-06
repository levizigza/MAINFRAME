"""Inspect repo instructions and code without modifying user work."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from mainframe.config import ROOT

SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    ".mainframe",
}


@dataclass
class InspectReport:
    root: str
    rules: list[str]
    docs: list[str]
    python_modules: list[str]
    user_state_present: bool
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _list_rel(base: Path, pattern: str) -> list[str]:
    if not base.exists():
        return []
    out: list[str] = []
    for path in sorted(base.glob(pattern)):
        if path.is_file():
            out.append(str(path.relative_to(ROOT)).replace("\\", "/"))
    return out


def inspect_workspace() -> InspectReport:
    rules = _list_rel(ROOT / ".cursor" / "rules", "*.mdc")
    docs = _list_rel(ROOT / "docs", "**/*")
    modules: list[str] = []
    pkg = ROOT / "mainframe"
    if pkg.is_dir():
        for path in sorted(pkg.rglob("*.py")):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            modules.append(str(path.relative_to(ROOT)).replace("\\", "/"))

    user_state = (ROOT / ".mainframe").is_dir()
    notes: list[str] = []
    if not rules:
        notes.append("No Cursor rules found yet.")
    if not modules:
        notes.append("No mainframe package modules found.")
    notes.append("Inspection is read-only; user notes under .mainframe/ are preserved.")

    return InspectReport(
        root=str(ROOT),
        rules=rules,
        docs=docs,
        python_modules=modules,
        user_state_present=user_state,
        notes=notes,
    )
