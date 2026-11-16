"""Deterministic cross-file import ↔ definition alignment.

When ``from pkg.mod import name`` cannot resolve ``name`` in the target module
but a camelCase/snake_case near-miss exists, propose renaming the definition
to match the import (preserves the public import name).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any


def _camel_to_snake(name: str) -> str:
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def _snake_to_camel(name: str) -> str:
    parts = name.split("_")
    if not parts:
        return name
    return parts[0] + "".join(p.title() for p in parts[1:] if p)


def _variants(name: str) -> set[str]:
    out = {name, name.casefold()}
    snake = _camel_to_snake(name)
    camel = _snake_to_camel(name)
    out.update({snake, camel, snake.casefold(), camel.casefold()})
    # PascalCase from snake
    if "_" in name:
        out.add("".join(p.title() for p in name.split("_") if p))
    return {v for v in out if v}


def _module_path(root: Path, module: str) -> Path | None:
    """Resolve dotted module to a .py path under root (best-effort, no sys.path)."""
    parts = module.split(".")
    candidates = [
        root.joinpath(*parts).with_suffix(".py"),
        root.joinpath(*parts, "__init__.py"),
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def _defined_names(tree: ast.AST) -> dict[str, ast.AST]:
    found: dict[str, ast.AST] = {}
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found[node.name] = node
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    found[t.id] = node
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            found[node.target.id] = node
    return found


def _line_span_text(src: str, node: ast.AST) -> tuple[str, str] | None:
    """Return (old_line_prefix_for_def, new) for renaming a def/class line only."""
    if not hasattr(node, "lineno"):
        return None
    lines = src.splitlines(keepends=True)
    idx = int(node.lineno) - 1
    if idx < 0 or idx >= len(lines):
        return None
    return lines[idx], lines[idx]


def propose_import_align_edits(root: Path) -> dict[str, Any]:
    """
    Scan Python files for unresolved imports with a local near-miss definition.

    Returns proposal-only edits (rename definition to match imported name).
    """
    root = root.resolve()
    edits: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []

    for py in sorted(root.rglob("*.py")):
        if any(part.startswith(".") for part in py.parts):
            continue
        try:
            src = py.read_text(encoding="utf-8")
            tree = ast.parse(src)
        except (OSError, SyntaxError):
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            # Relative imports: treat as under this package
            mod = node.module
            if node.level and node.level > 0:
                # resolve relative to file package
                pkg_parts = list(py.relative_to(root).parts[:-1])
                for _ in range(node.level - 1):
                    if pkg_parts:
                        pkg_parts.pop()
                if mod:
                    mod = ".".join(pkg_parts + mod.split(".")) if pkg_parts else mod
                else:
                    mod = ".".join(pkg_parts)

            target = _module_path(root, mod)
            if target is None or not target.is_file():
                continue
            try:
                t_src = target.read_text(encoding="utf-8")
                t_tree = ast.parse(t_src)
            except (OSError, SyntaxError):
                continue
            defined = _defined_names(t_tree)

            for alias in node.names:
                imported = alias.name
                if imported == "*":
                    continue
                if imported in defined:
                    continue
                # Near-miss: camel/snake mismatch
                match_name = None
                for def_name in defined:
                    if def_name == imported:
                        match_name = def_name
                        break
                    if imported in _variants(def_name) or def_name in _variants(imported):
                        match_name = def_name
                        break
                if not match_name or match_name == imported:
                    continue

                def_node = defined[match_name]
                span = _line_span_text(t_src, def_node)
                if not span:
                    continue
                old_line, _ = span
                # Rename only the identifier on the definition line
                if isinstance(def_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    new_line = re.sub(
                        rf"\bdef\s+{re.escape(match_name)}\b",
                        f"def {imported}",
                        old_line,
                        count=1,
                    )
                elif isinstance(def_node, ast.ClassDef):
                    new_line = re.sub(
                        rf"\bclass\s+{re.escape(match_name)}\b",
                        f"class {imported}",
                        old_line,
                        count=1,
                    )
                else:
                    new_line = re.sub(
                        rf"\b{re.escape(match_name)}\b",
                        imported,
                        old_line,
                        count=1,
                    )
                if new_line == old_line:
                    continue
                rel = str(target.relative_to(root)).replace("\\", "/")
                edit = {"path": rel, "old": old_line, "new": new_line}
                # Dedup
                if edit not in edits:
                    edits.append(edit)
                    evidence.append(
                        {
                            "importer": str(py.relative_to(root)).replace("\\", "/"),
                            "module": mod,
                            "imported": imported,
                            "found_as": match_name,
                            "fix": rel,
                        }
                    )

    return {
        "edits": edits,
        "evidence": evidence,
        "source": "import_symbol_align",
        "model_service_used": False,
    }
