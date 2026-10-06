"""Acceptance for minimal local release packaging."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mainframe.config import ROOT
from mainframe.release.package import DIST_ROOT
from mainframe.release.suite import REPORT_JSON, REPORT_MD, run_release_package


def run_release_accept() -> dict[str, Any]:
    payload = run_release_package(register_startup=True)
    acc = payload.get("acceptance") or {}
    checks: list[dict[str, Any]] = []

    checks.append(
        {
            "id": "reports_published",
            "ok": REPORT_MD.is_file() and REPORT_JSON.is_file(),
            "detail": {
                "md": str(REPORT_MD.relative_to(ROOT)).replace("\\", "/"),
                "json": str(REPORT_JSON.relative_to(ROOT)).replace("\\", "/"),
            },
        }
    )
    checks.append(
        {
            "id": "clean_install_smoke",
            "ok": bool(acc.get("clean_install_smoke")),
            "detail": payload.get("clean_install_smoke"),
        }
    )
    checks.append(
        {
            "id": "backup_restore",
            "ok": bool(acc.get("backup_restore")),
            "detail": {
                "archive": ((payload.get("backup_restore") or {}).get("backup") or {}).get(
                    "archive"
                ),
                "restored_count": (
                    (payload.get("backup_restore") or {}).get("restore") or {}
                ).get("restored_count"),
            },
        }
    )
    checks.append(
        {
            "id": "migrate_workflow_and_db",
            "ok": bool(acc.get("migrate_workflow_and_db")),
            "detail": payload.get("migrate"),
        }
    )
    checks.append(
        {
            "id": "upgrade_check_and_pins",
            "ok": bool(acc.get("upgrade_check") and acc.get("pins_and_licenses_present")),
            "detail": {
                "upgrade": (payload.get("upgrade") or {}).get("issues"),
                "license": (payload.get("pins") or {}).get("license_spdx"),
            },
        }
    )
    checks.append(
        {
            "id": "startup_explicit_removable",
            "ok": bool(acc.get("startup_explicit_removable")),
            "detail": payload.get("startup"),
        }
    )
    checks.append(
        {
            "id": "no_hosted_requirements",
            "ok": bool(
                acc.get("no_hosted_ci_signing_cloud_hosting_required")
                and acc.get("obsolete_installers_not_required")
                and acc.get("credentials_not_required_for_core")
            ),
            "detail": {
                "documented_not_tested": payload.get("documented_not_tested"),
                "non_requirements": (payload.get("package") or {})
                .get("target", {})
                .get("obsolete_installer_commands_refused"),
            },
        }
    )

    dest = (payload.get("package") or {}).get("dest")
    checks.append(
        {
            "id": "package_tree_local",
            "ok": bool(dest and Path(dest).is_dir() and DIST_ROOT.is_dir()),
            "detail": {"dest": dest, "hosted_upload": False},
        }
    )

    passed = sum(1 for c in checks if c.get("ok"))
    failed = len(checks) - passed
    return {
        "ok": failed == 0,
        "passed": passed,
        "failed": failed,
        "checks": checks,
        "report_md": payload.get("report_md"),
        "report_json": payload.get("report_json"),
        "release_version": payload.get("release_version"),
        "documented_not_tested": payload.get("documented_not_tested"),
    }
