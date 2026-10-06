"""Node-RED evaluation for optional FreeForge visual use — licenses, costs, remotion.

Verified sources (2026-09-29):
  - https://github.com/node-red/node-red/blob/HEAD/LICENSE → Apache License 2.0
  - https://www.npmjs.com/package/node-red → license Apache-2.0; local npm package
"""

from __future__ import annotations

from typing import Any

# Core package facts — observed from upstream LICENSE + npm metadata (2026-09-29).
NODE_RED_CORE = {
    "package": "node-red",
    "license": "Apache-2.0",
    "copyright": "OpenJS Foundation and other contributors",
    "license_url": "https://github.com/node-red/node-red/blob/HEAD/LICENSE",
    "npm": "https://www.npmjs.com/package/node-red",
    "local_runtime_fee": False,
    "account_required_for_local": False,
    "hosted_service_required": False,
    "service_cost_local": "none — runs on user's Node.js; electricity/hardware are user prerequisites",
    "note": (
        "Apache-2.0 permits local use, modification, and redistribution subject to license terms. "
        "This is not legal advice."
    ),
}

# Built-in @node-red/* packages that ship with core (same Apache-2.0 line on npm).
CORE_BUNDLED = [
    {"name": "@node-red/editor-api", "license": "Apache-2.0", "service_cost": "none (local)"},
    {"name": "@node-red/nodes", "license": "Apache-2.0", "service_cost": "none (local)"},
    {"name": "@node-red/runtime", "license": "Apache-2.0", "service_cost": "none (local)"},
    {"name": "@node-red/util", "license": "Apache-2.0", "service_cost": "none (local)"},
]

# Additional nodes MAINFRAME would need if we embedded a second stack — we do NOT require these.
ADDITIONAL_NODES_NOT_REQUIRED = [
    {
        "name": "(none required)",
        "reason": "FreeForge bridge uses a simple local form; no npm palette nodes are required.",
        "license": "n/a",
        "service_cost": "n/a",
        "dependencies": [],
    }
]

# Nodes that must NOT be used as competing schedulers / secret stores.
DISALLOWED_FOR_FREEFORGE = [
    {
        "pattern": "inject with repeat / cron inside Node-RED for FreeForge workflows",
        "reason": "Would independently run the same trigger as OpenClaw/FreeForge schedule owner.",
    },
    {
        "pattern": "credentials embedded in exported flows",
        "reason": "Secrets must live outside exported flows (FreeForge secret facility).",
    },
    {
        "pattern": "paid cloud connector nodes (e.g. billed SaaS palettes)",
        "reason": "Violates MAINFRAME zero-required-fee posture; audit each palette before use.",
    },
]


def evaluate_nodered_optional() -> dict[str, Any]:
    """Honest evaluation: optional, removable; prefer simple local form for edit/invoke."""
    return {
        "ok": True,
        "verdict": "optional_not_required",
        "recommendation": (
            "Do not add Node-RED as a second automation stack for FreeForge edit/invoke. "
            "A simple local loopback form that calls FreeForge APIs is sufficient. "
            "If Node-RED is already installed, it may call the FreeForge bridge over HTTP only — "
            "never as an independent scheduler for the same trigger."
        ),
        "core": NODE_RED_CORE,
        "core_bundled_packages": CORE_BUNDLED,
        "additional_nodes": ADDITIONAL_NODES_NOT_REQUIRED,
        "disallowed_patterns": DISALLOWED_FOR_FREEFORGE,
        "scheduler_owner": "openclaw_gateway",
        "command_policy_owner": "freeforge",
        "effect_ledger_owner": "freeforge",
        "removable": True,
        "required_to_run_freeforge": False,
        "install_required": False,
        "paid_fallback": False,
    }
