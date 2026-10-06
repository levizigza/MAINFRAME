"""Verify task outcomes using keys outside the workspace."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from mainframe.codingbench.keys import expectation_for
from mainframe.cost_gate import scrub_env_for_child


def verify_ui_page(workspace: Path) -> dict[str, Any]:
    from mainframe.browser.probe import playwright_available
    from mainframe.browser.session import ephemeral_session
    from mainframe.browser.waits import wait_for_load

    index = workspace / "index.html"
    if not index.is_file():
        return {"ok": False, "error": "missing_index"}
    if not playwright_available():
        return {"ok": False, "paused": True, "error": "playwright_unavailable"}
    url = index.resolve().as_uri()
    with ephemeral_session(project_id="codingbench_ui") as page:
        page.goto(url, wait_until="domcontentloaded")
        wait_for_load(page)
        page.get_by_role("button", name="Prepare").click()
        page.locator("#status").wait_for(state="visible")
        text = page.locator("#status").inner_text()
    return {"ok": text == "ready", "status_text": text}


def verify_task(task_id: str, workspace: Path, *, agent_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    agent_meta = agent_meta or {}
    spec = expectation_for(task_id)
    protected = list(spec.get("protected_paths_unchanged") or [])
    for rel in protected:
        p = workspace / rel
        if p.is_file():
            before = agent_meta.get("protected_snapshots", {}).get(rel)
            if before is not None and p.read_text(encoding="utf-8") != before:
                return {"ok": False, "reason": "protected_path_modified", "path": rel}

    verify = spec.get("verify") or []
    if verify == ["decline"]:
        return {
            "ok": bool(agent_meta.get("declined")),
            "mode": "decline",
            "declined": agent_meta.get("declined"),
        }
    if verify == ["clarify"]:
        return {
            "ok": bool(agent_meta.get("clarified")),
            "mode": "clarify",
            "clarified": agent_meta.get("clarified"),
        }
    if verify == ["ui"]:
        ui = verify_ui_page(workspace)
        return {"ok": ui.get("ok"), "mode": "ui", "detail": ui}

    cmd = list(verify)
    if not cmd:
        return {"ok": False, "error": "empty_verify"}
    env = scrub_env_for_child()
    proc = subprocess.run(
        cmd,
        cwd=str(workspace),
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    return {
        "ok": proc.returncode == 0,
        "mode": "pytest",
        "exit_code": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-500:],
        "stderr_tail": (proc.stderr or "")[-500:],
    }


def snapshot_protected(workspace: Path, task_id: str) -> dict[str, str]:
    spec = expectation_for(task_id)
    out: dict[str, str] = {}
    for rel in spec.get("protected_paths_unchanged") or []:
        p = workspace / rel
        if p.is_file():
            out[rel] = p.read_text(encoding="utf-8")
    return out
