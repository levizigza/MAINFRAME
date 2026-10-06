"""Acceptance for dual product surfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mainframe.config import ROOT
from mainframe.surfaces.suite import REPORT_JSON, REPORT_MD, run_surfaces


def run_surfaces_accept() -> dict[str, Any]:
    payload = run_surfaces()
    web = payload.get("web") or {}
    app = payload.get("application") or {}
    checks: list[dict[str, Any]] = []

    checks.append(
        {
            "id": "reports_published",
            "ok": REPORT_MD.is_file() and REPORT_JSON.is_file(),
            "detail": {"md": "docs/SURFACES.md", "json": "docs/SURFACES.json"},
        }
    )
    checks.append(
        {
            "id": "web_index_built",
            "ok": bool(web.get("ok")) and Path(web.get("index") or "").is_file(),
            "detail": web.get("dest"),
        }
    )
    checks.append(
        {
            "id": "web_optimized_for_sites",
            "ok": "websites" in ((web.get("manifest") or {}).get("focus") or {}).get(
                "optimized_for", []
            ),
            "detail": ((web.get("manifest") or {}).get("focus") or {}).get("optimized_for"),
        }
    )
    checks.append(
        {
            "id": "application_desktop_built",
            "ok": bool(app.get("ok")) and Path(app.get("dest") or "").is_dir(),
            "detail": app.get("dest"),
        }
    )
    checks.append(
        {
            "id": "store_uploads_not_required",
            "ok": app.get("app_store_upload_required") is False
            and any(
                c.get("id") == "ios_app_store" and c.get("status") == "documented_not_tested"
                for c in (app.get("store_checklist") or [])
            ),
            "detail": app.get("documented_not_tested"),
        }
    )
    checks.append(
        {
            "id": "hosted_ci_not_required",
            "ok": (payload.get("github_actions") or {}).get("required") is False,
            "detail": payload.get("github_actions"),
        }
    )
    wf = ROOT / ".github" / "workflows" / "surfaces.yml"
    checks.append(
        {
            "id": "optional_actions_workflow_present",
            "ok": wf.is_file(),
            "detail": str(wf.relative_to(ROOT)).replace("\\", "/"),
        }
    )

    passed = sum(1 for c in checks if c.get("ok"))
    failed = len(checks) - passed
    return {
        "ok": failed == 0,
        "passed": passed,
        "failed": failed,
        "checks": checks,
        "actions_url": "https://github.com/levizigza/MAINFRAME/actions",
        "pages_url_optional": "https://levizigza.github.io/MAINFRAME/",
        "report_md": payload.get("report_md"),
        "report_json": payload.get("report_json"),
    }
