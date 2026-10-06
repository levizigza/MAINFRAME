"""Build both surfaces and publish docs/SURFACES.md."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from mainframe.config import ROOT, RUNS_DIR, ensure_state
from mainframe.surfaces.application import build_application_surface
from mainframe.surfaces.catalog import surface_catalog
from mainframe.surfaces.web import build_web_surface

REPORT_MD = ROOT / "docs" / "SURFACES.md"
REPORT_JSON = ROOT / "docs" / "SURFACES.json"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_surfaces() -> dict[str, Any]:
    ensure_state()
    catalog = surface_catalog()
    web = build_web_surface()
    app = build_application_surface()

    payload = {
        "ok": bool(web.get("ok") and app.get("ok")),
        "generated_at": _utc(),
        "catalog": catalog,
        "web": web,
        "application": app,
        "github_actions": {
            "required": False,
            "workflow": ".github/workflows/surfaces.yml",
            "actions_url_template": "https://github.com/levizigza/MAINFRAME/actions",
            "pages_url_optional": "https://levizigza.github.io/MAINFRAME/",
            "note": "Actions/Pages are optional mirrors; local builds remain authoritative.",
        },
        "report_md": "docs/SURFACES.md",
        "report_json": "docs/SURFACES.json",
    }

    lines = [
        "# MAINFRAME product surfaces",
        "",
        f"Generated: `{payload['generated_at']}`",
        "",
        "Two optimized surfaces share the same free-only FreeForge core:",
        "",
        "1. **Web** — websites and web applications (browser, connectors, site maintenance, static UI)",
        "2. **Application** — desktop local package + store-market checklist (iOS/Android/desktop markets)",
        "",
        "## Web",
        "",
        f"- Artifact: `{web.get('dest')}`",
        f"- Index: `{web.get('index')}`",
        "- Build: `python -m mainframe surfaces build-web`",
        "- GitHub Pages: optional (not required)",
        "",
        "## Application",
        "",
        f"- Artifact: `{app.get('dest')}`",
        "- Build: `python -m mainframe surfaces build-app`",
        "- App Store / Play uploads: **not performed**; see checklist for DOCUMENTED_NOT_TESTED items",
        "",
        "## Optional GitHub Actions",
        "",
        "- Workflow: `.github/workflows/surfaces.yml`",
        "- Runs: https://github.com/levizigza/MAINFRAME/actions",
        "- Optional Pages: https://levizigza.github.io/MAINFRAME/",
        "- Hosted CI is **not** required to use MAINFRAME locally.",
        "",
        "## Non-requirements",
        "",
        "- Hosted CI, code-signing SaaS, cloud storage, public hosting, paid accounts",
        "",
    ]
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    REPORT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (RUNS_DIR / f"surfaces-{stamp}.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    return payload
