"""Repository-change triggers — path-filtered git/workspace observations."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any

from mainframe.cost_gate import scrub_env_for_child
from mainframe.triggers.events import normalize_event
from mainframe.triggers.file_watch import path_excluded


def git_changed_paths(root: Path) -> dict[str, Any]:
    """List changed paths via git (no network)."""
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain", "-uall"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=30,
            env=scrub_env_for_child(),
            shell=False,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "paths": []}
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or "")[:400], "paths": []}
    paths = []
    for line in (proc.stdout or "").splitlines():
        if len(line) < 4:
            continue
        # porcelain: XY PATH or XY ORIG -> PATH
        rest = line[3:].strip()
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1]
        paths.append(rest.replace("\\", "/"))
    return {"ok": True, "paths": paths}


def observe_repo_change(
    *,
    root: Path,
    binding_id: str,
    permission_scope: str,
    watched_prefixes: list[str],
    exclude_prefixes: list[str] | None = None,
) -> dict[str, Any]:
    """
    Emit an event only when a watched prefix changed.
    Unrelated repo churn (outside watched_prefixes) creates no event.
    """
    exclude = exclude_prefixes or [".mainframe/", ".git/"]
    st = git_changed_paths(root)
    if not st.get("ok"):
        return {"emitted": False, "reason": "git_unavailable", "detail": st}

    matched = []
    for p in st.get("paths") or []:
        if path_excluded(p, exclude):
            continue
        if any(p.startswith(pref) for pref in watched_prefixes):
            matched.append(p)

    if not matched:
        return {
            "emitted": False,
            "reason": "unrelated_change",
            "changed_n": len(st.get("paths") or []),
            "watched_prefixes": watched_prefixes,
        }

    fp = hashlib.sha256("|".join(sorted(matched)).encode()).hexdigest()[:24]
    event = normalize_event(
        source="repository_change",
        identity=",".join(sorted(matched)[:8]),
        permission_scope=permission_scope,
        content_fingerprint=fp,
        binding_id=binding_id,
        payload={"paths": matched, "watched_prefixes": watched_prefixes},
    )
    return {"emitted": True, "event": event, "matched": matched}
