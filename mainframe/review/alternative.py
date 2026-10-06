"""Bounded alternative candidate in an isolated worktree — not a swarm."""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from mainframe.config import STATE_DIR, ensure_state

ALT_ROOT = STATE_DIR / "review_worktrees"


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def create_isolated_worktree(
    source: Path,
    *,
    label: str = "alt",
) -> dict[str, Any]:
    """
    Isolate an alternative candidate.

    Prefer ``git worktree`` when ``source`` is inside a git repo; otherwise
    copytree into ``.mainframe/review_worktrees/`` (still isolated from the
    primary workspace).
    """
    ensure_state()
    ALT_ROOT.mkdir(parents=True, exist_ok=True)
    source = source.resolve()
    dest = ALT_ROOT / f"{label}-{_utc_stamp()}"
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)

    git_dir = _find_git_root(source)
    if git_dir is not None:
        # Detached worktree of current HEAD — bounded, one candidate
        branch = f"mainframe-review-alt-{_utc_stamp()}"
        proc = subprocess.run(
            ["git", "worktree", "add", "-b", branch, str(dest), "HEAD"],
            cwd=str(git_dir),
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0:
            return {
                "ok": True,
                "method": "git_worktree",
                "path": str(dest),
                "branch": branch,
                "source": str(source),
                "isolated": True,
            }
        # Fall through to copytree if worktree fails (e.g. dirty / OneDrive)

    shutil.copytree(
        source,
        dest,
        ignore=shutil.ignore_patterns(".git", ".mainframe", "__pycache__", ".pytest_cache"),
    )
    return {
        "ok": True,
        "method": "copytree_isolated",
        "path": str(dest),
        "branch": None,
        "source": str(source),
        "isolated": True,
        "git_worktree_fallback": git_dir is not None,
    }


def cleanup_worktree(info: dict[str, Any]) -> None:
    path = Path(info.get("path") or "")
    if info.get("method") == "git_worktree" and path.exists():
        git_root = _find_git_root(Path(info.get("source") or path))
        if git_root:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(path)],
                cwd=str(git_root),
                capture_output=True,
                text=True,
            )
            branch = info.get("branch")
            if branch:
                subprocess.run(
                    ["git", "branch", "-D", branch],
                    cwd=str(git_root),
                    capture_output=True,
                    text=True,
                )
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def run_bounded_alternative(
    workspace: Path,
    *,
    apply_candidate: Callable[[Path], dict[str, Any]],
    max_alternatives: int = 1,
    reason: str = "unresolved_high_value_failure",
) -> dict[str, Any]:
    """
    Allow at most ``max_alternatives`` (default 1) isolated candidate(s).
    Does not spawn a swarm.
    """
    if max_alternatives < 1:
        return {
            "ok": False,
            "skipped": True,
            "reason": "max_alternatives_zero",
            "swarm": False,
        }
    # Bound hard — never open more than 1 unless explicitly raised, still capped
    n = min(int(max_alternatives), 1)
    created = create_isolated_worktree(workspace, label="alt")
    if not created.get("ok"):
        return {"ok": False, "error": "worktree_create_failed", "detail": created, "swarm": False}

    alt_path = Path(created["path"])
    try:
        result = apply_candidate(alt_path)
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "error": str(exc)}

    return {
        "ok": bool(result.get("ok")),
        "reason": reason,
        "swarm": False,
        "alternatives_n": n,
        "max_alternatives": max_alternatives,
        "worktree": created,
        "candidate_result": result,
        "cleanup": str(alt_path),
    }


def _find_git_root(path: Path) -> Path | None:
    cur = path if path.is_dir() else path.parent
    for p in [cur, *cur.parents]:
        if (p / ".git").exists():
            return p
    return None
