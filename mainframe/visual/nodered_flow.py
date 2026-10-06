"""Optional Node-RED flow export — HTTP client only; no inject/cron for FreeForge triggers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mainframe.schedule.openclaw_payload import SCHEDULER_OWNER
from mainframe.visual.store import strip_inline_secrets


def export_nodered_flow(
    *,
    bridge_base_url: str = "http://127.0.0.1:8787",
    workflow_id: str,
    workflow: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Emit a minimal Node-RED flow that only POSTs to the FreeForge bridge.
    Intentionally omits inject-repeat / cron nodes so Node-RED cannot own the trigger.
    Secrets are stripped — only secret_ref placeholders allowed.
    """
    safe_wf = strip_inline_secrets(workflow) if workflow else None
    # Manual-only trigger comment + http request + debug
    nodes = [
        {
            "id": "ff_comment",
            "type": "comment",
            "name": "FreeForge owns schedule",
            "info": (
                f"Do not add inject-repeat or cron for this workflow. "
                f"scheduler_owner={SCHEDULER_OWNER}. Secrets stay outside this flow."
            ),
            "x": 160,
            "y": 80,
            "wires": [],
        },
        {
            "id": "ff_manual",
            "type": "inject",
            "name": "manual once (no repeat)",
            "props": [{"p": "payload"}],
            "repeat": "",
            "crontab": "",
            "once": False,
            "onceDelay": 0.1,
            "topic": "",
            "payload": json.dumps({"workflow_id": workflow_id}),
            "payloadType": "json",
            "x": 180,
            "y": 160,
            "wires": [["ff_http"]],
        },
        {
            "id": "ff_http",
            "type": "http request",
            "name": "invoke FreeForge bridge",
            "method": "POST",
            "ret": "obj",
            "paytoqs": "ignore",
            "url": f"{bridge_base_url.rstrip('/')}/api/run",
            "tls": "",
            "persist": False,
            "proxy": "",
            "authType": "",
            "x": 420,
            "y": 160,
            "wires": [["ff_debug"]],
        },
        {
            "id": "ff_debug",
            "type": "debug",
            "name": "execution results",
            "active": True,
            "tosidebar": True,
            "console": False,
            "tostatus": False,
            "complete": "payload",
            "targetType": "msg",
            "x": 680,
            "y": 160,
            "wires": [],
        },
    ]
    flow = {
        "label": f"FreeForge bridge → {workflow_id}",
        "nodes": nodes,
        "configs": [],
        "freeforge": {
            "scheduler_owner": SCHEDULER_OWNER,
            "dual_trigger_forbidden": True,
            "secrets_in_flow": False,
            "workflow_id": workflow_id,
            "workflow_snapshot_secret_scrubbed": safe_wf is not None,
        },
    }
    return {"ok": True, "flow": flow, "repeat_configured": False, "crontab_configured": False}


def write_nodered_flow(path: Path, **kwargs: Any) -> dict[str, Any]:
    exported = export_nodered_flow(**kwargs)
    Path(path).write_text(json.dumps(exported["flow"], indent=2) + "\n", encoding="utf-8")
    return {**exported, "path": str(path)}
