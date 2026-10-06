"""File-change triggers — debounce storms, partial writes, avoid self-retrigger."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

from mainframe.triggers.events import normalize_event
from mainframe.triggers.store import TriggerStore

PARTIAL_SUFFIXES = (".tmp", ".temp", ".part", ".swp", ".crdownload", "~")


def looks_partial(path: Path) -> bool:
    name = path.name
    return name.endswith(PARTIAL_SUFFIXES) or name.startswith(".") and name.endswith(".swx")


def wait_stable(path: Path, *, settle_ms: int = 50, checks: int = 2) -> dict[str, Any]:
    """Handle partial writes — require size/mtime stability across checks."""
    if not path.is_file():
        return {"stable": False, "reason": "missing"}
    if looks_partial(path):
        return {"stable": False, "reason": "partial_suffix"}
    prev: tuple[int, float] | None = None
    for _ in range(checks):
        st = path.stat()
        cur = (st.st_size, st.st_mtime)
        if prev is not None and cur != prev:
            return {"stable": False, "reason": "size_or_mtime_changed", "size": cur[0]}
        prev = cur
        time.sleep(settle_ms / 1000.0)
    assert prev is not None
    return {"stable": True, "size": prev[0], "mtime": prev[1]}


def path_excluded(rel: str, exclude_prefixes: list[str]) -> bool:
    rel_n = rel.replace("\\", "/")
    return any(rel_n.startswith(p) or f"/{p}" in f"/{rel_n}" for p in exclude_prefixes)


def file_fingerprint(path: Path) -> str:
    if not path.is_file():
        return "missing"
    h = hashlib.sha256()
    h.update(str(path).encode())
    st = path.stat()
    h.update(f"{st.st_size}:{st.st_mtime_ns}".encode())
    # Sample head for content without reading huge files fully
    with path.open("rb") as f:
        h.update(f.read(4096))
    return h.hexdigest()[:24]


def observe_file_change(
    store: TriggerStore,
    *,
    path: Path,
    root: Path,
    binding_id: str,
    permission_scope: str,
    exclude_prefixes: list[str] | None = None,
    debounce_ms: int = 500,
) -> dict[str, Any]:
    """
    Observe a file change for a binding. Unrelated / excluded / unstable → no event.
    Self-retrigger avoidance: outputs under .mainframe/ and binding exclude list.
    """
    exclude = exclude_prefixes or [".mainframe/", ".git/", "__pycache__/"]
    try:
        rel = str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except ValueError:
        return {"emitted": False, "reason": "outside_root"}

    if path_excluded(rel, exclude):
        return {"emitted": False, "reason": "excluded_self_or_unrelated", "path": rel}

    stable = wait_stable(path)
    if not stable.get("stable"):
        return {"emitted": False, "reason": f"partial_or_unstable:{stable.get('reason')}", "path": rel}

    fp = file_fingerprint(path)
    deb = store.debounce_allow(f"file:{rel}", fp, window_ms=debounce_ms)
    if not deb.get("allow"):
        return {"emitted": False, "reason": "debounced", "path": rel, "debounce": deb}

    event = normalize_event(
        source="file_change",
        identity=rel,
        permission_scope=permission_scope,
        content_fingerprint=fp,
        binding_id=binding_id,
        payload={"path": rel, "size": stable.get("size")},
    )
    return {"emitted": True, "event": event, "path": rel}
