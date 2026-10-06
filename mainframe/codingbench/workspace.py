"""Materialize agent-editable workspace copies (fixtures only, no keys)."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

from mainframe.codingbench.catalog import FIXTURES_ROOT, KEYS_ROOT


def prepare_workspace(task: dict[str, Any], dest: Path) -> dict[str, Any]:
    fixture = task.get("fixture") or task["id"]
    src = FIXTURES_ROOT / fixture
    if not src.is_dir():
        return {"ok": False, "error": "missing_fixture", "fixture": fixture}
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    # Ensure keys never enter workspace
    keys_marker = dest / ".keys_forbidden"
    keys_marker.write_text(f"Expectations live under {KEYS_ROOT.as_posix()}\n", encoding="utf-8")
    digest = _tree_digest(dest)
    prompt_path = dest / (task.get("prompt_file") or "TASK.md")
    prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.is_file() else ""
    return {
        "ok": True,
        "workspace": str(dest),
        "fixture": fixture,
        "workspace_digest": digest,
        "prompt": prompt,
    }


def _tree_digest(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.name != ".keys_forbidden":
            rel = p.relative_to(root).as_posix().encode()
            h.update(rel)
            h.update(p.read_bytes())
    return h.hexdigest()[:16]
