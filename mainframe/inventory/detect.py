"""Classify files: language, kind, packages, entry points, tests, deps, build config."""

from __future__ import annotations

from pathlib import Path
from typing import Any

LANG_BY_SUFFIX = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".cs": "csharp",
    ".md": "markdown",
    ".json": "json",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".toml": "toml",
    ".html": "html",
    ".css": "css",
    ".sql": "sql",
}

PACKAGE_MARKERS = {
    "package.json": "node_package",
    "pyproject.toml": "python_package",
    "setup.py": "python_package",
    "Cargo.toml": "rust_package",
    "go.mod": "go_module",
    "pom.xml": "maven_package",
}

BUILD_FILES = frozenset(
    {
        "Makefile",
        "CMakeLists.txt",
        "Dockerfile",
        "tsconfig.json",
        "webpack.config.js",
        "vite.config.ts",
        "vite.config.js",
        "pyproject.toml",
        "setup.cfg",
        "tox.ini",
        ".github/workflows",
    }
)

ENTRY_CANDIDATES = frozenset(
    {
        "main.py",
        "__main__.py",
        "cli.py",
        "index.js",
        "index.ts",
        "main.go",
        "main.rs",
        "app.py",
    }
)

GENERATED_NAMES = frozenset(
    {
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "Cargo.lock",
        "poetry.lock",
    }
)


def language_for(path: str) -> str | None:
    return LANG_BY_SUFFIX.get(Path(path).suffix.lower())


def classify_kind(rel_posix: str, *, is_symlink: bool = False) -> str:
    if is_symlink:
        return "symlink"
    name = Path(rel_posix).name
    lower = rel_posix.replace("\\", "/").lower()
    if name in PACKAGE_MARKERS:
        return "package_manifest"
    if name in GENERATED_NAMES or name.endswith(".min.js") or name.endswith(".map"):
        return "generated"
    if name in BUILD_FILES or "/.github/workflows/" in f"/{lower}/":
        return "build_config"
    if name.startswith("test_") or name.endswith("_test.py") or "/tests/" in f"/{lower}/" or name.endswith(".test.ts"):
        return "test"
    if name in ENTRY_CANDIDATES or lower.endswith("/__main__.py"):
        return "entry_point"
    if name in {"requirements.txt", "Pipfile", "go.sum"}:
        return "dependencies"
    if Path(rel_posix).suffix.lower() in LANG_BY_SUFFIX:
        return "source"
    return "other"


def detect_source_roots(paths: list[str]) -> list[str]:
    roots: set[str] = set()
    for p in paths:
        parts = p.replace("\\", "/").split("/")
        if parts[0] in {"src", "lib", "app", "mainframe", "packages", "services", "tests", "test"}:
            roots.add(parts[0])
        if len(parts) > 1 and parts[0] not in {".", "docs"}:
            # package dirs containing source
            if parts[-1].endswith((".py", ".ts", ".js", ".go", ".rs")):
                if parts[0] not in {"node_modules", "dist", "build"}:
                    roots.add(parts[0] if len(parts) > 1 else ".")
    if not roots:
        roots.add(".")
    return sorted(roots)


def detect_packages(paths: list[str]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for p in paths:
        name = Path(p).name
        if name in PACKAGE_MARKERS:
            out.append(
                {
                    "path": p.replace("\\", "/"),
                    "ecosystem": PACKAGE_MARKERS[name],
                    "dir": str(Path(p).parent).replace("\\", "/") or ".",
                }
            )
    return out


def summarize_inventory(entries: list[dict[str, Any]]) -> dict[str, Any]:
    visible = [e for e in entries if not e.get("privacy_excluded") and not e.get("ignored")]
    by_lang: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    for e in visible:
        lang = e.get("language") or "unknown"
        kind = e.get("kind") or "other"
        by_lang[lang] = by_lang.get(lang, 0) + 1
        by_kind[kind] = by_kind.get(kind, 0) + 1
    paths = [e["display_path"] for e in visible]
    return {
        "file_count": len(visible),
        "privacy_excluded_count": sum(1 for e in entries if e.get("privacy_excluded")),
        "ignored_count": sum(1 for e in entries if e.get("ignored")),
        "languages": by_lang,
        "kinds": by_kind,
        "packages": detect_packages(paths),
        "source_roots": detect_source_roots(paths),
        "entry_points": [e["display_path"] for e in visible if e.get("kind") == "entry_point"],
        "tests": [e["display_path"] for e in visible if e.get("kind") == "test"],
        "generated": [e["display_path"] for e in visible if e.get("kind") == "generated"],
        "dependencies": [e["display_path"] for e in visible if e.get("kind") == "dependencies"],
        "build_config": [e["display_path"] for e in visible if e.get("kind") == "build_config"],
        "untracked": [e["display_path"] for e in visible if e.get("git_status") == "untracked"],
        "symlinks": [e["display_path"] for e in visible if e.get("is_symlink")],
    }
