"""Upgrade compatibility check between installed tree and release pins."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mainframe import __version__
from mainframe.config import ROOT, STATE_DIR, ensure_state
from mainframe.release.pins import RELEASE_VERSION, build_pin_manifest
from mainframe.workflows.schema import FORMAT_VERSION


COMPAT_MIN_PACKAGE = "0.1.0"
WORKFLOW_FORMAT_SUPPORTED = {FORMAT_VERSION, "1.0"}


def upgrade_check(*, from_version: str | None = None) -> dict[str, Any]:
    ensure_state()
    pins = build_pin_manifest()
    current = from_version or __version__
    pkg_json = ROOT / "freeforge-cli" / "package.json"
    lock_ok = (ROOT / "freeforge-cli" / "package-lock.json").is_file()
    deps_match = pins.get("freeforge_cli_package_json_matches_pins")

    # State schema probes
    state_files = {
        "config.json": (STATE_DIR / "config.json").is_file(),
        "freeforge_schedule.sqlite": (STATE_DIR / "freeforge_schedule.sqlite").is_file(),
        "freeforge_workflow_receipts.sqlite": (
            STATE_DIR / "freeforge_workflow_receipts.sqlite"
        ).is_file(),
    }

    issues: list[str] = []
    if not deps_match:
        issues.append("freeforge-cli package.json dependencies drifted from release pins")
    if not lock_ok:
        issues.append("freeforge-cli/package-lock.json missing (optional CLI pin freeze)")

    compatible = len(issues) == 0
    return {
        "ok": compatible,
        "compatible": compatible,
        "from_version": current,
        "to_release_version": RELEASE_VERSION,
        "package_version": __version__,
        "workflow_format_supported": sorted(WORKFLOW_FORMAT_SUPPORTED),
        "compat_floor": COMPAT_MIN_PACKAGE,
        "state_files_present": state_files,
        "freeforge_cli_pins_match": deps_match,
        "package_lock_present": lock_ok,
        "issues": issues,
        "breaking_changes": [],
        "migration_required": {
            "workflows": f"format_version must be in {sorted(WORKFLOW_FORMAT_SUPPORTED)}",
            "sqlite": "WorkflowReceiptStore applies additive migrations on open",
        },
        "hosted_ci_required": False,
        "notes": (
            "Core Python path remains stdlib-only across upgrades. "
            "Optional Node CLI uses pinned package.json + lockfile when present."
        ),
        "pins_summary": {
            "release_version": pins.get("release_version"),
            "license_spdx": pins.get("license_spdx"),
            "non_requirements": pins.get("non_requirements"),
        },
        "package_json_path": str(pkg_json) if pkg_json.is_file() else None,
    }
