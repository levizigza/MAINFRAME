"""Pinned dependencies, licenses, and source links for the minimal release."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mainframe import __version__
from mainframe.config import ROOT

RELEASE_VERSION = "0.1.48"

# Core Python path: stdlib only — no pip pins required to launch.
PYTHON_CORE = {
    "id": "python_stdlib_cli",
    "requirement": "Python 3.11+ already installed",
    "pip_install_required": False,
    "license": "PSF + MAINFRAME MIT",
    "source": "https://docs.python.org/3/library/",
    "note": "Core `python -m mainframe` launches with zero pip packages.",
}

FREEFORGE_CLI_PINS = {
    "id": "freeforge_cli_optional",
    "required_for_core": False,
    "engines": {"node": ">=22.12.0"},
    "dependencies": {
        "commander": "12.1.0",
        "sql.js": "1.12.0",
    },
    "devDependencies": {
        "@types/node": "22.10.2",
        "tsx": "4.19.2",
        "typescript": "5.7.2",
    },
    "licenses": {
        "commander": "MIT",
        "sql.js": "MIT",
        "typescript": "Apache-2.0",
        "tsx": "MIT",
        "@types/node": "MIT",
    },
    "source": "freeforge-cli/package.json",
    "openclaw_pin": {
        "ref": "v2026.9.6",
        "commit": "eb377ac59e6c9fd6c7705028034812becf00271b",
        "packageVersion": "2026.9.6",
        "license": "MIT",
        "source": "https://github.com/openclaw/openclaw",
        "required_for_core": False,
    },
}


def load_freeforge_pins_file() -> dict[str, Any]:
    path = ROOT / "docs" / "freeforge" / "PINS.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_pin_manifest() -> dict[str, Any]:
    pkg_json = ROOT / "freeforge-cli" / "package.json"
    observed: dict[str, Any] = {}
    if pkg_json.is_file():
        observed = json.loads(pkg_json.read_text(encoding="utf-8"))
    deps_match = observed.get("dependencies") == FREEFORGE_CLI_PINS["dependencies"]
    return {
        "release_version": RELEASE_VERSION,
        "package_version": __version__,
        "python_core": PYTHON_CORE,
        "freeforge_cli": FREEFORGE_CLI_PINS,
        "freeforge_cli_package_json_matches_pins": deps_match,
        "upstream_pins": load_freeforge_pins_file(),
        "notices_path": "docs/NOTICES.md",
        "license_path": "LICENSE",
        "license_spdx": "MIT",
        "non_requirements": {
            "hosted_ci": False,
            "code_signing_service": False,
            "cloud_storage": False,
            "public_hosting": False,
            "paid_account": False,
            "trial_or_promo": False,
        },
    }


def write_pinned_json(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = build_pin_manifest()
    dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return dest
