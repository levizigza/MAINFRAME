"""Builtin tool implementations — narrow, local, structured."""

from __future__ import annotations

import hashlib
import subprocess
import time
from pathlib import Path
from typing import Any

from mainframe.cost_gate import scrub_env_for_child
from mainframe.inventory.tools import file_range as inv_file_range
from mainframe.retrieval.retrieve import retrieve


def tool_search(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    root = Path(ctx["root"])
    out = retrieve(
        root,
        issue_text=args["query"],
        goal=args.get("goal") or args["query"],
        use_fts5=False,
        top_k=int(args.get("top_k") or 5),
    )
    return {
        "hits": [
            {
                "path": h.get("path"),
                "start_line": h.get("start_line"),
                "end_line": h.get("end_line"),
                "score": h.get("score"),
            }
            for h in (out.get("results") or [])
        ],
        "no_relevant_evidence": out.get("no_relevant_evidence"),
    }


def tool_file_range(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    root = Path(ctx["root"])
    expect = args.get("content_sha256")
    path = root / args["path"]
    if expect:
        if not path.is_file():
            return {"_error_code": "stale_file", "error": "file missing"}
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expect:
            return {
                "_error_code": "stale_file",
                "error": "content hash mismatch",
                "expected": expect,
                "actual": actual,
            }
    return inv_file_range(root, args["path"], args.get("start", 1), args.get("end"))


def tool_symbols(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    from mainframe.codeintel.tools import lookup_symbol

    root = Path(ctx["root"])
    return lookup_symbol(root, args["name"], module=args.get("module"))


def tool_diagnostics(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    from mainframe.codeintel.tools import diagnostics, tool_status

    root = Path(ctx["root"])
    st = tool_status()
    if not (st.get("adapters") or {}).get("pyright") and args.get("require_pyright"):
        return {
            "_error_code": "capability_unavailable",
            "error": "pyright not available",
            "adapters": st.get("adapters"),
        }
    return diagnostics(root)


def tool_patch(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    """Apply a bounded single-file replacement (side-effecting)."""
    root = Path(ctx["root"])
    rel = args["path"]
    path = (root / rel).resolve()
    if not str(path).startswith(str(root.resolve())):
        return {"_error_code": "invalid_input", "error": "path_escape"}
    if not path.is_file():
        return {"_error_code": "stale_file", "error": "file missing"}
    expect = args.get("content_sha256")
    data = path.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if expect and actual != expect:
        return {
            "_error_code": "stale_file",
            "error": "refusing patch on stale file",
            "expected": expect,
            "actual": actual,
        }
    text = data.decode("utf-8", errors="replace")
    old, new = args["old"], args["new"]
    if old not in text:
        return {"_error_code": "invalid_input", "error": "old_text_not_found"}
    if text.count(old) != 1:
        return {"_error_code": "invalid_input", "error": "old_text_not_unique"}
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return {
        "patched": True,
        "path": rel.replace("\\", "/"),
        "new_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def tool_tests(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    root = Path(ctx["root"])
    target = args.get("target") or "-q"
    timeout = float(ctx.get("timeout_s") or 60)
    cmd = ["python", "-m", "pytest", target] if not target.startswith("-") else [
        "python",
        "-m",
        "pytest",
        target,
    ]
    if args.get("extra"):
        cmd.extend(args["extra"])
    try:
        p = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=scrub_env_for_child(),
        )
    except FileNotFoundError:
        return {"_error_code": "capability_unavailable", "error": "python/pytest missing"}
    except subprocess.TimeoutExpired:
        return {"_error_code": "timeout", "error": "test run timed out"}
    return {
        "exit_code": p.returncode,
        "passed": p.returncode == 0,
        "stdout_tail": (p.stdout or "")[-2000:],
        "stderr_tail": (p.stderr or "")[-1000:],
        "command": cmd,
    }


def tool_diff(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    root = Path(ctx["root"])
    rel = args["path"]
    path = root / rel
    if not path.is_file():
        return {"_error_code": "stale_file", "error": "file missing"}
    left = args.get("before")
    right = path.read_text(encoding="utf-8", errors="replace")
    if left is None:
        return {
            "path": rel,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size": len(right),
            "unified": None,
            "note": "no before text; returned fingerprint only",
        }
    import difflib

    ud = "".join(
        difflib.unified_diff(
            left.splitlines(keepends=True),
            right.splitlines(keepends=True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
        )
    )
    return {"path": rel, "unified": ud, "changed": bool(ud)}
