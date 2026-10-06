"""Local issue→code retrieval — exact cues + lexical ranking; optional FTS5."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from mainframe.cost_gate import authorize
from mainframe.inventory.ignore import is_privacy_excluded
from mainframe.retrieval.index import build_index, fts_search, list_code_files
from mainframe.retrieval.parse import IssueCues, parse_issue
from mainframe.retrieval.rank import (
    Hit,
    add_signal,
    context_char_count,
    expand_range,
    merge_overlapping,
)

CODE_SUFFIXES = frozenset(
    {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".cs"}
)

# Minimum score for "has evidence"; below → no_relevant_evidence
MIN_EVIDENCE_SCORE = 6.0
# Pure weak lexical without exact/stack/import/error does not count as evidence
STRONG_KINDS = frozenset(
    {
        "exact_filename",
        "stack_frame_path",
        "stack_frame_line",
        "exact_identifier",
        "error_message",
        "quoted_string",
        "import_from_stack",
        "follow_up_term",
    }
)

IMPORT_LINE_RE = re.compile(
    r"^\s*(?:from\s+([\w.]+)\s+import\s+([\w,\s*]+)|import\s+([\w.]+))",
    re.MULTILINE,
)


def _lexical_weight(overlap: int) -> float:
    return min(6.0, 1.5 * overlap)


def _read_lines(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    if text.startswith("\ufeff"):
        text = text[1:]
    return text.splitlines()


def _path_matches(rel: str, cue: str) -> bool:
    a = rel.replace("\\", "/").casefold()
    b = cue.replace("\\", "/").casefold()
    return a == b or a.endswith("/" + b) or a.split("/")[-1] == b.split("/")[-1]


def _module_to_candidates(mod: str, root: Path) -> list[str]:
    """Map Python import module to relative path candidates."""
    parts = mod.replace(".", "/")
    cands = [f"{parts}.py", f"{parts}/__init__.py"]
    # also last segment
    if "/" in parts:
        cands.append(f"{parts.split('/')[-1]}.py")
    return cands


def _imports_in_file(lines: list[str]) -> list[str]:
    mods: list[str] = []
    text = "\n".join(lines)
    for m in IMPORT_LINE_RE.finditer(text):
        if m.group(1):
            mods.append(m.group(1))
        if m.group(3):
            mods.append(m.group(3))
    return mods


def _find_identifier_lines(lines: list[str], ident: str) -> list[int]:
    out: list[int] = []
    # word boundary-ish
    pat = re.compile(rf"\b{re.escape(ident)}\b")
    for i, ln in enumerate(lines, start=1):
        if pat.search(ln):
            out.append(i)
    return out


def _find_substring_lines(lines: list[str], needle: str) -> list[int]:
    if not needle or len(needle) < 3:
        return []
    n = needle.casefold()
    return [i for i, ln in enumerate(lines, start=1) if n in ln.casefold()]


def _attach_snippet(hit: Hit, lines: list[str]) -> None:
    start, end = expand_range(len(lines), hit.start_line, hit.end_line)
    hit.start_line = start
    hit.end_line = end
    hit.lines = lines[start - 1 : end]
    # Numbered snippet for readability
    hit.snippet = "\n".join(f"{start + i}|{ln}" for i, ln in enumerate(hit.lines))


def _ensure_hit(bucket: dict[str, Hit], path: str, start: int, end: int) -> Hit:
    key = f"{path.casefold()}::{start}::{end}"
    if key not in bucket:
        bucket[key] = Hit(path=path.replace("\\", "/"), start_line=start, end_line=end)
    return bucket[key]


def retrieve(
    root: Path,
    *,
    issue_text: str,
    goal: str,
    follow_up: str | None = None,
    use_fts5: bool | None = None,
    top_k: int = 8,
) -> dict[str, Any]:
    """
    Rank files/ranges for an issue.

    ``goal`` is always returned unchanged alongside search terms so lexical
    matches cannot silently redefine the user's task.

    ``use_fts5``: True/False force; None = use measured policy (see accept).
    """
    gate = authorize("tool", "local.issue_retrieval", local=True)
    if not gate.allowed:
        return {"ok": False, "cost_gate": gate.to_dict()}

    root = root.resolve()
    cues = parse_issue(issue_text, goal=goal, follow_up=follow_up)

    # Measured policy file written by accept; default False until proven useful
    policy_path = Path(__file__).resolve().parent / "fts5_policy.json"
    policy_use = False
    if policy_path.is_file():
        try:
            import json

            policy_use = bool(json.loads(policy_path.read_text(encoding="utf-8")).get("use_fts5"))
        except (OSError, ValueError):
            policy_use = False
    fts_enabled = policy_use if use_fts5 is None else bool(use_fts5)

    files = list_code_files(root)
    # Filter to code-ish
    files = [(r, p) for r, p in files if Path(r).suffix.lower() in CODE_SUFFIXES or True]

    content: dict[str, list[str]] = {}
    for rel, full in files:
        content[rel.replace("\\", "/")] = _read_lines(full)

    bucket: dict[str, Hit] = {}

    # --- exact filename ---
    for cue_fn in cues.filenames:
        for rel in content:
            if _path_matches(rel, cue_fn):
                hit = _ensure_hit(bucket, rel, 1, min(12, max(1, len(content[rel]))))
                add_signal(hit, "exact_filename", cue_fn)

    # --- stack frames ---
    stack_paths: list[str] = []
    for fr in cues.stack_frames:
        matched_rel = None
        for rel in content:
            if _path_matches(rel, fr["path"]):
                matched_rel = rel
                break
        if not matched_rel:
            continue
        stack_paths.append(matched_rel)
        line = int(fr["line"])
        total = len(content[matched_rel])
        line = min(max(1, line), max(1, total))
        hit = _ensure_hit(bucket, matched_rel, line, line)
        add_signal(hit, "stack_frame_path", fr["path"])
        add_signal(hit, "stack_frame_line", {"line": line, "func": fr.get("func")})

    # --- import edges from stack files (bug often outside stack) ---
    for sp in stack_paths:
        for mod in _imports_in_file(content[sp]):
            for cand in _module_to_candidates(mod, root):
                for rel in content:
                    if _path_matches(rel, cand) or rel.replace("\\", "/").endswith(
                        "/" + cand.replace("\\", "/")
                    ):
                        # Prefer identifier/error lines in imported module
                        lines = content[rel]
                        centers = []
                        for err in cues.error_messages:
                            # strip exception type prefix for body search
                            body = err.split(":", 1)[-1].strip() if ":" in err else err
                            centers.extend(_find_substring_lines(lines, body))
                        for ident in cues.identifiers[:15]:
                            centers.extend(_find_identifier_lines(lines, ident)[:3])
                        if not centers:
                            centers = [1]
                        for c in centers[:5]:
                            hit = _ensure_hit(bucket, rel, c, c)
                            add_signal(
                                hit,
                                "import_from_stack",
                                {"from": sp, "import": mod},
                            )

    # --- error messages / quoted strings / identifiers ---
    for rel, lines in content.items():
        for err in cues.error_messages:
            body = err.split(":", 1)[-1].strip() if ":" in err else err
            for ln in _find_substring_lines(lines, body)[:5]:
                hit = _ensure_hit(bucket, rel, ln, ln)
                add_signal(hit, "error_message", err[:120])
            # also full error line fragment
            for ln in _find_substring_lines(lines, err[:60])[:3]:
                hit = _ensure_hit(bucket, rel, ln, ln)
                add_signal(hit, "error_message", err[:120], weight=4.0)

        for qs in cues.quoted_strings:
            for ln in _find_substring_lines(lines, qs)[:5]:
                hit = _ensure_hit(bucket, rel, ln, ln)
                add_signal(hit, "quoted_string", qs)

        for ident in cues.identifiers[:25]:
            locs = _find_identifier_lines(lines, ident)
            # Cap per file to avoid flooding
            for ln in locs[:8]:
                hit = _ensure_hit(bucket, rel, ln, ln)
                kind = (
                    "follow_up_term"
                    if ident in cues.follow_up_terms
                    else "exact_identifier"
                )
                add_signal(hit, kind, ident)

        # weak lexical: term frequency in file (basename + content tokens)
        overlap = 0
        joined = "\n".join(lines).casefold()
        matched_terms: list[str] = []
        for term in cues.lexical_terms[:20]:
            t = term.casefold()
            if len(t) < 4:
                continue
            if t in joined or t in rel.casefold():
                overlap += 1
                matched_terms.append(term)
        if overlap:
            hit = _ensure_hit(bucket, rel, 1, min(8, max(1, len(lines))))
            add_signal(
                hit,
                "lexical_overlap",
                {"terms": matched_terms[:8], "count": overlap},
                weight=_lexical_weight(overlap),
            )

    # --- optional FTS5 ---
    fts_hits_raw: list[dict[str, Any]] = []
    fts_index_meta: dict[str, Any] | None = None
    if fts_enabled:
        fts_index_meta = build_index(root)
        fts_hits_raw = fts_search(
            root,
            cues.lexical_terms + cues.identifiers + [Path(f).stem for f in cues.filenames],
            limit=15,
        )
        for fh in fts_hits_raw:
            rel = fh["path"]
            if rel not in content:
                continue
            lines = content[rel]
            # Map snippet to first lexical hit line if possible
            centers = []
            for term in cues.lexical_terms[:10]:
                centers.extend(_find_identifier_lines(lines, term)[:2])
            c = centers[0] if centers else 1
            hit = _ensure_hit(bucket, rel, c, c)
            add_signal(hit, "fts5_bm25", {"score": fh.get("fts_score"), "snip": fh.get("snippet")})

    hits = list(bucket.values())
    for h in hits:
        lines = content.get(h.path, [])
        if lines:
            _attach_snippet(h, lines)

    merged = merge_overlapping(hits)
    # Drop privacy
    merged = [h for h in merged if not is_privacy_excluded(h.path)]
    merged.sort(key=lambda h: (-h.score, h.path, h.start_line))
    top = merged[:top_k]

    has_strong = any(
        any(s["kind"] in STRONG_KINDS for s in h.signals) and h.score >= MIN_EVIDENCE_SCORE
        for h in top
    )
    no_evidence = not has_strong

    return {
        "ok": True,
        "goal": cues.goal,
        "search_terms": {
            "filenames": cues.filenames,
            "identifiers": cues.identifiers,
            "lexical_terms": cues.lexical_terms,
            "error_messages": cues.error_messages,
            "follow_up_terms": cues.follow_up_terms,
            "stack_frames": cues.stack_frames,
        },
        "results": [
            {
                "path": h.path,
                "start_line": h.start_line,
                "end_line": h.end_line,
                "score": round(h.score, 3),
                "signals": h.signals,
                "snippet": h.snippet,
                "line_count": len(h.lines),
            }
            for h in top
        ],
        "no_relevant_evidence": no_evidence,
        "context_chars": context_char_count(top),
        "fts5_used": bool(fts_enabled and fts_hits_raw is not None and fts_enabled),
        "fts5_index": fts_index_meta,
        "remote_vector_db_used": False,
        "paid_embedding_used": False,
        "deduplicated": True,
        "goal_preserved": cues.goal == (goal.strip() or "(goal not provided)"),
    }
