"""Pinned Void evaluation summary for acceptance (no vendored workbench code)."""

from __future__ import annotations

from typing import Any

VOID_PIN = "b3166e7ef2aefbdfeb139445fdf248a561b85d4d"


def void_evaluation_summary() -> dict[str, Any]:
    return {
        "pin_commit": VOID_PIN,
        "license": "Apache-2.0",
        "copyright_appendix": "Copyright 2025 Glass Devtools, Inc.",
        "inherited_vscode_license": "MIT (microsoft/vscode) + third-party notices — retain if forking",
        "status": "deprecated_archived_reference_only",
        "copy_workbench_services": False,
        "prefer_extension": True,
        "fork_optional": True,
        "services_evaluated": {
            "editCodeService": "diff zones / fast-slow apply — concept only; use MAINFRAME patching",
            "voidModelService": "URI↔model sync — concept only; use TextDocument + shared buffers",
            "completion_ux": "budgeted only with eligible local model",
            "context_selection": "extension selection → shared task context",
        },
        "docs": ["docs/VOID_EVAL.md", "docs/VOID_FORK_PLAN.md", "docs/NOTICES.md"],
        "code_copied_from_void": False,
    }
