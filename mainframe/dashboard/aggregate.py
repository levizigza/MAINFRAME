"""Aggregate dashboard view from existing FreeForge stores (reuse, don't invent a second stack)."""

from __future__ import annotations

from typing import Any

from mainframe.capabilities.store import CapabilityStore
from mainframe.config import STATE_DIR, ensure_state
from mainframe.dashboard.notify import notify_policy
from mainframe.dashboard.states import normalize_state, recovery_hint
from mainframe.durable.store import DurableStore
from mainframe.editor.state import EditorTaskStore
from mainframe.quota.admit import AdmissionController
from mainframe.workflows.receipts import WorkflowReceiptStore


def _quota_snapshot() -> dict[str, Any]:
    ensure_state()
    ctl = AdmissionController(path=STATE_DIR / "quota_ledger.sqlite")
    try:
        key = ctl.bind_bucket(
            provider_id="ollama_local",
            window_id="dashboard",
        )
        snap = ctl.ledger.snapshot(key)
        return {
            "ok": "error" not in snap,
            "provider": snap.get("provider_id") or "ollama_local",
            "in_flight": snap.get("in_flight"),
            "remaining": snap.get("remaining"),
            "limits": snap.get("limits"),
            "availability": "local_ledger",
            "note": "Quota from FreeForge local ledger — not a hosted meter.",
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "availability": "unknown"}


def _workflow_cards(
    limit: int = 30,
    *,
    receipt_store: WorkflowReceiptStore | None = None,
) -> list[dict[str, Any]]:
    store = receipt_store or WorkflowReceiptStore()
    cards = []
    for run in store.list_recent_runs(limit=limit):
        steps = store.list_step_receipts(run["run_id"])
        checks = []
        artifacts = []
        for s in steps:
            checks.append(
                {
                    "ok": s.get("state") == "succeeded",
                    "step_id": s.get("step_id"),
                    "state": s.get("state"),
                    "error": s.get("error"),
                    "evidence": {
                        "operation_id": s.get("operation_id"),
                        "delivery_status": s.get("delivery_status"),
                        "effect": (s.get("effect_receipt") or {}).get("outcome")
                        if s.get("effect_receipt")
                        else None,
                    },
                }
            )
            for a in s.get("artifact_refs") or []:
                artifacts.append(a)
            out = s.get("output") or {}
            if out.get("artifact_path"):
                artifacts.append(out["artifact_path"])
        st = normalize_state(
            run.get("state"),
            cancelled=bool(run.get("cancel_requested")),
            outcome_unknown=run.get("state") == "outcome_unknown",
        )
        failed = [c for c in checks if not c["ok"] and c.get("state") not in {"succeeded"}]
        reason = run.get("error") or (failed[-1].get("error") if failed else None)
        cards.append(
            {
                "id": run["run_id"],
                "kind": "workflow",
                "label": run.get("workflow_id") or run["run_id"],
                "state": st,
                "raw_state": run.get("state"),
                "updated_at": run.get("updated_at"),
                "checks": checks[-12:],
                "artifacts": list(dict.fromkeys(artifacts))[:20],
                "pending_decisions": [],
                "recovery": recovery_hint(st, reason=reason, checks=failed),
                "controls": {"stop": True, "resume": st in {"blocked", "running", "proposed"}},
            }
        )
    return cards


def _editor_cards(*, editor_store: EditorTaskStore | None = None) -> list[dict[str, Any]]:
    store = editor_store or EditorTaskStore()
    cards = []
    for meta in store.list_tasks():
        task = store.load(meta["task_id"])
        if not task:
            continue
        st = normalize_state(
            task.get("state"),
            cancelled=bool(task.get("cancelled")),
        )
        prop = task.get("proposal") or {}
        apply = task.get("apply") or {}
        checks = []
        if prop:
            checks.append(
                {
                    "ok": bool((prop.get("validation") or {}).get("ok", prop.get("reviewable_diffs"))),
                    "step_id": "propose",
                    "state": "proposed",
                    "evidence": {
                        "operation_id": prop.get("operation_id"),
                        "diffs_n": len(prop.get("reviewable_diffs") or []),
                    },
                }
            )
        if apply:
            checks.append(
                {
                    "ok": bool(apply.get("ok")),
                    "step_id": "apply",
                    "state": "verified" if apply.get("ok") else "blocked",
                    "error": apply.get("error"),
                    "evidence": {
                        "operation_id": apply.get("operation_id"),
                        "batch_id": apply.get("batch_id"),
                        "duplicate_suppressed": apply.get("duplicate_suppressed"),
                    },
                }
            )
        artifacts = []
        if apply.get("result") and apply["result"].get("applied"):
            for a in apply["result"]["applied"]:
                if a.get("path"):
                    artifacts.append(a["path"])
        failed = [c for c in checks if not c["ok"]]
        reason = None
        if apply and not apply.get("ok"):
            reason = apply.get("error") or "apply_failed"
        cards.append(
            {
                "id": task["task_id"],
                "kind": "editor",
                "label": (task.get("chat") or task["task_id"])[:80],
                "state": st,
                "raw_state": task.get("state"),
                "updated_at": task.get("updated_at"),
                "checks": checks,
                "artifacts": artifacts,
                "pending_decisions": [],
                "recovery": recovery_hint(st, reason=reason, checks=failed),
                "controls": {"stop": True, "resume": not task.get("cancelled")},
                "project_boundary": task.get("workspace"),
            }
        )
    return cards


def _capability_pending(
    project_id: str = "default",
    *,
    cap_store: CapabilityStore | None = None,
) -> list[dict[str, Any]]:
    store = cap_store or CapabilityStore()
    held = store.list_queue(project_id, state="held")
    out = []
    for item in held:
        out.append(
            {
                "id": item.get("item_id"),
                "kind": "pending_decision",
                "label": f"Held: {item.get('hold_reason')}",
                "state": "blocked",
                "raw_state": "held_for_decision",
                "updated_at": item.get("updated_at"),
                "checks": [
                    {
                        "ok": False,
                        "step_id": "capability_hold",
                        "state": "blocked",
                        "error": item.get("hold_reason"),
                        "evidence": {"preview": item.get("preview")},
                    }
                ],
                "artifacts": [],
                "pending_decisions": [
                    {
                        "item_id": item.get("item_id"),
                        "hold_reason": item.get("hold_reason"),
                        "options": (item.get("preview") or {}).get("decision_options")
                        or ["allow_once", "deny"],
                    }
                ],
                "recovery": recovery_hint(
                    "blocked",
                    reason=item.get("hold_reason"),
                    checks=[{"ok": False, "error": item.get("hold_reason")}],
                ),
                "controls": {"stop": False, "resume": False, "decide": True},
                "project_id": project_id,
            }
        )
    return out


def _durable_cards(
    limit: int = 20,
    *,
    durable_store: DurableStore | None = None,
) -> list[dict[str, Any]]:
    store = durable_store or DurableStore()
    cards = []
    for state in ("outcome_unknown", "failed", "started", "succeeded", "cancelled"):
        try:
            rows = store.list_by_state(state)[: max(1, limit // 5)]
        except Exception:  # noqa: BLE001
            rows = []
        for t in rows:
            st = normalize_state(t.get("state"), outcome_unknown=t.get("state") == "outcome_unknown")
            cards.append(
                {
                    "id": t.get("operation_id"),
                    "kind": "durable",
                    "label": t.get("goal") or t.get("operation_id"),
                    "state": st,
                    "raw_state": t.get("state"),
                    "updated_at": t.get("updated_at"),
                    "checks": [
                        {
                            "ok": st == "verified",
                            "step_id": "durable",
                            "state": st,
                            "evidence": {
                                "effect_receipt": bool(t.get("effect_receipt")),
                                "idempotency_key": t.get("idempotency_key"),
                            },
                        }
                    ],
                    "artifacts": [],
                    "pending_decisions": [],
                    "recovery": recovery_hint(st, reason=t.get("error")),
                    "controls": {"stop": True, "resume": st in {"blocked", "running", "outcome_unknown"}},
                }
            )
    return cards[:limit]


def build_dashboard(
    *,
    project_id: str = "default",
    editor_store: EditorTaskStore | None = None,
    receipt_store: WorkflowReceiptStore | None = None,
    cap_store: CapabilityStore | None = None,
    durable_store: DurableStore | None = None,
    include_live: bool = True,
) -> dict[str, Any]:
    if include_live:
        ensure_state()
    tasks: list[dict[str, Any]] = []
    if include_live or receipt_store is not None:
        tasks.extend(_workflow_cards(receipt_store=receipt_store))
    if include_live or editor_store is not None:
        tasks.extend(_editor_cards(editor_store=editor_store))
    if include_live or cap_store is not None:
        tasks.extend(_capability_pending(project_id, cap_store=cap_store))
    if include_live or durable_store is not None:
        tasks.extend(_durable_cards(durable_store=durable_store))
    tasks.sort(key=lambda t: t.get("updated_at") or "", reverse=True)
    history = [
        {
            "id": t["id"],
            "kind": t["kind"],
            "state": t["state"],
            "label": t["label"],
            "updated_at": t.get("updated_at"),
        }
        for t in tasks
    ]
    return {
        "ok": True,
        "view": "freeforge_local_dashboard",
        "reused_views": [
            "workflows.receipts",
            "editor.tasks",
            "capabilities.queue",
            "durable.tasks",
            "quota.ledger",
        ],
        "auth_boundaries_intact": True,
        "project_id": project_id,
        "states_legend": [
            ["proposed", "Awaiting review / not started"],
            ["running", "In progress or interrupted"],
            ["verified", "Checks passed"],
            ["blocked", "Needs human fix or decision"],
            ["outcome_unknown", "External effect uncertain — no blind retry"],
            ["cancelled", "Stopped; completed effects kept"],
        ],
        "tasks": tasks,
        "workflow_history": history,
        "quota": _quota_snapshot(),
        "pending_decisions": [t for t in tasks if t.get("pending_decisions")],
        "notifications": notify_policy(),
        "decorative_agent_activity": False,
        "note": "Shows actual checks and evidence only — not animated agent chrome.",
    }


def task_detail(
    task_id: str,
    *,
    project_id: str = "default",
    **kwargs: Any,
) -> dict[str, Any]:
    dash = build_dashboard(project_id=project_id, **kwargs)
    for t in dash.get("tasks") or []:
        if t.get("id") == task_id:
            return {"ok": True, "task": t, "recovery": t.get("recovery"), "without_logs": True}
    return {"ok": False, "error": "not_found", "task_id": task_id}
