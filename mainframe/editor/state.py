"""Shared editor↔CLI task state — one source of truth under .mainframe/editor_tasks/."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.config import STATE_DIR, ensure_state

TASK_DIR_NAME = "editor_tasks"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def tasks_root(root: Path | None = None) -> Path:
    ensure_state()
    base = root or (STATE_DIR / TASK_DIR_NAME)
    base.mkdir(parents=True, exist_ok=True)
    return base


class EditorTaskStore:
    """JSON task documents shared by the VS Code extension and CLI."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = tasks_root(root)

    def _path(self, task_id: str) -> Path:
        return self.root / f"{task_id}.json"

    def create(
        self,
        *,
        chat: str,
        workspace: str,
        source: str = "editor",
    ) -> dict[str, Any]:
        task_id = f"edt_{uuid.uuid4().hex[:12]}"
        task = {
            "task_id": task_id,
            "format_version": "1.0",
            "source": source,
            "workspace": str(Path(workspace).resolve()),
            "chat": chat,
            "state": "open",
            "created_at": _utc(),
            "updated_at": _utc(),
            "context": {"selection": None, "diagnostics": [], "buffers": {}},
            "proposal": None,
            "apply": None,
            "operation_ids": {},
            "cancelled": False,
            "completion": {"enabled": False, "reason": "not_requested"},
            "shared_with_cli": True,
            "note": "Editor and CLI share this task document; do not duplicate apply.",
        }
        self.save(task)
        return task

    def save(self, task: dict[str, Any]) -> Path:
        task["updated_at"] = _utc()
        path = self._path(task["task_id"])
        path.write_text(json.dumps(task, indent=2) + "\n", encoding="utf-8")
        return path

    def load(self, task_id: str) -> dict[str, Any] | None:
        path = self._path(task_id)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list_tasks(self) -> list[dict[str, Any]]:
        out = []
        for p in sorted(self.root.glob("edt_*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            out.append(
                {
                    "task_id": data.get("task_id"),
                    "state": data.get("state"),
                    "workspace": data.get("workspace"),
                    "cancelled": data.get("cancelled"),
                }
            )
        return out


def content_fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def operation_id_for_patch(task_id: str, patch_fingerprint: str) -> str:
    raw = f"{task_id}|{patch_fingerprint}"
    return "op_ed_" + hashlib.sha256(raw.encode()).hexdigest()[:16]
