"""Permission tokens bound to project identity — stale / foreign tokens refuse."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from mainframe.projects.registry import get_project, project_home, safe_project_id

TOKEN_FILE = "permission_tokens.json"


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso() -> str:
    return _utc().isoformat()


def _token_path(project_id: str) -> Path:
    return project_home(project_id) / "grants" / TOKEN_FILE


def _load(project_id: str) -> dict[str, Any]:
    path = _token_path(project_id)
    if not path.is_file():
        return {"tokens": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _save(project_id: str, data: dict[str, Any]) -> None:
    path = _token_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def issue_token(
    project_id: str,
    *,
    capabilities: list[str] | None = None,
    ttl_seconds: int = 3600,
) -> dict[str, Any]:
    rec = get_project(project_id)
    if not rec:
        return {"ok": False, "error": "project_not_found"}
    pid = safe_project_id(project_id)
    raw = secrets.token_urlsafe(24)
    token_id = hashlib.sha256(f"{pid}:{raw}".encode()).hexdigest()[:20]
    expires = _utc() + timedelta(seconds=max(1, int(ttl_seconds)))
    data = _load(pid)
    data.setdefault("tokens", {})[token_id] = {
        "token_id": token_id,
        "project_id": pid,
        "secret_hash": hashlib.sha256(raw.encode()).hexdigest(),
        "capabilities": list(capabilities or ["read"]),
        "expires_at": expires.isoformat(),
        "revoked": False,
        "created_at": _utc_iso(),
    }
    _save(pid, data)
    return {
        "ok": True,
        "token": raw,
        "token_id": token_id,
        "project_id": pid,
        "expires_at": expires.isoformat(),
        "capabilities": list(capabilities or ["read"]),
        "note": "Present token only to the issuing project; stale or foreign tokens are refused.",
    }


def validate_token(
    *,
    token: str,
    requester_project_id: str,
    issuing_project_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Stale permission tokens and tokens from another project cannot expose data.
    """
    try:
        req = safe_project_id(requester_project_id)
    except ValueError:
        return {"ok": False, "allowed": False, "error": "invalid_project_id", "exposed": False}

    # Search issuing project first, then requester (token always bound to issuer)
    candidates = []
    if issuing_project_id:
        try:
            candidates.append(safe_project_id(issuing_project_id))
        except ValueError:
            pass
    if req not in candidates:
        candidates.append(req)

    stamp = now or _utc()
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    for pid in candidates:
        data = _load(pid)
        for meta in (data.get("tokens") or {}).values():
            if meta.get("secret_hash") != token_hash:
                continue
            # Wrong project
            if meta.get("project_id") != req:
                return {
                    "ok": True,
                    "allowed": False,
                    "exposed": False,
                    "error": "stale_or_foreign_permission_token",
                    "token_project_id": meta.get("project_id"),
                    "requester_project_id": req,
                    "data_returned": None,
                }
            if meta.get("revoked"):
                return {
                    "ok": True,
                    "allowed": False,
                    "exposed": False,
                    "error": "token_revoked",
                    "requester_project_id": req,
                }
            try:
                exp = datetime.fromisoformat(meta["expires_at"])
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
            except (KeyError, ValueError):
                return {"ok": True, "allowed": False, "exposed": False, "error": "token_expiry_invalid"}
            if stamp > exp:
                return {
                    "ok": True,
                    "allowed": False,
                    "exposed": False,
                    "error": "stale_permission_token",
                    "expires_at": meta.get("expires_at"),
                    "requester_project_id": req,
                    "data_returned": None,
                }
            return {
                "ok": True,
                "allowed": True,
                "exposed": False,
                "token_id": meta.get("token_id"),
                "project_id": req,
                "capabilities": meta.get("capabilities"),
            }

    # Token might belong to another project — scan sibling homes lightly via registry
    from mainframe.projects.registry import list_projects

    for p in list_projects():
        opid = p["project_id"]
        if opid == req:
            continue
        data = _load(opid)
        for meta in (data.get("tokens") or {}).values():
            if meta.get("secret_hash") == token_hash:
                return {
                    "ok": True,
                    "allowed": False,
                    "exposed": False,
                    "error": "stale_or_foreign_permission_token",
                    "token_project_id": opid,
                    "requester_project_id": req,
                    "data_returned": None,
                }

    return {
        "ok": True,
        "allowed": False,
        "exposed": False,
        "error": "unknown_token",
        "requester_project_id": req,
        "data_returned": None,
    }


def revoke_token(project_id: str, token_id: str) -> dict[str, Any]:
    pid = safe_project_id(project_id)
    data = _load(pid)
    tok = (data.get("tokens") or {}).get(token_id)
    if not tok:
        return {"ok": False, "error": "token_not_found"}
    tok["revoked"] = True
    data["tokens"][token_id] = tok
    _save(pid, data)
    return {"ok": True, "token_id": token_id, "revoked": True}
