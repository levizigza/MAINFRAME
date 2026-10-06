"""Classify verification failures — product vs environment vs tooling."""

from __future__ import annotations

from typing import Any, Literal

FailureKind = Literal[
    "product_defect",
    "missing_dependency",
    "unavailable_service",
    "flaky_check",
    "environment_failure",
    "preexisting_failure",
    "edge_case_failure",
    "integrity_violation",
    "stale_verification",
]


def classify_run_failure(
    *,
    exit_code: int | None,
    stdout: str = "",
    stderr: str = "",
    error: str | None = None,
    reproduced_before_repair: bool | None = None,
) -> dict[str, Any]:
    text = f"{stdout}\n{stderr}\n{error or ''}".lower()

    if "no module named" in text or "modulenotfounderror" in text:
        return {
            "kind": "missing_dependency",
            "product_defect": False,
            "detail": "Import/module missing",
        }
    if "connection refused" in text or "timed out" in text or "offline" in text:
        if "pytest" not in text and "assert" not in text:
            return {
                "kind": "unavailable_service",
                "product_defect": False,
                "detail": "Network/service unavailable",
            }
    if "permission denied" in text or "not a valid win32" in text:
        return {
            "kind": "environment_failure",
            "product_defect": False,
            "detail": "Environment/OS failure",
        }
    if exit_code is None and error and "timeout" in (error or "").lower():
        return {
            "kind": "environment_failure",
            "product_defect": False,
            "detail": "Process timeout",
        }
    # Flaky heuristic: explicit marker only (do not invent)
    if "flaky" in text or "intermittent" in text:
        return {
            "kind": "flaky_check",
            "product_defect": False,
            "detail": "Marked flaky in output",
        }

    if reproduced_before_repair is True:
        return {
            "kind": "preexisting_failure",
            "product_defect": True,
            "detail": "Failure reproduced before repair attempt",
        }

    if exit_code not in (0, None) and ("assert" in text or "fail" in text or "error" in text):
        return {
            "kind": "product_defect",
            "product_defect": True,
            "detail": "Test/assertion failure in product code",
        }

    if exit_code not in (0, None):
        return {
            "kind": "environment_failure",
            "product_defect": False,
            "detail": "Nonzero exit without clear product assertion",
        }

    return {
        "kind": "product_defect",
        "product_defect": False,
        "detail": "passed_or_unclear",
    }
