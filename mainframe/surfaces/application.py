"""Application surface — desktop package + store-oriented checklist (no forced signing)."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe import __version__
from mainframe.config import ROOT
from mainframe.release.package import build_release_tree
from mainframe.surfaces.catalog import APPLICATION_FOCUS, SURFACE_APPLICATION

APP_DIST = ROOT / "dist" / "application"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


STORE_CHECKLIST = [
    {
        "id": "desktop_windows_local_package",
        "status": "supported",
        "note": "Built via release package / surfaces build-app — local folder, no store account",
    },
    {
        "id": "macos_app_bundle",
        "status": "documented_not_tested",
        "note": "Target market listed; packaging not executed on this Windows host",
    },
    {
        "id": "ios_app_store",
        "status": "documented_not_tested",
        "note": "Requires Apple Developer Program — outside MAINFRAME free contract; not uploaded",
    },
    {
        "id": "android_play_store",
        "status": "documented_not_tested",
        "note": "Requires Google Play Console — outside free contract; not uploaded",
    },
    {
        "id": "microsoft_store",
        "status": "documented_not_tested",
        "note": "Optional later; local Win32/folder distribution is the verified path",
    },
    {
        "id": "code_signing_service",
        "status": "not_required",
        "note": "No code-signing SaaS required for local application surface",
    },
]


def build_application_surface(dest: Path | None = None) -> dict[str, Any]:
    out = dest or APP_DIST
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    # Reuse minimal release tree as desktop application payload
    packaged = build_release_tree(dest=out / f"mainframe-desktop-{__version__}")

    readme = f"""# MAINFRAME application surface

Version: `{__version__}`
Generated: `{_utc()}`

## What this is

Desktop-first FreeForge packaging for local Windows use, plus a **store-readiness checklist**
for iOS, Android, and other markets. This does **not** upload to any app store.

## Optimized for

{chr(10).join('- ' + x for x in APPLICATION_FOCUS['optimized_for'])}

## Run locally (Windows — verified path)

```powershell
cd mainframe-desktop-{__version__}
python -m mainframe status
python -m mainframe doctor
python -m mainframe recommend accept
```

## Store markets

See `STORE_CHECKLIST.json`. Items marked `documented_not_tested` need separate developer
accounts and are not part of MAINFRAME's zero-fee core.

## Not required

- Hosted CI (optional GitHub Actions may mirror these checks)
- Code-signing SaaS
- App Store / Play Console accounts
"""
    (out / "README.md").write_text(readme, encoding="utf-8")
    (out / "STORE_CHECKLIST.json").write_text(
        json.dumps(
            {
                "surface": SURFACE_APPLICATION,
                "generated_at": _utc(),
                "checklist": STORE_CHECKLIST,
                "focus": APPLICATION_FOCUS,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    # Editor extension pointer (desktop IDE)
    ext = ROOT / "extensions" / "freeforge-editor"
    if ext.is_dir():
        tip = out / "editor"
        tip.mkdir(exist_ok=True)
        (tip / "README.md").write_text(
            "VS Code extension sources live at `extensions/freeforge-editor` in the repo.\n"
            "Package with vsce only if you already have tooling — not required for core.\n",
            encoding="utf-8",
        )

    manifest = {
        "surface": SURFACE_APPLICATION,
        "version": __version__,
        "generated_at": _utc(),
        "desktop_package": packaged.get("dest"),
        "store_checklist": "STORE_CHECKLIST.json",
        "app_store_upload_performed": False,
        "code_signing_used": False,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    return {
        "ok": bool(packaged.get("ok")),
        "surface": SURFACE_APPLICATION,
        "dest": str(out),
        "desktop_package": packaged,
        "store_checklist": STORE_CHECKLIST,
        "app_store_upload_required": False,
        "documented_not_tested": [
            c["id"] for c in STORE_CHECKLIST if c["status"] == "documented_not_tested"
        ],
    }
