"""Build a minimal local release tree (no cloud upload, no code-signing service)."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.config import ROOT
from mainframe.release.pins import RELEASE_VERSION, write_pinned_json
from mainframe.release.target import measure_target

DIST_ROOT = ROOT / "dist" / "release"
INCLUDE_DIRS = (
    "mainframe",
    "docs/eval/workflows/fixtures/input_to_report",
    "docs/eval/connectors",
    "docs/freeforge/public-apis-snapshot",
    "docs/freeforge/PINS.json",
    "docs/NOTICES.md",
    "docs/DOCTOR.md",
    "docs/DEPENDENCIES.md",
    "docs/COST_AUDIT.md",
    "freeforge-cli/package.json",
    "freeforge-cli/package-lock.json",
    "freeforge-cli/tsconfig.json",
    "freeforge-cli/src",
    "LICENSE",
    "README.md",
    ".cursor/rules/mainframe-core.mdc",
)

EXCLUDE_NAME_FRAGMENTS = (
    "__pycache__",
    ".pyc",
    "node_modules",
    ".mainframe",
    ".git",
)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _should_skip(path: Path) -> bool:
    parts = path.parts
    text = str(path)
    for frag in EXCLUDE_NAME_FRAGMENTS:
        if frag in parts or text.endswith(frag):
            return True
    return False


def _copy_path(src: Path, dest_root: Path) -> list[str]:
    copied: list[str] = []
    if not src.exists():
        return copied
    rel = src.relative_to(ROOT)
    dest = dest_root / rel
    if src.is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        copied.append(str(rel).replace("\\", "/"))
        return copied
    for path in src.rglob("*"):
        if path.is_dir() or _should_skip(path):
            continue
        r = path.relative_to(ROOT)
        d = dest_root / r
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, d)
        copied.append(str(r).replace("\\", "/"))
    return copied


def _write_setup_md(dest: Path, target: dict[str, Any]) -> None:
    py = target["python"]
    nt = target["os"]["nt_version"]
    lines = [
        "# MAINFRAME local setup (verified on this host)",
        "",
        f"Release: `{RELEASE_VERSION}`",
        f"Generated: `{_utc()}`",
        "",
        "## Target platform (measured)",
        "",
        f"- `platform`: `{target['os']['platform_string']}`",
        f"- Registry ProductName: `{nt.get('product_name')}`",
        f"- DisplayVersion: `{nt.get('display_version')}` / build `{nt.get('current_build')}`",
        f"- Python: `{py['version']}` at `{py['executable']}` (3.11+ required: `{py['meets_3_11']}`)",
        f"- Node present: `{target['tools']['node'].get('present')}` "
        f"version `{target['tools']['node'].get('version')}`",
        f"- Git present: `{target['tools']['git'].get('present')}`",
        "",
        "## Install (core)",
        "",
        "1. Copy or extract this release folder to a writable local path.",
        "2. Open PowerShell in that folder.",
        "3. Run (uses **already-installed** Python — no pip, no choco/winget invented here):",
        "",
        "```powershell",
        "python -m mainframe status",
        "python -m mainframe doctor",
        "python -m mainframe run echo --param message=hello",
        "```",
        "",
        "No `pip install` is required for core. No Docker Desktop. No paid account.",
        "",
        "## Optional FreeForge TypeScript CLI",
        "",
        "Only if you want the Node CLI (not required for core):",
        "",
        "```powershell",
        "cd freeforge-cli",
        "npm ci",
        "npm run accept",
        "```",
        "",
        "Pinned versions are in `PINNED_DEPENDENCIES.json` and `freeforge-cli/package.json`.",
        "",
        "## Doctor / credentials / fixtures / backups",
        "",
        "```powershell",
        "python -m mainframe doctor",
        "python -m mainframe release credentials-status",
            "python -m mainframe connectors call --connector dog_ceo --op list_breeds --mode fixture",
        "python -m mainframe release backup",
        "python -m mainframe release restore --archive <path-from-backup>",
        "python -m mainframe release migrate-workflow --fixture input_to_report",
        "python -m mainframe release upgrade-check",
        "```",
        "",
        "## Startup scheduling (explicit, removable)",
        "",
        "Install does **not** register logon/startup tasks. To opt in (local removable job; "
        "OS Task Scheduler ONLOGON attempted when permitted):",
        "",
        "```powershell",
        "python -m mainframe release startup-register --confirm",
        "python -m mainframe release startup-status",
        "python -m mainframe release startup-remove",
        "```",
        "",
        "## What is NOT required",
        "",
        "- Hosted CI, code-signing services, cloud object storage, public hosting",
        "- Paid accounts, trials, promotional credits",
        "- Obsolete installer commands (refused below)",
        "",
        "## Obsolete installer commands (not documented as required)",
        "",
    ]
    for row in target["obsolete_installer_commands_refused"]:
        lines.append(f"- `{row['command']}` — {row['reason']}")
    lines.extend(
        [
            "",
            "## Optional platform limitations",
            "",
            "- Sleep/hibernate suspends local schedules.",
            "- Application policy cannot jail arbitrary networked processes; "
            "non-loopback live connectors stay disabled without OS network isolation.",
            "- OpenClaw Gateway is optional and was "
            + (
                "**not present** on the packaging host — Gateway setup steps are "
                "**DOCUMENTED_NOT_TESTED** here."
                if target["optional_not_present"]["openclaw"]
                else "present on this host."
            ),
            "- Docker Desktop is not required "
            + (
                "and was **not present** (DOCUMENTED_NOT_TESTED if you choose to use it)."
                if target["optional_not_present"]["docker"]
                else "."
            ),
            "",
            "## Uninstall",
            "",
            "See `UNINSTALL.md` in this folder, or:",
            "",
            "```powershell",
            "python -m mainframe release uninstall --confirm",
            "```",
            "",
            "## Physical resources (not software fees)",
            "",
            "Electricity, local CPU/GPU, disk, RAM, and optional download bandwidth remain user-borne.",
            "",
        ]
    )
    dest.write_text("\n".join(lines), encoding="utf-8")


def _write_uninstall_md(dest: Path) -> None:
    dest.write_text(
        "\n".join(
            [
                "# Uninstall MAINFRAME (local)",
                "",
                "1. Remove any explicit startup task:",
                "   `python -m mainframe release startup-remove`",
                "2. Optional: delete local state `.mainframe/` (preserves nothing — back up first).",
                "3. Delete the release/extract folder (or the git working tree if that is how you installed).",
                "4. No Windows service, no global pip package, no cloud tenant to cancel.",
                "",
                "Hosted CI / code-signing / cloud storage were never required — nothing to tear down there.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def build_release_tree(dest: Path | None = None) -> dict[str, Any]:
    target = measure_target()
    out_dir = dest or (DIST_ROOT / f"mainframe-{RELEASE_VERSION}")
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    missing: list[str] = []
    for item in INCLUDE_DIRS:
        src = ROOT / item
        if not src.exists():
            missing.append(item)
            continue
        copied.extend(_copy_path(src, out_dir))

    write_pinned_json(out_dir / "PINNED_DEPENDENCIES.json")
    _write_setup_md(out_dir / "SETUP.md", target)
    _write_uninstall_md(out_dir / "UNINSTALL.md")

    manifest = {
        "release_version": RELEASE_VERSION,
        "generated_at": _utc(),
        "root": str(out_dir),
        "file_count": len(copied),
        "missing_optional_paths": missing,
        "target": target,
        "non_requirements": {
            "hosted_ci": False,
            "code_signing_service": False,
            "cloud_storage": False,
            "public_hosting": False,
        },
    }
    (out_dir / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return {
        "ok": True,
        "dest": str(out_dir),
        "file_count": len(copied),
        "missing": missing,
        "target": target,
        "manifest": "MANIFEST.json",
    }
