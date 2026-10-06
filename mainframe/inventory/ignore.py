"""Ignore rules and privacy exclusions for repository inventory."""

from __future__ import annotations

import re
from pathlib import Path

# Always excluded from inventory content (privacy / secrets).
PRIVACY_BASENAMES = frozenset(
    {
        ".env",
        ".env.local",
        ".env.production",
        "credentials.json",
        "secrets.json",
        "id_rsa",
        "id_ed25519",
        "private.pem",
        ".npmrc",
        "auth.json",
    }
)
PRIVACY_SUFFIXES = (".pem", ".p12", ".pfx", ".key")
PRIVACY_NAME_RE = re.compile(
    r"(?i)(^|[/\\])(\.env(\..+)?|.*secret.*|.*credential.*|.*password.*|.*token\.json)(/|$)"
)

DEFAULT_IGNORE_DIRS = frozenset(
    {
        ".git",
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
        "dist",
        "build",
        ".mainframe",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".next",
        "coverage",
        ".idea",
        ".vscode",
    }
)

GENERATED_GLOBS = (
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "*.min.js",
    "*.min.css",
    "*.map",
    "*.pyc",
)


def is_privacy_excluded(rel_posix: str) -> bool:
    name = Path(rel_posix).name
    if name in PRIVACY_BASENAMES:
        return True
    if name.endswith(PRIVACY_SUFFIXES):
        return True
    if PRIVACY_NAME_RE.search(rel_posix.replace("\\", "/")):
        return True
    return False


def load_gitignore_patterns(root: Path) -> list[str]:
    patterns: list[str] = []
    gi = root / ".gitignore"
    if gi.is_file():
        for line in gi.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            patterns.append(s)
    return patterns


def path_matches_gitignore(rel_posix: str, patterns: list[str]) -> bool:
    """Minimal gitignore matcher (glob-ish) — good enough for inventory fixtures."""
    path = rel_posix.replace("\\", "/").lstrip("./")
    for pat in patterns:
        negated = pat.startswith("!")
        p = pat[1:] if negated else pat
        p = p.rstrip("/")
        if p.startswith("/"):
            p = p[1:]
        matched = _simple_match(path, p) or _simple_match(Path(path).name, p)
        if matched:
            return not negated
    return False


def _simple_match(path: str, pattern: str) -> bool:
    if pattern == path:
        return True
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return path == prefix or path.startswith(prefix + "/")
    if pattern.endswith("/*"):
        prefix = pattern[:-2]
        if path.startswith(prefix + "/"):
            rest = path[len(prefix) + 1 :]
            return "/" not in rest
    if "*" in pattern or "?" in pattern:
        rx = re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".")
        return re.fullmatch(rx, path) is not None or re.fullmatch(rx, Path(path).name) is not None
    if path.startswith(pattern + "/"):
        return True
    return False


def should_skip_dir(name: str) -> bool:
    return name in DEFAULT_IGNORE_DIRS
