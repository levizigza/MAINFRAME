"""Load workflow JSON documents from fixtures or paths."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from mainframe.config import ROOT

FIXTURES = ROOT / "docs" / "eval" / "workflows" / "fixtures"


def load_workflow(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


def load_fixture(name: str) -> dict[str, Any]:
    return load_workflow(FIXTURES / name / "workflow.json")


def materialize_fixture(name: str, dest: Path) -> Path:
    src = FIXTURES / name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    return dest
