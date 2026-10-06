"""Stdlib AST parser — definitions, references, imports, callers (approximate)."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from mainframe.codeintel.provenance import evidence
from mainframe.codeintel.versions import content_version, range_dict


@dataclass
class SymbolDef:
    name: str
    kind: str  # function | class | async_function
    path: str
    lineno: int
    col: int
    end_lineno: int
    qualname: str
    module: str


@dataclass
class Index:
    root: Path
    files: dict[str, list[str]] = field(default_factory=dict)  # rel -> lines
    defs: list[SymbolDef] = field(default_factory=list)
    # (rel, lineno, name) call sites
    calls: list[dict[str, Any]] = field(default_factory=list)
    imports: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    versions: dict[str, dict[str, Any]] = field(default_factory=dict)


def _module_name(root: Path, rel: str) -> str:
    p = rel.replace("\\", "/")
    if p.endswith("/__init__.py"):
        p = p[: -len("/__init__.py")]
    elif p.endswith(".py"):
        p = p[:-3]
    return p.replace("/", ".")


def _walk_py(root: Path) -> Iterator[tuple[str, Path]]:
    skip = {".git", "__pycache__", ".venv", "venv", "node_modules", ".mainframe", "dist", "build"}
    for dirpath, dirnames, filenames in __import__("os").walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in skip]
        base = Path(dirpath)
        for name in filenames:
            if not name.endswith(".py"):
                continue
            full = base / name
            try:
                rel = full.relative_to(root).as_posix()
            except ValueError:
                continue
            yield rel, full


def build_ast_index(root: Path) -> Index:
    root = root.resolve()
    idx = Index(root=root)
    for rel, full in _walk_py(root):
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if text.startswith("\ufeff"):
            text = text[1:]
        lines = text.splitlines()
        idx.files[rel] = lines
        idx.versions[rel] = content_version(full)
        try:
            tree = ast.parse(text, filename=rel)
        except SyntaxError:
            continue
        mod = _module_name(root, rel)
        idx.imports[rel] = []

        class Visitor(ast.NodeVisitor):
            def __init__(self) -> None:
                self.stack: list[str] = []

            def _qual(self, name: str) -> str:
                return ".".join(self.stack + [name]) if self.stack else name

            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                self._add_def(node, "function")
                self.stack.append(node.name)
                self.generic_visit(node)
                self.stack.pop()

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
                self._add_def(node, "async_function")
                self.stack.append(node.name)
                self.generic_visit(node)
                self.stack.pop()

            def visit_ClassDef(self, node: ast.ClassDef) -> None:
                self._add_def(node, "class")
                self.stack.append(node.name)
                self.generic_visit(node)
                self.stack.pop()

            def _add_def(self, node: ast.AST, kind: str) -> None:
                name = getattr(node, "name", "")
                idx.defs.append(
                    SymbolDef(
                        name=name,
                        kind=kind,
                        path=rel,
                        lineno=getattr(node, "lineno", 1),
                        col=getattr(node, "col_offset", 0),
                        end_lineno=getattr(node, "end_lineno", getattr(node, "lineno", 1)),
                        qualname=f"{mod}.{self._qual(name)}",
                        module=mod,
                    )
                )

            def visit_Call(self, node: ast.Call) -> None:
                name = _call_name(node.func)
                if name:
                    idx.calls.append(
                        {
                            "path": rel,
                            "lineno": node.lineno,
                            "col": node.col_offset,
                            "name": name,
                            "simple": name.split(".")[-1],
                        }
                    )
                self.generic_visit(node)

            def visit_Import(self, node: ast.Import) -> None:
                for a in node.names:
                    idx.imports[rel].append(
                        {
                            "kind": "import",
                            "module": a.name,
                            "alias": a.asname,
                            "lineno": node.lineno,
                        }
                    )
                self.generic_visit(node)

            def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
                mod = node.module or ""
                for a in node.names:
                    idx.imports[rel].append(
                        {
                            "kind": "from",
                            "module": mod,
                            "name": a.name,
                            "alias": a.asname,
                            "lineno": node.lineno,
                        }
                    )
                self.generic_visit(node)

        Visitor().visit(tree)
    return idx


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_name(node.value)
        if base:
            return f"{base}.{node.attr}"
        return node.attr
    return None


def find_defs_by_name(idx: Index, name: str, *, module_hint: str | None = None) -> list[SymbolDef]:
    hits = [d for d in idx.defs if d.name == name]
    if module_hint:
        mh = module_hint.replace("\\", "/").replace("/", ".")
        filtered = [
            d
            for d in hits
            if d.module == mh
            or d.module.endswith("." + mh)
            or d.path.replace("\\", "/").startswith(mh.replace(".", "/"))
            or mh in d.qualname
        ]
        if filtered:
            return filtered
    return hits


def find_callers(idx: Index, defn: SymbolDef) -> list[dict[str, Any]]:
    """Locate call sites that refer to this specific definition (import-aware)."""
    out: list[dict[str, Any]] = []
    for rel, imps in idx.imports.items():
        local_names: set[str] = set()
        for im in imps:
            if im["kind"] == "from":
                if im.get("name") == defn.name and _modules_compatible(
                    im.get("module") or "", defn.module
                ):
                    # Prefer exact module equality when possible
                    if _module_exact_or_suffix(im.get("module") or "", defn.module):
                        local_names.add(im.get("alias") or defn.name)
            elif im["kind"] == "import":
                mod = im.get("module") or ""
                if _module_exact_or_suffix(mod, defn.module):
                    alias = im.get("alias") or mod
                    local_names.add(f"{alias}.{defn.name}")

        if _module_name(idx.root, rel) == defn.module:
            local_names.add(defn.name)

        for call in idx.calls:
            if call["path"] != rel:
                continue
            if call["name"] in local_names:
                out.append(call)

    seen: set[tuple[Any, ...]] = set()
    uniq: list[dict[str, Any]] = []
    for c in out:
        key = (c["path"], c["lineno"], c["col"], c["name"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)
    return uniq


def _module_exact_or_suffix(imported: str, defined: str) -> bool:
    a = imported.replace("\\", "/").replace("/", ".")
    b = defined.replace("\\", "/").replace("/", ".")
    return a == b or b.endswith("." + a) or a.endswith("." + b)


def _modules_compatible(a: str, b: str) -> bool:
    a = a.replace("\\", "/").replace("/", ".")
    b = b.replace("\\", "/").replace("/", ".")
    return a == b or a.endswith("." + b) or b.endswith("." + a) or a.split(".")[-1] == b.split(".")[-1]


def def_to_result(idx: Index, d: SymbolDef) -> dict[str, Any]:
    full = idx.root / d.path
    return {
        "name": d.name,
        "kind": d.kind,
        "qualname": d.qualname,
        "module": d.module,
        "range": range_dict(
            full,
            d.lineno,
            d.col,
            d.end_lineno,
            d.col,
            version=idx.versions.get(d.path),
        ),
        "evidence": evidence(
            "parser_approximate",
            tool="stdlib_ast",
            detail="Definition from ast.parse",
        ),
    }
