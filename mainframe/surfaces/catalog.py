"""Product surface definitions — web (sites/webapps) vs application (desktop/mobile stores)."""

from __future__ import annotations

from typing import Any

SURFACE_WEB = "web"
SURFACE_APPLICATION = "application"

WEB_FOCUS = {
    "id": SURFACE_WEB,
    "title": "Web surface",
    "optimized_for": [
        "websites",
        "web applications",
        "browser maintenance",
        "HTTP connectors",
        "static/loopback web UI",
        "Playwright DOM evidence",
    ],
    "primary_workloads": [
        "website_maintenance",
        "document_reporting_for_web_content",
        "connectors_readonly",
        "browser_tools",
        "visual_bridge_optional",
    ],
    "deliverables": [
        "static site under dist/web/ (GitHub Pages–ready, optional)",
        "loopback dashboard HTML tuned for browser use",
        "web workflow fixtures and site-holdout evals",
    ],
    "not_for": [
        "App Store / Play Store binary submission",
        "native iOS/Android packaging (see application surface)",
    ],
    "hosted_pages_required": False,
    "note": "Local `python -m mainframe surfaces build-web` produces artifacts; Pages is optional.",
}

APPLICATION_FOCUS = {
    "id": SURFACE_APPLICATION,
    "title": "Application surface",
    "optimized_for": [
        "desktop Windows apps",
        "desktop packaging metadata",
        "mobile app-store oriented projects (iOS/Android) as target markets",
        "local automation against app codebases",
        "editor extension + FreeForge CLI",
    ],
    "primary_workloads": [
        "repository_repair",
        "codingbench_holdout",
        "editor_bridge",
        "release_package_desktop",
        "project_isolation",
    ],
    "deliverables": [
        "desktop release tree under dist/application/",
        "store-readiness checklist (not a signed store upload)",
        "VS Code/FreeForge editor extension path",
    ],
    "not_for": [
        "Claiming App Store / Play distribution without separate store accounts",
        "Replacing web-site maintenance workflows (use web surface)",
    ],
    "app_store_upload_required": False,
    "code_signing_service_required": False,
    "note": (
        "Application surface prepares local desktop packages and store-oriented checklists. "
        "Actual iOS/Android store submission needs developer accounts outside MAINFRAME's free contract "
        "and is labeled DOCUMENTED_NOT_TESTED until the user runs those steps."
    ),
}


def surface_catalog() -> dict[str, Any]:
    return {
        "objective": "correct_completed_work_per_available_resource",
        "surfaces": {
            SURFACE_WEB: WEB_FOCUS,
            SURFACE_APPLICATION: APPLICATION_FOCUS,
        },
        "shared_core": [
            "deterministic_offline mode",
            "eligibility / cost_gate",
            "quota ledger",
            "workflows + receipts",
            "recommend config",
        ],
        "non_requirements": {
            "hosted_ci": False,
            "github_pages": False,
            "app_store_account": False,
            "code_signing_saas": False,
        },
    }
