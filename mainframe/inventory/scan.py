"""Repository inventory scan using Git, ripgrep, and filesystem metadata."""

from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mainframe.cost_gate import authorize, scrub_env_for_child
from mainframe.inventory.detect import classify_kind, language_for, summarize_inventory
from mainframe.inventory.ignore import (
    is_privacy_excluded,
    load_gitignore_patterns,
    path_matches_gitignore,
    should_skip_dir,
)
from mainframe.inventory.store import (
    connect,
    get_entry,
    root_key,
    save_summary,
    upsert_file,
)


@dataclass
class ScanStats:
    listed: int = 0
    hashed: int = 0
    reused: int = 0
    skipped_ignored: int = 0
    skipped_privacy: int = 0
    changed_during_scan: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "listed": self.listed,
            "hashed": self.hashed,
            "reused": self.reused,
            "skipped_ignored": self.skipped_ignored,
            "skipped_privacy": self.skipped_privacy,
            "changed_during_scan": self.changed_during_scan,
            "errors": self.errors,
        }


def _run(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
    try:
        p = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            env=scrub_env_for_child(),
            timeout=120,
        )
        return p.returncode, p.stdout or "", p.stderr or ""
    except Exception as exc:  # noqa: BLE001
        return 1, "", f"{type(exc).__name__}: {exc}"


def git_status_map(root: Path) -> dict[str, str]:
    """path -> tracked|untracked|modified|other"""
    code, out, err = _run(["git", "status", "--porcelain", "-uall"], root)
    mapping: dict[str, str] = {}
    if code != 0:
        return mapping
    for line in out.splitlines():
        if len(line) < 4:
            continue
        status = line[:2]
        path = line[3:].strip().replace("\\", "/")
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if status == "??":
            mapping[path] = "untracked"
        elif "M" in status or "A" in status or "D" in status:
            mapping[path] = "modified"
        else:
            mapping[path] = "tracked"
    # Mark other git files as tracked via ls-files
    code2, out2, _ = _run(["git", "ls-files"], root)
    if code2 == 0:
        for line in out2.splitlines():
            p = line.strip().replace("\\", "/")
            mapping.setdefault(p, "tracked")
    return mapping


def rg_file_list(root: Path) -> list[str] | None:
    """Use ripgrep --files respecting gitignore when available."""
    code, out, err = _run(["rg", "--files", "--hidden", "--glob", "!.git"], root)
    if code != 0:
        return None
    return [ln.strip().replace("\\", "/") for ln in out.splitlines() if ln.strip()]


def walk_fallback(root: Path, gitignore: list[str]) -> list[tuple[str, Path]]:
    found: list[tuple[str, Path]] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
        base = Path(dirpath)
        for name in filenames:
            full = base / name
            try:
                rel = full.relative_to(root).as_posix()
            except ValueError:
                continue
            if path_matches_gitignore(rel, gitignore) or should_skip_dir(name):
                continue
            found.append((rel, full))
    return found


def normalize_path_key(rel_posix: str) -> str:
    return rel_posix.replace("\\", "/").casefold()


def hash_file(path: Path) -> tuple[str | None, int | None, int | None, str | None]:
    """Return sha256, size, mtime_ns, error."""
    try:
        st = path.lstat()
        if path.is_symlink():
            return None, st.st_size, getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)), None
        h = hashlib.sha256()
        size = 0
        with path.open("rb") as f:
            while True:
                chunk = f.read(1024 * 256)
                if not chunk:
                    break
                size += len(chunk)
                h.update(chunk)
        # Re-stat to detect change during read
        st2 = path.lstat()
        m1 = getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))
        m2 = getattr(st2, "st_mtime_ns", int(st2.st_mtime * 1e9))
        if st.st_size != st2.st_size or m1 != m2:
            return h.hexdigest(), size, m2, "changed_during_scan"
        return h.hexdigest(), size, m2, None
    except OSError as exc:
        return None, None, None, str(exc)


def scan_repository(root: Path, *, incremental: bool = True) -> dict[str, Any]:
    gate = authorize("tool", "local.inventory_scan", local=True)
    if not gate.allowed:
        return {"ok": False, "cost_gate": gate.to_dict()}

    root = root.resolve()
    stats = ScanStats()
    gitignore = load_gitignore_patterns(root)
    git_map = git_status_map(root)

    rg_list = rg_file_list(root)
    paths: list[tuple[str, Path]] = []
    if rg_list is not None:
        for rel in rg_list:
            if should_skip_dir(rel.split("/")[0]):
                stats.skipped_ignored += 1
                continue
            if path_matches_gitignore(rel, gitignore):
                stats.skipped_ignored += 1
                continue
            paths.append((rel, root / rel))
    else:
        paths = walk_fallback(root, gitignore)

    stats.listed = len(paths)
    rk = root_key(root)
    conn = connect(root)
    entries: list[dict[str, Any]] = []

    for rel, full in paths:
        path_key = normalize_path_key(rel)
        privacy = is_privacy_excluded(rel)
        ignored = path_matches_gitignore(rel, gitignore)

        if privacy:
            stats.skipped_privacy += 1
            entry = {
                "path_key": path_key,
                "display_path": rel,
                "content_sha256": None,
                "size_bytes": None,
                "mtime_ns": None,
                "is_symlink": 0,
                "symlink_target": None,
                "language": None,
                "kind": "privacy_excluded",
                "git_status": git_map.get(rel, "unknown"),
                "privacy_excluded": 1,
                "ignored": int(ignored),
                "provenance": {"source": "privacy_exclusion", "tools": ["policy"]},
            }
            upsert_file(conn, rk, entry)
            entries.append(entry)
            continue

        if ignored:
            stats.skipped_ignored += 1
            continue

        is_link = full.is_symlink()
        link_target = None
        if is_link:
            try:
                link_target = os.readlink(full)
            except OSError:
                link_target = None

        st_mtime = None
        st_size = None
        try:
            st = full.lstat()
            st_mtime = getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))
            st_size = st.st_size
        except OSError as exc:
            stats.errors.append(f"{rel}: {exc}")
            continue

        prev = get_entry(conn, rk, path_key) if incremental else None
        reuse = (
            incremental
            and prev
            and prev.get("mtime_ns") == st_mtime
            and prev.get("size_bytes") == st_size
            and prev.get("content_sha256")
            and not is_link
        )

        if reuse:
            stats.reused += 1
            sha = prev["content_sha256"]
            err = None
            size = prev["size_bytes"]
            mtime = prev["mtime_ns"]
        else:
            sha, size, mtime, err = hash_file(full)
            stats.hashed += 1
            if err == "changed_during_scan":
                stats.changed_during_scan += 1

        kind = classify_kind(rel, is_symlink=is_link)
        entry = {
            "path_key": path_key,
            "display_path": rel,
            "content_sha256": sha,
            "size_bytes": size if size is not None else st_size,
            "mtime_ns": mtime if mtime is not None else st_mtime,
            "is_symlink": int(is_link),
            "symlink_target": link_target,
            "language": language_for(rel),
            "kind": kind,
            "git_status": git_map.get(rel, "untracked" if not git_map else git_map.get(rel, "unknown")),
            "privacy_excluded": 0,
            "ignored": 0,
            "provenance": {
                "source": "inventory_scan",
                "tools": ["git", "rg" if rg_list is not None else "os.walk", "sha256"],
                "incremental_reuse": bool(reuse),
                "scan_note": err,
            },
        }
        # Fix git_status default
        if rel not in git_map:
            entry["git_status"] = "untracked" if (root / ".git").exists() else "no_git"
        else:
            entry["git_status"] = git_map[rel]

        upsert_file(conn, rk, entry)
        entries.append(entry)

    summary = summarize_inventory(entries)
    summary["work"] = stats.to_dict()
    summary["root"] = str(root)
    summary["embedding_service_used"] = False
    summary["model_request_used"] = False
    summary["rg_used"] = rg_list is not None
    summary["git_used"] = bool(git_map) or (root / ".git").exists()
    save_summary(conn, rk, str(root), summary)
    conn.close()
    return {"ok": True, "summary": summary, "entry_count": len(entries)}
