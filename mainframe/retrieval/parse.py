"""Parse issue text into exact retrieval cues (no embeddings)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# File "path", line N, in name  |  path:line:  |  File path:line
STACK_RE = re.compile(
    r'(?:File\s+"([^"]+)",\s*line\s+(\d+)(?:,\s*in\s+(\w+))?)'
    r"|(?:^|\s)([\w./\\-]+\.\w+):(\d+)(?::\d+)?",
    re.MULTILINE,
)
FILENAME_RE = re.compile(
    r"(?<![\w/])((?:[\w.-]+/)*[\w.-]+\.(?:py|ts|tsx|js|jsx|go|rs|java|cs|md))(?![\w.])",
    re.IGNORECASE,
)
ERROR_RE = re.compile(
    r"(?m)^(?:\s*)((?:ValueError|TypeError|KeyError|AttributeError|RuntimeError|"
    r"AssertionError|IndexError|ImportError|Exception|Error|FAIL|FAILED)"
    r"[^\n]{0,200})",
)
IDENT_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]{2,})\b")
IMPORT_HINT_RE = re.compile(
    r"(?m)^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))",
)
QUOTED_RE = re.compile(r"[\"']([^\"']{3,80})[\"']")

STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "that",
        "this",
        "with",
        "from",
        "into",
        "when",
        "where",
        "which",
        "while",
        "should",
        "would",
        "could",
        "about",
        "error",
        "failed",
        "failure",
        "issue",
        "bug",
        "fix",
        "line",
        "file",
        "traceback",
        "stack",
        "trace",
        "most",
        "recent",
        "call",
        "last",
        "return",
        "returns",
        "true",
        "false",
        "none",
        "null",
        "def",
        "class",
        "import",
        "from",
        "self",
        "test",
        "tests",
        "http",
        "https",
        "com",
        "org",
    }
)


@dataclass
class IssueCues:
    goal: str
    raw_issue: str
    filenames: list[str] = field(default_factory=list)
    stack_frames: list[dict[str, Any]] = field(default_factory=list)
    error_messages: list[str] = field(default_factory=list)
    identifiers: list[str] = field(default_factory=list)
    quoted_strings: list[str] = field(default_factory=list)
    lexical_terms: list[str] = field(default_factory=list)
    follow_up_terms: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "filenames": self.filenames,
            "stack_frames": self.stack_frames,
            "error_messages": self.error_messages,
            "identifiers": self.identifiers,
            "quoted_strings": self.quoted_strings,
            "lexical_terms": self.lexical_terms,
            "follow_up_terms": self.follow_up_terms,
        }


def _uniq(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        k = x.casefold()
        if k in seen or not x.strip():
            continue
        seen.add(k)
        out.append(x)
    return out


def parse_issue(
    issue_text: str,
    *,
    goal: str,
    follow_up: str | None = None,
) -> IssueCues:
    """Extract exact cues; keep goal separate so lexical hits do not redefine the task."""
    text = issue_text or ""
    frames: list[dict[str, Any]] = []
    for m in STACK_RE.finditer(text):
        if m.group(1):
            frames.append(
                {
                    "path": m.group(1).replace("\\", "/"),
                    "line": int(m.group(2)),
                    "func": m.group(3),
                }
            )
        elif m.group(4):
            frames.append(
                {
                    "path": m.group(4).replace("\\", "/"),
                    "line": int(m.group(5)),
                    "func": None,
                }
            )

    filenames = _uniq([m.group(1).replace("\\", "/") for m in FILENAME_RE.finditer(text)])
    for fr in frames:
        if fr["path"] not in {f.casefold() for f in filenames}:
            filenames.append(fr["path"])

    errors = _uniq([m.group(1).strip() for m in ERROR_RE.finditer(text)])
    quoted = _uniq([m.group(1) for m in QUOTED_RE.finditer(text)])

    # Identifiers: prefer those near errors / after "in " / CamelOrSnake
    idents: list[str] = []
    for m in IDENT_RE.finditer(text):
        tok = m.group(1)
        if tok.casefold() in STOPWORDS:
            continue
        if tok.isupper() and len(tok) <= 3:
            continue
        idents.append(tok)
    idents = _uniq(idents)

    lexical = [
        t
        for t in idents
        if len(t) >= 4 and t.casefold() not in {f.casefold() for f in filenames}
    ]
    # Also split path basenames into lexical
    for fn in filenames:
        base = fn.rsplit("/", 1)[-1]
        stem = base.rsplit(".", 1)[0]
        if stem and stem.casefold() not in STOPWORDS:
            lexical.append(stem)
    lexical = _uniq(lexical)

    follow_terms: list[str] = []
    if follow_up:
        follow_terms = _uniq(
            [
                m.group(1)
                for m in IDENT_RE.finditer(follow_up)
                if m.group(1).casefold() not in STOPWORDS
            ]
            + [m.group(1).replace("\\", "/") for m in FILENAME_RE.finditer(follow_up)]
        )
        for t in follow_terms:
            if t not in lexical:
                lexical.append(t)
            if "." in t and t not in filenames:
                filenames.append(t)

    return IssueCues(
        goal=goal.strip() or "(goal not provided)",
        raw_issue=text,
        filenames=filenames,
        stack_frames=frames,
        error_messages=errors,
        identifiers=idents[:40],
        quoted_strings=quoted,
        lexical_terms=lexical[:50],
        follow_up_terms=follow_terms,
    )
