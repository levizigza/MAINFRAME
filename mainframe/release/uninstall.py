"""Clean uninstall path — local files only; removable startup; no cloud teardown."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from mainframe.config import ROOT, STATE_DIR
from mainframe.release.pins import RELEASE_VERSION
from mainframe.release.startup import startup_remove, startup_status


def uninstall_plan() -> dict[str, Any]:
    st = startup_status()
    return {
        "release_version": RELEASE_VERSION,
        "steps": [
            {
                "id": "remove_startup_task",
                "command": "python -m mainframe release startup-remove",
                "required": False,
                "present": st.get("registered"),
            },
            {
                "id": "optional_delete_state",
                "path": str(STATE_DIR),
                "note": "Back up first; contains user notes and local DBs",
                "required": False,
            },
            {
                "id": "delete_install_tree",
                "path": str(ROOT),
                "note": "Delete the folder you extracted or cloned",
                "required": True,
            },
        ],
        "not_applicable": [
            "cancel_cloud_subscription",
            "revoke_hosted_ci",
            "remove_code_signing_cert_service",
            "empty_cloud_object_storage",
            "unpublish_public_hosting",
        ],
        "global_pip_package": False,
        "windows_service": False,
    }


def run_uninstall(
    *,
    confirm: bool,
    delete_state: bool = False,
    delete_dist: bool = False,
) -> dict[str, Any]:
    if not confirm:
        return {
            "ok": False,
            "error": "confirm_required",
            "plan": uninstall_plan(),
            "hint": "Pass --confirm. Destructive deletes need an explicit flag.",
        }
    startup = startup_remove()
    actions: list[dict[str, Any]] = [{"id": "startup_remove", **startup}]

    if delete_state and STATE_DIR.is_dir():
        shutil.rmtree(STATE_DIR)
        actions.append({"id": "deleted_state", "path": str(STATE_DIR), "ok": True})
    else:
        actions.append(
            {
                "id": "state_preserved",
                "path": str(STATE_DIR),
                "ok": True,
                "note": "Pass --delete-state to remove .mainframe/",
            }
        )

    dist = ROOT / "dist" / "release"
    if delete_dist and dist.is_dir():
        shutil.rmtree(dist)
        actions.append({"id": "deleted_dist", "path": str(dist), "ok": True})
    else:
        actions.append(
            {
                "id": "dist_preserved",
                "path": str(dist),
                "ok": True,
                "note": "Pass --delete-dist to remove packaged trees under dist/release/",
            }
        )

    return {
        "ok": bool(startup.get("ok")),
        "actions": actions,
        "install_tree_deleted": False,
        "note": (
            "The source/install tree is never auto-deleted (too dangerous). "
            "Delete it manually after backup."
        ),
        "plan": uninstall_plan(),
    }
