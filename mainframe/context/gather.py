"""Gather progressive context sections from local tools."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from mainframe.context.rank import EvidenceItem
from mainframe.context.tokens import estimate_tokens
from mainframe.contracts.build import build_contract
from mainframe.inventory.ignore import should_skip_dir
from mainframe.retrieval.retrieve import retrieve


def _est(text: str) -> int:
    return estimate_tokens(text)


# Fix circular - don't import estimate_via_tokens from rank
def gather_evidence(
    root: Path,
    *,
    request_text: str,
    goal: str | None = None,
    contract: dict[str, Any] | None = None,
    diagnostics_text: str | None = None,
    include_docs_module: str | None = None,
    include_docs_attr: str | None = None,
) -> list[EvidenceItem]:
    root = root.resolve()
    items: list[EvidenceItem] = []
    goal = goal or request_text

    # --- Task contract ---
    if contract is None:
        built = build_contract(request_text)
        contract = built.get("contract") if built.get("ok") else None
    if contract:
        inv = contract.get("invariants") or []
        body = (
            f"KIND: {contract.get('kind')}\n"
            f"DESIRED: {contract.get('desired_behavior')}\n"
            f"CONSTRAINTS: {contract.get('constraints')}\n"
            f"INVARIANTS: {inv}\n"
            f"ACCEPTANCE: {contract.get('acceptance_checks')}\n"
            f"SIDE_EFFECTS: {contract.get('permitted_side_effects')}\n"
            f"ASSUMPTIONS: {contract.get('assumptions')}\n"
            f"INTENT: {contract.get('intent_natural_language')}\n"
        )
        items.append(
            EvidenceItem(
                id="contract",
                kind="contract",
                critical="contract",
                path=None,
                start_line=None,
                end_line=None,
                signature=None,
                content=body,
                pointers=["contract"],
                relevance=1.0,
                tokens_est=_est(body),
                trust="local",
                attribution="task_contract",
            )
        )
        for i, invariant in enumerate(inv):
            text = str(invariant)
            items.append(
                EvidenceItem(
                    id=f"invariant:{i}",
                    kind="invariant",
                    critical="invariant",
                    path=None,
                    start_line=None,
                    end_line=None,
                    signature=None,
                    content=text,
                    pointers=[f"invariant:{i}"],
                    relevance=0.95,
                    tokens_est=_est(text),
                    trust="local",
                )
            )

    # --- Repository overview (bounded, no file bodies) ---
    overview = _lite_overview(root)
    ov_text = (
        f"files={overview.get('file_count')} packages={overview.get('packages')} "
        f"tests={overview.get('tests')}"
    )
    items.append(
        EvidenceItem(
            id="overview",
            kind="overview",
            critical="normal",
            path=None,
            start_line=None,
            end_line=None,
            signature=None,
            content=ov_text,
            pointers=["overview"],
            relevance=0.4,
            tokens_est=_est(ov_text),
            trust="local",
        )
    )

    # --- Retrieval for relevant ranges ---
    ret = retrieve(root, issue_text=request_text, goal=goal, use_fts5=False, top_k=8)
    for i, hit in enumerate(ret.get("results") or []):
        path = hit.get("path") or ""
        snippet = hit.get("snippet") or ""
        # Detect if this looks like a signature-bearing range
        sig = _extract_signature_from_snippet(snippet)
        critical = "signature" if sig else "source_pointer"
        # Deprioritize irrelevant / noise paths
        relevance = min(1.0, float(hit.get("score") or 0) / 50.0)
        if "irrelevant" in path or path.endswith(".log"):
            relevance *= 0.05
            critical = "normal"
        ptr = f"{path}:{hit.get('start_line')}-{hit.get('end_line')}"
        items.append(
            EvidenceItem(
                id=f"range:{i}:{path}",
                kind="range",
                critical=critical,  # type: ignore[arg-type]
                path=path,
                start_line=hit.get("start_line"),
                end_line=hit.get("end_line"),
                signature=sig,
                content=snippet if not sig else f"{sig}\n{snippet}",
                pointers=[ptr],
                relevance=relevance,
                tokens_est=_est(snippet),
                trust="local",
                attribution="inventory_retrieve",
            )
        )

    # --- Relevant symbols (AST defs mentioned in request / retrieval) ---
    for sym in _collect_symbols(root, request_text, ret):
        items.append(sym)

    # --- Diagnostic evidence ---
    diag = diagnostics_text or _load_default_diagnostics(root)
    if diag:
        # Split repeated log blocks; keep first occurrence higher novelty later
        chunks = _split_diag_chunks(diag)
        for i, chunk in enumerate(chunks):
            is_log = "TRACE" in chunk or chunk.count("\n") > 20
            items.append(
                EvidenceItem(
                    id=f"diag:{i}",
                    kind="log" if is_log else "diagnostic",
                    critical="diagnostic" if not is_log or i == 0 else "normal",
                    path=_diag_path_hint(chunk),
                    start_line=None,
                    end_line=None,
                    signature=None,
                    content=chunk[:4000],
                    pointers=[f"{m[0]}:{m[1]}" for m in re.findall(r"([\w./\\-]+\.py):(\d+)", chunk)[:5]],
                    relevance=0.9 if ("Error" in chunk or "FAIL" in chunk or "Assertion" in chunk) else 0.3,
                    tokens_est=_est(chunk[:4000]),
                    trust="local",
                    attribution="diagnostics",
                )
            )

    # --- External API: prefer installed types ---
    if include_docs_module:
        from mainframe.context.docs_cache import installed_api_excerpt

        doc = installed_api_excerpt(include_docs_module, include_docs_attr)
        if doc.get("ok"):
            body = doc["body"]
            items.append(
                EvidenceItem(
                    id=f"docs:{include_docs_module}",
                    kind="docs",
                    critical="signature" if include_docs_attr else "normal",
                    path=None,
                    start_line=None,
                    end_line=None,
                    signature=include_docs_attr,
                    content=body,
                    pointers=[f"installed:{include_docs_module}"],
                    relevance=0.7,
                    tokens_est=_est(body),
                    trust="installed_types",
                    attribution=doc.get("attribution"),
                )
            )

    return items


def _lite_overview(root: Path) -> dict[str, Any]:
    files = 0
    packages: list[str] = []
    tests: list[str] = []
    for dirpath, dirnames, filenames in __import__("os").walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
        base = Path(dirpath)
        for name in filenames:
            full = base / name
            try:
                rel = full.relative_to(root).as_posix()
            except ValueError:
                continue
            files += 1
            if name in {"package.json", "pyproject.toml", "__init__.py"} and "/" in rel:
                packages.append(rel.split("/")[0])
            if name.startswith("test_") and name.endswith(".py"):
                tests.append(rel)
    return {
        "file_count": files,
        "packages": sorted(set(packages))[:20],
        "tests": tests[:20],
    }


def _extract_signature_from_snippet(snippet: str) -> str | None:
    for ln in snippet.splitlines():
        s = re.sub(r"^\d+\|", "", ln).strip()
        if s.startswith("def ") or s.startswith("async def ") or s.startswith("class "):
            return s
    return None


def _collect_symbols(root: Path, request: str, ret: dict[str, Any]) -> list[EvidenceItem]:
    names = set(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]{2,})\b", request))
    out: list[EvidenceItem] = []
    for hit in ret.get("results") or []:
        path = hit.get("path")
        if not path or "irrelevant" in path:
            continue
        full = root / path
        if not full.is_file():
            continue
        try:
            src = full.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(src)
        except (OSError, SyntaxError):
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
                sig = f"def {node.name}({', '.join(a.arg for a in node.args.args)})"
                # Full signature line preserved
                line = src.splitlines()[node.lineno - 1] if node.lineno <= len(src.splitlines()) else sig
                out.append(
                    EvidenceItem(
                        id=f"symbol:{path}:{node.name}",
                        kind="symbol",
                        critical="signature",
                        path=path,
                        start_line=node.lineno,
                        end_line=node.end_lineno or node.lineno,
                        signature=line.strip(),
                        content=line.strip(),
                        pointers=[f"{path}:{node.lineno}"],
                        relevance=0.95,
                        tokens_est=_est(line),
                        trust="local",
                    )
                )
    return out


def _load_default_diagnostics(root: Path) -> str | None:
    for cand in ("diagnostics.txt", "logs/repeated.log", "pytest.out"):
        p = root / cand
        if p.is_file():
            try:
                return p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
    # concatenate logs/
    logdir = root / "logs"
    if logdir.is_dir():
        parts = []
        for f in sorted(logdir.glob("*.log")):
            parts.append(f.read_text(encoding="utf-8", errors="replace"))
        if parts:
            return "\n".join(parts)
    return None


def _split_diag_chunks(text: str) -> list[str]:
    # Keep assertion/error blocks intact; separate huge repeated tails
    lines = text.splitlines()
    if len(lines) <= 40:
        return [text]
    head = "\n".join(lines[:30])
    # Detect repetition in tail
    tail_lines = lines[30:]
    uniq = []
    prev = None
    repeat = 0
    for ln in tail_lines:
        if ln == prev:
            repeat += 1
            continue
        if repeat:
            uniq.append(f"... repeated prior line {repeat} times ...")
            repeat = 0
        uniq.append(ln)
        prev = ln
    if repeat:
        uniq.append(f"... repeated prior line {repeat} times ...")
    return [head, "\n".join(uniq[:40])]


def _diag_path_hint(chunk: str) -> str | None:
    m = re.search(r"([\w./\\-]+\.py)", chunk)
    return m.group(1).replace("\\", "/") if m else None
