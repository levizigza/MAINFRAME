"""Acceptance: recurring report no re-prompt; new recipient/destructive held."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from mainframe.capabilities.authorize import authorize_action
from mainframe.capabilities.connector import apply_connector_or_workflow_change
from mainframe.capabilities.revoke import emergency_stop, revoke_grant
from mainframe.capabilities.runner import (
    decide_held,
    request_new_recipient_or_destructive,
    run_recurring_report,
)
from mainframe.capabilities.schedule_policy import schedule_trigger
from mainframe.capabilities.store import CapabilityStore
from mainframe.capabilities.types import ALL_CAPABILITIES


def run_capabilities_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    tmp = Path(tempfile.mkdtemp(prefix="mf-cap-"))
    store = CapabilityStore(tmp / "caps.sqlite")
    project = "proj_reports"

    # --- Grant scoped capabilities ---
    g = store.grant(
        project_id=project,
        capabilities=["reading", "editing", "running_tests", "sending_messages"],
        destinations=["local", "reports@example.com"],
        operations=["read_file", "edit_file", "run_tests", "send_report"],
        expires_at=None,
        source="user_authorization",
    )
    checks.append(
        {
            "id": "scoped_capabilities_bound_to_project",
            "ok": (
                g.get("ok")
                and set(ALL_CAPABILITIES)
                >= {"reading", "editing", "running_tests", "browsing", "sending_messages", "publishing", "deletion"}
                and g["grant"]["project_id"] == project
                and "reports@example.com" in g["grant"]["destinations"]
            ),
            "detail": g.get("grant"),
        }
    )

    # Carry forward
    cf = store.carry_forward(g["grant"]["grant_id"])
    checks.append(
        {
            "id": "carry_forward_existing_authorization",
            "ok": (
                cf.get("ok")
                and cf["grant"]["carried_forward_from"] == g["grant"]["grant_id"]
                and cf["grant"]["capabilities"] == g["grant"]["capabilities"]
            ),
            "detail": {
                "from": g["grant"]["grant_id"],
                "to": (cf.get("grant") or {}).get("grant_id"),
                "source": (cf.get("grant") or {}).get("source"),
            },
        }
    )

    # Reversible local editing — no re-prompt
    edit = authorize_action(
        store,
        project_id=project,
        capability="editing",
        operation="edit_file",
        destination="local",
        payload={"path": "README.md"},
    )
    checks.append(
        {
            "id": "reversible_local_no_reprompt",
            "ok": edit.get("allowed") is True and edit.get("prompt") is False,
            "detail": edit,
        }
    )

    # --- Recurring authorized report — no repeated prompts ---
    r1 = run_recurring_report(
        store,
        project_id=project,
        destination="reports@example.com",
        subject="Weekly",
        body="All green",
    )
    r2 = run_recurring_report(
        store,
        project_id=project,
        destination="reports@example.com",
        subject="Weekly",
        body="Still green",
    )
    checks.append(
        {
            "id": "authorized_recurring_report_no_reprompt",
            "ok": (
                r1.get("ok")
                and r1.get("ran_without_reprompt") is True
                and r1.get("prompts") == 0
                and r2.get("ok")
                and r2.get("ran_without_reprompt") is True
                and r2.get("prompts") == 0
            ),
            "detail": {"r1": r1.get("decision", {}).get("status"), "r2": r2.get("decision", {}).get("status")},
        }
    )

    # --- New recipient held ---
    new_rcpt = request_new_recipient_or_destructive(
        store,
        project_id=project,
        capability="sending_messages",
        operation="send_report",
        destination="new-person@elsewhere.test",
        payload={"subject": "Leak?", "body": "should hold"},
    )
    checks.append(
        {
            "id": "new_recipient_held_for_decision",
            "ok": (
                new_rcpt.get("held") is True
                and new_rcpt.get("requires_specific_decision") is True
                and (new_rcpt.get("preview") or {}).get("concrete") is True
                and "new-person@elsewhere.test" in ((new_rcpt.get("preview") or {}).get("summary_text") or "")
            ),
            "detail": {
                "hold_reason": (new_rcpt.get("preview") or {}).get("hold_reason"),
                "options": (new_rcpt.get("preview") or {}).get("decision_options"),
            },
        }
    )

    # --- Destructive deletion held ---
    dest = request_new_recipient_or_destructive(
        store,
        project_id=project,
        capability="deletion",
        operation="delete_paths",
        destination="local",
        payload={"paths": ["important.db"]},
    )
    checks.append(
        {
            "id": "destructive_action_held_for_decision",
            "ok": (
                dest.get("held") is True
                and dest.get("requires_specific_decision") is True
                and (dest.get("preview") or {}).get("hold_reason") == "destructive_deletion"
            ),
            "detail": dest.get("preview"),
        }
    )

    # Decide held item specifically
    held_id = ((new_rcpt.get("decision") or {}).get("queue_item") or {}).get("item_id")
    decided = decide_held(store, held_id, choice="deny") if held_id else {"ok": False}
    checks.append(
        {
            "id": "specific_decision_applied",
            "ok": decided.get("ok") and (decided.get("item") or {}).get("state") == "denied",
            "detail": decided.get("item"),
        }
    )

    # --- Schedule grants no permissions ---
    sched = schedule_trigger(
        store,
        project_id=project,
        schedule_id="cron_weekly",
        requested_capability="publishing",
    )
    checks.append(
        {
            "id": "schedule_alone_grants_no_permissions",
            "ok": (
                sched.get("schedule_grants_permissions") is False
                and sched.get("permissions_added") == []
            ),
            "detail": sched,
        }
    )

    # --- Connector/workflow change does not expand authority ---
    change = apply_connector_or_workflow_change(
        store,
        project_id=project,
        change_kind="workflow_edit",
        previous_authority={
            "capabilities": ["sending_messages"],
            "destinations": ["reports@example.com"],
            "operations": ["send_report"],
        },
        proposed_authority={
            "capabilities": ["sending_messages", "publishing", "deletion"],
            "destinations": ["reports@example.com", "https://evil.example/hook"],
            "operations": ["send_report", "publish_all", "delete_all"],
        },
    )
    checks.append(
        {
            "id": "connector_workflow_no_silent_expand",
            "ok": (
                change.get("silently_expanded") is False
                and change.get("expansion_detected") is True
                and "publishing" in change.get("expanded_capabilities", [])
                and change["authority_applied"]["capabilities"] == ["sending_messages"]
                and "https://evil.example/hook" not in change["authority_applied"]["destinations"]
            ),
            "detail": {
                "expanded_caps": change.get("expanded_capabilities"),
                "applied": change.get("authority_applied"),
            },
        }
    )

    # --- Revoke + emergency stop ---
    # Queue something then e-stop
    store.enqueue(
        project_id=project,
        capability="reading",
        operation="read_file",
        payload={"path": "a"},
        state="queued",
    )
    store.enqueue(
        project_id=project,
        capability="editing",
        operation="edit_file",
        payload={"path": "b"},
        state="held",
        hold_reason="test",
        preview={"concrete": True},
    )
    stop = emergency_stop(store, reason="accept_test")
    queued_after = store.list_queue(project, state="queued")
    held_after = store.list_queue(project, state="held")
    blocked = authorize_action(
        store,
        project_id=project,
        capability="reading",
        operation="read_file",
        destination="local",
    )
    rev = revoke_grant(store, g["grant"]["grant_id"])
    checks.append(
        {
            "id": "revoke_and_emergency_stop",
            "ok": (
                stop.get("stopped") is True
                and stop.get("cancelled_n", 0) >= 2
                and len(queued_after) == 0
                and len(held_after) == 0
                and blocked.get("status") == "emergency_stopped"
                and rev.get("ok")
                and (rev.get("grant") or {}).get("revoked") is True
            ),
            "detail": {
                "cancelled_n": stop.get("cancelled_n"),
                "blocked": blocked.get("status"),
                "revoked": (rev.get("grant") or {}).get("revoked"),
            },
        }
    )

    passed = sum(1 for c in checks if c["ok"])
    failed = len(checks) - passed
    return {"ok": failed == 0, "passed": passed, "failed": failed, "checks": checks}
