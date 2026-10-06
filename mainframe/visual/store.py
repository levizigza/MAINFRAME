"""Workflow document store — owned by FreeForge; visual UI is disposable."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from mainframe.config import STATE_DIR, ensure_state

SAFE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_\-]{0,63}$")


def workflows_root(root: Path | None = None) -> Path:
    ensure_state()
    base = root or (STATE_DIR / "workflows")
    base.mkdir(parents=True, exist_ok=True)
    return base


def list_workflows(root: Path | None = None) -> list[dict[str, Any]]:
    base = workflows_root(root)
    out = []
    for p in sorted(base.glob("*/workflow.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        out.append(
            {
                "id": data.get("id") or p.parent.name,
                "path": str(p),
                "permissions": data.get("permissions") or [],
                "step_count": len(data.get("steps") or []),
            }
        )
    return out


def workflow_dir(workflow_id: str, root: Path | None = None) -> Path:
    if not SAFE_ID.match(workflow_id):
        raise ValueError("invalid_workflow_id")
    return workflows_root(root) / workflow_id


def save_workflow(wf: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    wid = str(wf.get("id") or "")
    if not SAFE_ID.match(wid):
        return {"ok": False, "error": "invalid_workflow_id"}
    # Strip any inline secrets before persist
    cleaned = strip_inline_secrets(wf)
    dest = workflow_dir(wid, root)
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / "workflow.json"
    path.write_text(json.dumps(cleaned, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "id": wid, "path": str(path), "secrets_inline": False}


def load_saved(workflow_id: str, root: Path | None = None) -> dict[str, Any]:
    path = workflow_dir(workflow_id, root) / "workflow.json"
    if not path.is_file():
        return {"ok": False, "error": "not_found"}
    return {"ok": True, "workflow": json.loads(path.read_text(encoding="utf-8")), "path": str(path)}


def strip_inline_secrets(wf: dict[str, Any]) -> dict[str, Any]:
    """Ensure secrets are references only — never embed credential material in flows."""
    out = json.loads(json.dumps(wf))  # deep copy via JSON
    banned_keys = {"password", "api_key", "apikey", "token", "secret", "credentials"}

    def scrub(obj: Any) -> Any:
        if isinstance(obj, dict):
            cleaned = {}
            for k, v in obj.items():
                lk = str(k).lower()
                if lk in banned_keys or lk.endswith("_secret") or lk.endswith("_password"):
                    if isinstance(v, str) and v.startswith("secret_ref:"):
                        cleaned[k] = v  # allow explicit refs
                    else:
                        cleaned[k] = "secret_ref:REDACTED_USE_FACILITY"
                else:
                    cleaned[k] = scrub(v)
            return cleaned
        if isinstance(obj, list):
            return [scrub(x) for x in obj]
        return obj

    return scrub(out)
