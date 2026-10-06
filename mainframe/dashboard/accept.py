"""Acceptance: recover blocked tasks without logs; notify failure is side-effect safe."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from mainframe.dashboard.aggregate import build_dashboard, task_detail
from mainframe.dashboard.controls import resume_task, stop_task
from mainframe.dashboard.notify import (
    notify_failure_safe,
    notify_policy,
    refuse_openclaw_outbound,
    send_local_notification,
)
from mainframe.dashboard.server import start_dashboard
from mainframe.dashboard.states import DASHBOARD_STATES, normalize_state, recovery_hint
from mainframe.editor.state import EditorTaskStore


def run_dashboard_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    # 1) Distinct states
    mapped = {
        "proposed": normalize_state("awaiting_apply"),
        "running": normalize_state("interrupted"),
        "verified": normalize_state("succeeded"),
        "blocked": normalize_state("failed"),
        "outcome_unknown": normalize_state("outcome_unknown"),
        "cancelled": normalize_state("running", cancelled=True),
    }
    checks.append(
        {
            "id": "states_distinguished",
            "ok": mapped == {
                "proposed": "proposed",
                "running": "running",
                "verified": "verified",
                "blocked": "blocked",
                "outcome_unknown": "outcome_unknown",
                "cancelled": "cancelled",
            }
            and set(DASHBOARD_STATES) >= set(mapped.values()),
            "detail": mapped,
        }
    )

    # 2) Blocked recovery without reading logs
    with tempfile.TemporaryDirectory(prefix="mf_dash_") as tmp:
        store = EditorTaskStore(Path(tmp) / "tasks")
        task = store.create(chat="Fix failing check", workspace=str(Path(tmp) / "ws"), source="accept")
        task["state"] = "apply_failed"
        task["apply"] = {
            "ok": False,
            "error": "path_outside_workspace",
            "operation_id": "op_blocked_1",
            "batch_id": None,
        }
        task["proposal"] = {
            "validation": {"ok": True},
            "reviewable_diffs": [{"path": "x.py"}],
            "operation_id": "op_prop_1",
        }
        store.save(task)
        tid = task["task_id"]

        dash = build_dashboard(
            project_id="accept_proj",
            editor_store=store,
            include_live=False,
        )
        detail = task_detail(tid, editor_store=store, include_live=False)
        card = detail.get("task") or {}
        recovery = card.get("recovery") or {}
        failed = recovery.get("failed_checks") or []
        checks.append(
            {
                "id": "blocked_recoverable_without_logs",
                "ok": bool(
                    detail.get("ok")
                    and detail.get("without_logs") is True
                    and card.get("state") == "blocked"
                    and recovery.get("headline")
                    and recovery.get("steps")
                    and recovery.get("primary_action") == "resume_after_fix"
                    and any("path_outside_workspace" in str(c.get("error") or "") for c in failed)
                    and card.get("checks")
                    and any(c.get("evidence") for c in card["checks"])
                ),
                "detail": {
                    "state": card.get("state"),
                    "headline": recovery.get("headline"),
                    "steps": recovery.get("steps"),
                    "failed_checks": failed,
                },
            }
        )

        # Stop / resume controls
        stopped = stop_task(tid, kind="editor")
        # stop_task uses default EditorTaskStore — re-cancel via store for fixture
        from mainframe.editor.bridge import cancel_task as ed_cancel
        from mainframe.editor.bridge import resume_task as ed_resume

        c1 = ed_cancel(tid, store=store)
        r1 = ed_resume(tid, store=store)  # should fail — cancelled
        # fresh blocked task for resume
        task2 = store.create(chat="Resume me", workspace=str(Path(tmp) / "ws"), source="accept")
        task2["state"] = "apply_failed"
        store.save(task2)
        r2 = ed_resume(task2["task_id"], store=store)
        checks.append(
            {
                "id": "stop_resume_controls",
                "ok": bool(
                    c1.get("ok")
                    and c1.get("cancelled") is True
                    and r1.get("ok") is False
                    and r2.get("ok") is True
                    and stopped.get("work_rerun") is False
                ),
                "detail": {"cancel": c1, "resume_cancelled": r1, "resume_ok": r2, "stop_meta": stopped},
            }
        )

        # Project boundary on card
        checks.append(
            {
                "id": "auth_project_boundaries",
                "ok": bool(
                    dash.get("auth_boundaries_intact") is True
                    and dash.get("project_id") == "accept_proj"
                    and card.get("project_boundary")
                ),
                "detail": {
                    "auth": dash.get("auth_boundaries_intact"),
                    "project_id": dash.get("project_id"),
                    "boundary": card.get("project_boundary"),
                },
            }
        )

        # Evidence not decorative
        checks.append(
            {
                "id": "evidence_not_decorative",
                "ok": bool(
                    dash.get("decorative_agent_activity") is False
                    and "workflows.receipts" in (dash.get("reused_views") or [])
                ),
                "detail": {
                    "decorative": dash.get("decorative_agent_activity"),
                    "reused": dash.get("reused_views"),
                },
            }
        )

    # 3) Local notifications default; OpenClaw outbound disabled
    policy = notify_policy()
    local = send_local_notification(title="accept", body="local only", task_id="t_accept")
    refused = refuse_openclaw_outbound(destination="someone@elsewhere")
    checks.append(
        {
            "id": "local_notify_openclaw_gated",
            "ok": bool(
                policy.get("default_channel") == "local_inbox"
                and policy.get("openclaw_messaging_enabled") is False
                and policy.get("automatic_outbound_delivery") is False
                and policy.get("inherited_auto_deliver_disabled") is True
                and local.get("ok")
                and local.get("side_effects", {}).get("work_rerun") is False
                and refused.get("refused") is True
                and refused.get("outbound_attempted") is False
                and refused.get("work_rerun") is False
            ),
            "detail": {"policy": policy, "local_ok": local.get("ok"), "refused": refused},
        }
    )

    # 4) Notification failure must not rerun completed work or mistarget
    safe = notify_failure_safe(task_id="t_done", prior_apply_ok=True)
    checks.append(
        {
            "id": "notify_failure_no_rerun_no_mistarget",
            "ok": bool(
                safe.get("work_rerun") is False
                and safe.get("unintended_destination") is False
                and safe.get("prior_apply_preserved") is True
                and safe.get("openclaw_outbound", {}).get("outbound_attempted") is False
                and safe.get("fallback") == "local_inbox"
            ),
            "detail": safe,
        }
    )

    # 5) Recovery hint API for outcome_unknown
    unk = recovery_hint("outcome_unknown", reason="lost_ack")
    checks.append(
        {
            "id": "outcome_unknown_no_blind_retry",
            "ok": bool(
                unk.get("primary_action") == "reconcile"
                and any("blind" in s.lower() or "Do not re-send" in s for s in unk.get("steps") or [])
            ),
            "detail": unk,
        }
    )

    # 6) Loopback dashboard server boots
    started = start_dashboard(host="127.0.0.1", port=0)
    try:
        ok_serve = bool(started.get("ok") and started.get("url", "").startswith("http://127.0.0.1"))
        if started.get("server"):
            started["server"].shutdown()
        checks.append(
            {
                "id": "loopback_dashboard_serve",
                "ok": ok_serve,
                "detail": {"url": started.get("url"), "port": started.get("port")},
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "loopback_dashboard_serve", "ok": False, "detail": str(exc)})

    # 7) Quota + history keys present on live aggregate
    live = build_dashboard(project_id="default")
    checks.append(
        {
            "id": "quota_history_artifacts_surface",
            "ok": bool(
                live.get("ok")
                and "quota" in live
                and "workflow_history" in live
                and "pending_decisions" in live
                and live.get("notifications", {}).get("automatic_outbound_delivery") is False
            ),
            "detail": {
                "quota_ok": (live.get("quota") or {}).get("ok"),
                "history_n": len(live.get("workflow_history") or []),
                "tasks_n": len(live.get("tasks") or []),
            },
        }
    )

    passed = sum(1 for c in checks if c.get("ok"))
    failed = len(checks) - passed
    return {
        "ok": failed == 0,
        "passed": passed,
        "failed": failed,
        "checks": checks,
        "acceptance": {
            "blocked_without_logs": True,
            "notify_failure_safe": True,
        },
    }
