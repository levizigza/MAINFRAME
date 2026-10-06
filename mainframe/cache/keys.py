"""Exact cache key material — content, environment, model, config, permissions."""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from pathlib import Path
from typing import Any


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def project_id(root: Path) -> str:
    """Isolate cache namespaces per project root."""
    return sha256_hex(str(root.resolve()).replace("\\", "/").casefold())[:24]


def environment_version() -> dict[str, Any]:
    return {
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
    }


def content_version(root: Path, paths: list[str] | None = None) -> dict[str, Any]:
    """
    Fingerprint relevant source content.

    If ``paths`` is None, fingerprint a bounded walk of text-ish files under root
    (excluding .mainframe / .git / caches).
    """
    root = root.resolve()
    skip_dirs = {
        ".git",
        ".mainframe",
        "__pycache__",
        ".venv",
        "venv",
        "node_modules",
        ".pytest_cache",
        "dist",
        "build",
    }
    files: list[str] = []
    digest = hashlib.sha256()
    if paths:
        rels = sorted(p.replace("\\", "/") for p in paths)
    else:
        rels = []
        for p in sorted(root.rglob("*")):
            if not p.is_file():
                continue
            try:
                rel = p.relative_to(root).as_posix()
            except ValueError:
                continue
            if any(part in skip_dirs for part in Path(rel).parts):
                continue
            if p.suffix.lower() not in {
                ".py",
                ".md",
                ".txt",
                ".json",
                ".toml",
                ".yml",
                ".yaml",
                ".ini",
                ".cfg",
            } and p.name not in {"LICENSE", "README"}:
                continue
            rels.append(rel)
    for rel in rels:
        path = root / rel
        digest.update(rel.encode())
        try:
            body = path.read_bytes()
            digest.update(body)
            files.append(f"{rel}:{sha256_hex(body)[:16]}")
        except OSError:
            digest.update(b"missing")
            files.append(f"{rel}:missing")
    return {
        "content_hash": digest.hexdigest(),
        "file_count": len(files),
        "files_sample": files[:40],
    }


def config_version(config: dict[str, Any] | None = None) -> str:
    from mainframe.config import load_config

    cfg = dict(config if config is not None else load_config())
    # Drop volatile fields that must not stabilize keys incorrectly
    for k in ("last_run", "session_id", "notes"):
        cfg.pop(k, None)
    return sha256_hex(_canon(cfg))[:32]


def permission_version(permissions: dict[str, Any] | None = None) -> str:
    """
    Version of authorization / capability posture for this process.

    Changing entitlements or denied routes must invalidate cached results that
    depended on prior authorization.
    """
    from mainframe.eligibility import DISABLED_PROVIDERS, ELIGIBLE_PROVIDERS

    material = {
        "permissions": permissions or {},
        "eligible_providers": sorted(ELIGIBLE_PROVIDERS.keys()),
        "disabled_providers": sorted(DISABLED_PROVIDERS.keys()),
    }
    return sha256_hex(_canon(material))[:32]


def model_version(model: dict[str, Any] | None = None) -> str:
    if not model:
        return "none"
    material = {
        "provider_id": model.get("provider_id"),
        "model_id": model.get("model_id"),
        "model_version": model.get("model_version"),
        "fingerprint": model.get("fingerprint"),
    }
    return sha256_hex(_canon(material))[:32]


def exact_cache_key(
    *,
    kind: str,
    project: str,
    operation: str,
    content: dict[str, Any] | str,
    environment: dict[str, Any] | None = None,
    model: dict[str, Any] | None = None,
    config_ver: str | None = None,
    permission_ver: str | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    """
    Exact-reuse key. All relevant dimensions are mandatory inputs to the hash.
    Approximate similarity must never produce this key.
    """
    material = {
        "kind": kind,
        "project": project,
        "operation": operation,
        "content": content if isinstance(content, str) else content,
        "environment": environment or environment_version(),
        "model": model_version(model),
        "config": config_ver or config_version(),
        "permissions": permission_ver or permission_version(),
        "extra": extra or {},
        "reuse": "exact",
    }
    return sha256_hex(_canon(material))
