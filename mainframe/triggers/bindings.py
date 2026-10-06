"""Bind triggers to pre-registered jobs — events cannot select arbitrary commands."""

from __future__ import annotations

from typing import Any

from mainframe.triggers.store import TriggerStore


def bind_trigger(
    store: TriggerStore,
    *,
    binding_id: str,
    source: str,
    job_id: str,
    permission_scope: str,
    path_prefix: str | None = None,
    path_globs: list[str] | None = None,
    exclude_prefixes: list[str] | None = None,
) -> dict[str, Any]:
    """
    A binding fixes the job_id. Inbound events may only reference binding_id;
    they cannot supply argv/command.
    """
    if not job_id or not str(job_id).startswith("job_"):
        # Allow any non-empty job id from ScheduleStore; still refuse blank
        if not job_id:
            return {"ok": False, "error": "job_id_required"}
    filt = {
        "path_prefix": path_prefix,
        "path_globs": list(path_globs or []),
        "exclude_prefixes": list(
            exclude_prefixes
            or [
                ".mainframe/",
                ".git/",
                "__pycache__/",
                "node_modules/",
            ]
        ),
    }
    row = store.register_binding(
        binding_id=binding_id,
        source=source,
        job_id=job_id,
        permission_scope=permission_scope,
        filter_spec=filt,
    )
    return {
        "ok": True,
        "binding": row,
        "command_selectable_by_event": False,
        "note": "Events resolve to this binding's fixed job_id only.",
    }


def resolve_binding_for_event(
    store: TriggerStore,
    event: dict[str, Any],
) -> dict[str, Any]:
    """Map event → binding. Reject attempts to override command/argv."""
    payload = event.get("payload") or {}
    if any(k in payload for k in ("command", "argv", "command_argv", "shell")):
        return {
            "ok": False,
            "error": "event_cannot_select_command",
            "detail": "Authenticated events must not carry executable command fields.",
        }
    bid = event.get("binding_id")
    if not bid:
        return {"ok": False, "error": "binding_id_required"}
    binding = store.get_binding(bid)
    if not binding:
        return {"ok": False, "error": "unknown_binding"}
    if binding["source"] != event.get("source"):
        if event.get("source") != "manual":
            return {
                "ok": False,
                "error": "source_mismatch",
                "expected": binding["source"],
                "got": event.get("source"),
            }
    # Permission scope must match
    if event.get("permission_scope") != binding["permission_scope"]:
        return {
            "ok": False,
            "error": "permission_scope_mismatch",
            "expected": binding["permission_scope"],
            "got": event.get("permission_scope"),
        }
    return {"ok": True, "binding": binding, "job_id": binding["job_id"]}
