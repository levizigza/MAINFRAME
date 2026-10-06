"""Boundary enforcement report — enforced vs assumptions."""

from __future__ import annotations

from typing import Any

from mainframe.boundaries.isolation import probe_isolation
from mainframe.boundaries.policy import (
    EXECUTABLE_CODE_KINDS,
    classify_executable,
    mode_for_isolation,
    not_sandbox_disclaimer,
)


def boundary_report(*, verify: bool = True) -> dict[str, Any]:
    isolation = probe_isolation(verify_enforcement=verify)
    mode = mode_for_isolation(isolation)

    enforced = [
        {
            "boundary": "filesystem_paths",
            "enforced": True,
            "layer": "mainframe_path_resolution",
            "covers": ["path_traversal", "symlink_escape"],
            "note": "Final resolved path must remain under allowed root.",
        },
        {
            "boundary": "environment_variables",
            "enforced": True,
            "layer": "worker_env_scrub",
            "covers": ["model_credentials_excluded_from_workers"],
        },
        {
            "boundary": "network_access",
            "enforced": True,
            "layer": "policy",
            "covers": ["untrusted_and_non_loopback_denied"],
            "os_network_isolation": bool(isolation.get("os_network_isolation")),
        },
        {
            "boundary": "elapsed_time",
            "enforced": True,
            "layer": "wall_clock_timeout_plus_job_terminate",
        },
        {
            "boundary": "process_spawning",
            "enforced": True,
            "layer": "spawn_bounded",
            "covers": ["shell_false", "permit_gate", "job_object_when_available"],
        },
    ]

    if isolation.get("reliable_process_isolation"):
        enforced.extend(
            [
                {
                    "boundary": "cpu",
                    "enforced": True,
                    "layer": "windows_job_object_user_time_limit",
                    "verified_on_this_host": isolation.get("verified_on_this_host"),
                },
                {
                    "boundary": "memory",
                    "enforced": True,
                    "layer": "windows_job_object_memory_limit",
                    "verified_on_this_host": isolation.get("verified_on_this_host"),
                },
            ]
        )
    else:
        enforced.append(
            {
                "boundary": "cpu_memory_via_os_job",
                "enforced": False,
                "reason": "Job Object unreliable/unavailable — unattended untrusted disabled",
            }
        )

    assumptions = [
        {
            "boundary": "os_network_isolation",
            "assumption": True,
            "detail": (
                "No verified zero-fee AppContainer/firewall jail in MAINFRAME; "
                "network is policy-denied, not OS-quarantined."
            ),
        },
        {
            "boundary": "os_filesystem_jail",
            "assumption": True,
            "detail": (
                "Job Object is not a filesystem jail; path policy enforces root confinement."
            ),
        },
        {
            "boundary": "not_sandboxes",
            "assumption": False,
            "detail": not_sandbox_disclaimer()["statement"],
            "items": not_sandbox_disclaimer()["not_security_sandboxes"],
        },
    ]
    assumptions.extend(
        {"boundary": "isolation_note", "assumption": True, "detail": a}
        for a in (isolation.get("assumptions") or [])
    )

    return {
        "isolation": isolation,
        "mode": mode,
        "executable_code_kinds": list(EXECUTABLE_CODE_KINDS),
        "examples": {
            "repository_script": classify_executable("repository_script"),
            "downloaded_plugin": classify_executable("downloaded_plugin"),
            "dependency_package": classify_executable("dependency_package"),
        },
        "enforced": enforced,
        "assumptions": assumptions,
        "credentials_outside_worker_environments": True,
    }
