"""Provenance labels — distinguish tool facts from approximations and hypotheses."""

from __future__ import annotations

from typing import Any, Literal

EvidenceKind = Literal[
    "language_server_fact",  # LSP / Jedi / Pyright structured result
    "parser_approximate",  # stdlib ast / tree-sitter-like local parse
    "lexical_fallback",  # text search when tooling unavailable
    "installed_api_fact",  # importlib/inspect against installed package
    "model_hypothesis",  # never emitted by codeintel; rejected if present
]

TOOLING_LIMITATION = "tooling_unavailable"


def evidence(
    kind: EvidenceKind,
    *,
    tool: str,
    detail: str | None = None,
    limitation: str | None = None,
) -> dict[str, Any]:
    if kind == "model_hypothesis":
        raise ValueError("codeintel must not emit model_hypothesis evidence")
    return {
        "kind": kind,
        "tool": tool,
        "detail": detail,
        "limitation": limitation,
        "model_service_used": False,
    }
