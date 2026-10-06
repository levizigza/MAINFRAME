"""Project-scoped secret facility — secrets never leave project home or exports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mainframe.projects.registry import get_project
from mainframe.secretdata.facility import LocalSecretFacility


def project_secrets(project_id: str) -> LocalSecretFacility | dict[str, Any]:
    rec = get_project(project_id)
    if not rec:
        return {"ok": False, "error": "project_not_found"}
    root = Path(rec["paths"]["secrets"])
    return LocalSecretFacility(root=root)


def store_project_secret(project_id: str, secret_id: str, value: str) -> dict[str, Any]:
    fac = project_secrets(project_id)
    if isinstance(fac, dict):
        return fac
    out = fac.store(secret_id, value, scopes=[f"project:{project_id}"])
    return {**out, "project_id": project_id, "exportable": False}


def get_project_secret(
    project_id: str,
    secret_id: str,
    *,
    requester_project_id: str,
) -> dict[str, Any]:
    """Foreign project cannot read sealed secrets."""
    if requester_project_id != project_id:
        return {
            "ok": False,
            "allowed": False,
            "exposed": False,
            "error": "cross_project_secret_denied",
            "value": None,
        }
    fac = project_secrets(project_id)
    if isinstance(fac, dict):
        return fac
    return fac.get(secret_id, requester_scope=f"project:{project_id}")
