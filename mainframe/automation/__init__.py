"""Deterministic automation — works with AI paused."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Callable

from mainframe.config import ROOT, RUNS_DIR, ensure_state
from mainframe.workspace import SKIP_DIRS

TaskFn = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class RunResult:
    task: str
    ok: bool
    started_at: str
    finished_at: str
    duration_ms: int
    output: dict[str, Any]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def task_echo(params: dict[str, Any]) -> dict[str, Any]:
    message = str(params.get("message", "MAINFRAME ready"))
    return {"message": message}


def task_list_tree(params: dict[str, Any]) -> dict[str, Any]:
    max_files = int(params.get("max_files", 200))
    files: list[str] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        files.append(str(path.relative_to(ROOT)).replace("\\", "/"))
        if len(files) >= max_files:
            break
    return {"count": len(files), "files": files}


def task_workspace_checksum(params: dict[str, Any]) -> dict[str, Any]:
    """Stable SHA-256 over relative path + file bytes for tracked source/docs."""
    include_globs = params.get(
        "include",
        ["mainframe/**/*.py", "docs/**/*", ".cursor/rules/**/*", "README.md", "LICENSE"],
    )
    h = hashlib.sha256()
    included: list[str] = []
    for pattern in include_globs:
        for path in sorted(ROOT.glob(pattern)):
            if not path.is_file():
                continue
            rel = str(path.relative_to(ROOT)).replace("\\", "/")
            data = path.read_bytes()
            h.update(rel.encode("utf-8"))
            h.update(b"\0")
            h.update(data)
            h.update(b"\0")
            included.append(rel)
    return {"sha256": h.hexdigest(), "file_count": len(included), "files": included}


def task_write_run_report(params: dict[str, Any]) -> dict[str, Any]:
    ensure_state()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = RUNS_DIR / f"report-{stamp}.json"
    payload = {
        "generated_at": _utc_now(),
        "note": params.get("note", "deterministic report"),
        "root": str(ROOT),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return {"report": str(path.relative_to(ROOT)).replace("\\", "/")}


REGISTRY: dict[str, TaskFn] = {
    "echo": task_echo,
    "list-tree": task_list_tree,
    "workspace-checksum": task_workspace_checksum,
    "write-run-report": task_write_run_report,
}


def list_tasks() -> list[str]:
    return sorted(REGISTRY.keys())


def run_task(name: str, params: dict[str, Any] | None = None) -> RunResult:
    ensure_state()
    params = params or {}
    started = time.perf_counter()
    started_at = _utc_now()
    if name not in REGISTRY:
        finished_at = _utc_now()
        return RunResult(
            task=name,
            ok=False,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=int((time.perf_counter() - started) * 1000),
            output={},
            error=f"Unknown task: {name}. Known: {', '.join(list_tasks())}",
        )
    try:
        output = REGISTRY[name](params)
        ok = True
        error = None
    except Exception as exc:  # noqa: BLE001 — surface to run log
        output = {}
        ok = False
        error = f"{type(exc).__name__}: {exc}"
    finished_at = _utc_now()
    result = RunResult(
        task=name,
        ok=ok,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=int((time.perf_counter() - started) * 1000),
        output=output,
        error=error,
    )
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in started_at)
    log_path = RUNS_DIR / f"run-{safe}.json"
    log_path.write_text(json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8")
    return result
