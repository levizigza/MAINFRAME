"""Bind verification results to exact code hashes and environment fingerprint."""

from __future__ import annotations

import hashlib
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_paths(root: Path, rels: list[str]) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for rel in rels:
        p = root / rel.replace("\\", "/")
        try:
            out[rel.replace("\\", "/")] = hashlib.sha256(p.read_bytes()).hexdigest()
        except OSError:
            out[rel.replace("\\", "/")] = None
    return out


def environment_fingerprint() -> dict[str, Any]:
    return {
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "executable": sys.executable,
    }


def bind_result(
    *,
    root: Path,
    code_paths: list[str],
    phase: str,
    checks: list[dict[str, Any]],
    contract_id: str | None = None,
) -> dict[str, Any]:
    return {
        "bound_at": _utc(),
        "phase": phase,
        "root": str(root.resolve()),
        "code_hashes": hash_paths(root, code_paths),
        "environment": environment_fingerprint(),
        "contract_id": contract_id,
        "checks": checks,
        "binding_id": hashlib.sha256(
            (
                str(root)
                + phase
                + "".join(f"{k}{v}" for k, v in sorted(hash_paths(root, code_paths).items()))
                + sys.version
            ).encode()
        ).hexdigest()[:20],
    }


def binding_still_valid(root: Path, binding: dict[str, Any]) -> dict[str, Any]:
    """Invalidate prior verification when relevant code hashes drift."""
    expected = binding.get("code_hashes") or {}
    current = hash_paths(root, list(expected.keys()))
    drifted = {
        p: {"was": expected[p], "now": current.get(p)}
        for p in expected
        if expected[p] != current.get(p)
    }
    return {
        "valid": len(drifted) == 0,
        "binding_id": binding.get("binding_id"),
        "drifted": drifted,
        "stale": len(drifted) > 0,
    }
