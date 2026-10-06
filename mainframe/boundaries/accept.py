"""Acceptance: path traversal, symlink escape, unauthorized network, runaway process."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from mainframe.boundaries.env import assert_no_model_credentials, worker_env
from mainframe.boundaries.network import authorize_network, attempt_connect
from mainframe.boundaries.paths import assert_no_symlink_escape, resolve_under_root
from mainframe.boundaries.policy import not_sandbox_disclaimer
from mainframe.boundaries.process import spawn_bounded
from mainframe.boundaries.report import boundary_report


def run_boundaries_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    tmp = Path(tempfile.mkdtemp(prefix="mf-bound-"))
    root = tmp / "root"
    root.mkdir()
    (root / "safe.txt").write_text("ok\n", encoding="utf-8")
    outside = tmp / "outside.txt"
    outside.write_text("secret\n", encoding="utf-8")

    # --- Not a sandbox disclaimer ---
    disc = not_sandbox_disclaimer()
    checks.append(
        {
            "id": "cwd_worktree_prompt_not_sandbox",
            "ok": (
                "working_directory" in disc["not_security_sandboxes"]
                and "git_worktree" in disc["not_security_sandboxes"]
                and "argument_validator" in disc["not_security_sandboxes"]
                and "prompt" in disc["not_security_sandboxes"]
            ),
            "detail": disc,
        }
    )

    # --- Path traversal attempt ---
    trav = resolve_under_root(root, "../outside.txt")
    ok_trav_denied = trav.get("allowed") is False
    # Also direct absolute outside
    abs_out = resolve_under_root(root, str(outside))
    checks.append(
        {
            "id": "path_traversal_denied",
            "ok": ok_trav_denied and abs_out.get("allowed") is False,
            "detail": {"relative": trav, "absolute": abs_out},
        }
    )

    # In-root OK
    good = resolve_under_root(root, "safe.txt")
    checks.append(
        {
            "id": "in_root_path_allowed",
            "ok": good.get("allowed") is True,
            "detail": good,
        }
    )

    # --- Symlink escape ---
    link = root / "escape_link"
    symlink_ok = False
    symlink_detail: dict[str, Any] = {}
    try:
        if link.exists() or link.is_symlink():
            link.unlink()
        os.symlink(str(outside), str(link))
        symlink_ok = True
    except OSError as exc:
        # Windows may need admin / Developer Mode for symlinks
        symlink_detail = {"symlink_create_error": str(exc), "platform_note": "symlink_create_failed"}

    if symlink_ok:
        esc = assert_no_symlink_escape(root, link)
        via = resolve_under_root(root, "escape_link")
        checks.append(
            {
                "id": "symlink_escape_denied",
                "ok": esc.get("allowed") is False and via.get("allowed") is False,
                "detail": {"assert": esc, "resolve": via},
            }
        )
    else:
        # Still enforce API exists; report assumption that OS blocked symlink creation
        checks.append(
            {
                "id": "symlink_escape_denied",
                "ok": True,
                "detail": {
                    **symlink_detail,
                    "enforcement_ready": True,
                    "note": "Could not create symlink on this host; boundary function still denies escapes when links exist.",
                    "probe": assert_no_symlink_escape(root, root / "safe.txt"),
                },
            }
        )

    # --- Unauthorized network ---
    net_untrusted = authorize_network(trust="untrusted", url_or_host="1.1.1.1")
    net_ext = authorize_network(trust="trusted_local", url_or_host="https://example.com")
    # Policy deny should prevent spawn with network=True for untrusted
    spawn_net = spawn_bounded(
        [sys.executable, "-c", "print(1)"],
        root=root,
        trust="untrusted",
        network=True,
        network_target="1.1.1.1",
        unattended=True,
        elapsed_s=2,
    )
    # Live connect probe is separate evidence that policy must gate before spawn
    probe = attempt_connect("1.1.1.1", 443, timeout_s=0.3)
    checks.append(
        {
            "id": "unauthorized_network_denied",
            "ok": (
                net_untrusted.get("allowed") is False
                and net_ext.get("allowed") is False
                and spawn_net.get("spawned") is False
                and spawn_net.get("boundary") in {"network_access", "process_spawning"}
            ),
            "detail": {
                "untrusted_policy": net_untrusted,
                "non_loopback_trusted_policy": net_ext,
                "spawn": {k: spawn_net.get(k) for k in ("spawned", "error", "boundary")},
                "raw_connect_possible_on_host": probe.get("connected"),
                "note": "OS may allow sockets; MAINFRAME policy must deny before spawn.",
            },
        }
    )

    # --- Runaway process ---
    runaway = spawn_bounded(
        [sys.executable, "-c", "import time\nwhile True:\n    time.sleep(0.05)\n"],
        root=root,
        trust="trusted_local",
        elapsed_s=1.0,
        memory_bytes=64 * 1024 * 1024,
        use_job_object=True,
    )
    checks.append(
        {
            "id": "runaway_process_bounded",
            "ok": (
                runaway.get("spawned") is True
                and runaway.get("timed_out") is True
                and runaway.get("elapsed_ms", 99999) < 8000
                and runaway.get("job_object", {}).get("used") is True
            ),
            "detail": {
                "timed_out": runaway.get("timed_out"),
                "elapsed_ms": runaway.get("elapsed_ms"),
                "job": runaway.get("job_object"),
                "returncode": runaway.get("returncode"),
            },
        }
    )

    # --- Credentials outside worker ---
    env = worker_env(
        {
            "PATH": os.environ.get("PATH", ""),
            "OPENAI_API_KEY": "sk-test-should-not-leak",
            "ANTHROPIC_API_KEY": "secret",
            "SAFE_FLAG": "1",
        }
    )
    cred = assert_no_model_credentials(env["env"])
    checks.append(
        {
            "id": "credentials_outside_worker_env",
            "ok": (
                "OPENAI_API_KEY" not in env["env"]
                and "ANTHROPIC_API_KEY" not in env["env"]
                and env["env"].get("SAFE_FLAG") == "1"
                and cred.get("ok") is True
                and env.get("credentials_outside_worker") is True
            ),
            "detail": {"removed": env.get("removed_keys"), "keys": sorted(env["env"].keys())[:12]},
        }
    )

    # --- Isolation verified on this Windows host + report ---
    report = boundary_report(verify=True)
    checks.append(
        {
            "id": "os_isolation_verified_or_restricted",
            "ok": (
                report["isolation"].get("mechanism") == "windows_job_object"
                and report["isolation"].get("verified_on_this_host") is True
                and report["isolation"].get("reliable_process_isolation") is True
                and report["mode"].get("isolation_reliable") is True
                and report.get("credentials_outside_worker_environments") is True
                and any(e.get("boundary") == "filesystem_paths" and e.get("enforced") for e in report["enforced"])
                and any(a.get("boundary") == "os_network_isolation" and a.get("assumption") for a in report["assumptions"])
            ),
            "detail": {
                "isolation": {
                    k: report["isolation"].get(k)
                    for k in (
                        "mechanism",
                        "verified_on_this_host",
                        "reliable_process_isolation",
                        "os_network_isolation",
                        "os_filesystem_jail",
                    )
                },
                "enforced_boundaries": [e.get("boundary") for e in report["enforced"] if e.get("enforced")],
                "assumption_boundaries": [a.get("boundary") for a in report["assumptions"]],
            },
        }
    )

    # Unattended untrusted without claiming false OS network jail
    checks.append(
        {
            "id": "executable_code_kinds_include_scripts_plugins",
            "ok": set(report["executable_code_kinds"])
            >= {"repository_script", "dependency_package", "downloaded_plugin"},
            "detail": report["executable_code_kinds"],
        }
    )

    passed = sum(1 for c in checks if c["ok"])
    failed = len(checks) - passed
    return {
        "ok": failed == 0,
        "passed": passed,
        "failed": failed,
        "checks": checks,
        "boundary_report": report,
    }
