"""Clone pinned vscode + apply FreeForge overlay (local; hosted CI not required)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from mainframe.config import ROOT
from mainframe.workbench.status import CLONE_REL, OVERLAY_DIR, load_pin


def bootstrap_workbench(*, skip_clone: bool = False) -> dict[str, Any]:
    pin = load_pin()
    upstream = pin.get("upstream") or {}
    tag = upstream.get("tag")
    repo = upstream.get("repo")
    if not tag or not repo:
        return {"ok": False, "error": "pin_missing"}

    clone = ROOT / CLONE_REL
    clone.parent.mkdir(parents=True, exist_ok=True)
    cloned = False
    if not skip_clone:
        if not (clone / ".git").is_dir():
            proc = subprocess.run(
                ["git", "clone", "--depth", "1", "--branch", str(tag), str(repo), str(clone)],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                return {
                    "ok": False,
                    "error": "git_clone_failed",
                    "stderr": (proc.stderr or "")[-500:],
                    "hint": "Network required once to fetch vscode pin; or use --skip-clone after manual clone",
                }
            cloned = True
        else:
            subprocess.run(
                ["git", "fetch", "--depth", "1", "origin", f"tag", str(tag)],
                cwd=str(clone),
                capture_output=True,
                text=True,
                check=False,
            )
            subprocess.run(
                ["git", "checkout", str(tag)],
                cwd=str(clone),
                capture_output=True,
                text=True,
                check=False,
            )

    dest = clone / "src" / "vs" / "workbench" / "contrib" / "freeforge"
    if not OVERLAY_DIR.is_dir():
        return {"ok": False, "error": "overlay_missing"}

    # Always materialize overlay into expected contrib path (even without full clone)
    if not clone.exists() and skip_clone:
        dest = ROOT / ".workbench-build" / "overlay-staging" / "freeforge"
    dest.mkdir(parents=True, exist_ok=True)
    for src in OVERLAY_DIR.rglob("*"):
        if src.is_file():
            rel = src.relative_to(OVERLAY_DIR)
            out = dest / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, out)

    copied = [str(p.relative_to(dest)).replace("\\", "/") for p in dest.rglob("*") if p.is_file()]
    return {
        "ok": True,
        "tag": tag,
        "repo": repo,
        "cloned": cloned,
        "skip_clone": skip_clone,
        "overlay_dest": str(dest),
        "overlay_files_copied": copied,
        "full_electron_build": False,
        "note": (
            "Overlay applied. Full vscode Electron build is a separate local step "
            "(see workbench/README.md); not required for MAINFRAME CLI."
        ),
        "hosted_ci_required": False,
    }


def run_overlay_check() -> dict[str, Any]:
    check = OVERLAY_DIR / "check.mjs"
    if not check.is_file():
        return {"ok": False, "error": "check_mjs_missing"}
    node = shutil.which("node")
    if not node:
        return {"ok": False, "error": "node_not_on_path", "hint": "Optional for overlay unit check"}
    proc = subprocess.run(
        [node, str(check)],
        cwd=str(OVERLAY_DIR),
        capture_output=True,
        text=True,
        check=False,
    )
    payload: dict[str, Any] = {"ok": proc.returncode == 0, "exit_code": proc.returncode}
    try:
        payload["result"] = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        payload["stdout"] = (proc.stdout or "")[-400:]
        payload["stderr"] = (proc.stderr or "")[-400:]
    return payload
