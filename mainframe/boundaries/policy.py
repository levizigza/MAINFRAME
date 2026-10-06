"""Executable-tool policy — what counts as code; trust levels; non-sandbox myths."""

from __future__ import annotations

from typing import Any, Literal

TrustLevel = Literal["trusted_local", "untrusted"]

# Explicit: these are NOT security sandboxes.
NOT_A_SANDBOX: tuple[str, ...] = (
    "working_directory",
    "git_worktree",
    "argument_validator",
    "prompt",
    "copytree_isolated_folder",
    "review_worktree",
)

# Repository scripts, dependencies, and downloaded plugins are executable code.
EXECUTABLE_CODE_KINDS: tuple[str, ...] = (
    "repository_script",
    "dependency_package",
    "downloaded_plugin",
    "model_generated_code",
    "shell_command",
    "python_subprocess",
)


def classify_executable(kind: str) -> dict[str, Any]:
    is_exec = kind in EXECUTABLE_CODE_KINDS or kind.endswith("_plugin") or kind.endswith("_script")
    return {
        "kind": kind,
        "treated_as_executable_code": is_exec,
        "note": (
            "Repository scripts, dependencies, and downloaded plugins are executable code "
            "and require boundary enforcement — not merely a narrower cwd."
            if is_exec
            else "Not classified as executable code for this policy."
        ),
    }


def not_sandbox_disclaimer() -> dict[str, Any]:
    return {
        "not_security_sandboxes": list(NOT_A_SANDBOX),
        "statement": (
            "A working directory, Git worktree, argument validator, or prompt is not a "
            "security sandbox."
        ),
    }


def mode_for_isolation(isolation: dict[str, Any]) -> dict[str, Any]:
    """
    If reliable OS isolation is unavailable, restrict to trusted local workloads
    and disable unattended untrusted execution.
    """
    reliable = bool(isolation.get("reliable_process_isolation"))
    if reliable:
        return {
            "trust_default": "trusted_local",
            "unattended_untrusted_execution": "allowed_only_inside_verified_job_object",
            "untrusted_network": "denied_by_policy",
            "isolation_reliable": True,
        }
    return {
        "trust_default": "trusted_local",
        "unattended_untrusted_execution": "disabled",
        "untrusted_network": "denied",
        "isolation_reliable": False,
        "reason": (
            "Reliable OS isolation unavailable on this host; system restricted to trusted "
            "local workloads; unattended untrusted execution disabled."
        ),
    }


def may_execute_untrusted(
    *,
    trust: TrustLevel,
    isolation: dict[str, Any],
    unattended: bool,
) -> dict[str, Any]:
    mode = mode_for_isolation(isolation)
    if trust == "trusted_local":
        return {"allowed": True, "reason": "trusted_local_workload", "mode": mode}
    if not isolation.get("reliable_process_isolation"):
        return {
            "allowed": False,
            "reason": "untrusted_blocked_no_reliable_isolation",
            "mode": mode,
        }
    if unattended and mode.get("unattended_untrusted_execution") == "disabled":
        return {
            "allowed": False,
            "reason": "unattended_untrusted_disabled",
            "mode": mode,
        }
    if unattended and mode.get("unattended_untrusted_execution") != "allowed_only_inside_verified_job_object":
        return {"allowed": False, "reason": "unattended_untrusted_disabled", "mode": mode}
    return {
        "allowed": True,
        "reason": "untrusted_inside_verified_job_object",
        "mode": mode,
        "requires_job_object": True,
    }
