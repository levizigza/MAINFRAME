"""Local fixture runner — checkpoints, resume, cancel, retries, effect receipts."""

from __future__ import annotations

import hashlib
import time
import uuid
from pathlib import Path
from typing import Any

from mainframe.workflows.effects import compensation_for
from mainframe.workflows.handlers import get_handler
from mainframe.workflows.plan import topological_order
from mainframe.workflows.receipts import WorkflowReceiptStore
from mainframe.workflows.redact_diag import redact_diag
from mainframe.workflows.retry_policy import reconcile_before_retry, should_retry
from mainframe.workflows.schema import normalize_workflow
from mainframe.workflows.typesafe import validate_value_against_schema
from mainframe.workflows.validate import validate_workflow


def _eval_condition(condition: dict[str, Any] | None, ctx: dict[str, Any]) -> bool:
    if not condition:
        return True
    field = condition.get("field")
    op = condition.get("op") or "eq"
    expected = condition.get("value")
    actual = ctx.get(field) if field else None
    if op == "eq":
        return actual == expected
    if op == "neq":
        return actual != expected
    if op == "truthy":
        return bool(actual)
    if op == "exists":
        return field in ctx
    return True


def _stable_operation_id(run_id: str, step_id: str) -> str:
    raw = f"{run_id}:{step_id}"
    return "op_" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def run_workflow(
    raw: dict[str, Any],
    *,
    inputs: dict[str, Any] | None = None,
    work_dir: Path,
    available_capabilities: set[str] | None = None,
    store: WorkflowReceiptStore | None = None,
    human_decision: str | None = "approve",
    strict_capabilities: bool = True,
    resume_run_id: str | None = None,
    interrupt_after: str | None = None,
    max_concurrent: int = 4,
    delivery_mode: str | None = None,
    model_fixture: dict[str, Any] | None = None,
    force_ai_unavailable: bool = False,
    project_id: str | None = None,
    require_project: bool = False,
) -> dict[str, Any]:
    """
    Execute / resume a workflow with step checkpoints and effect receipts.

    interrupt_after: stop after successfully completing this step (for acceptance).
    resume_run_id: continue a prior interrupted/failed run without duplicating effects.
    model_fixture: offline/fixture model response for typed AI steps.
    force_ai_unavailable: checkpoint AI steps and continue independent work only.
    project_id / require_project: bind run to an explicit project identity.
    """
    if require_project or project_id is not None:
        from mainframe.projects.bind import bind_workflow_run

        wf_id = str((raw or {}).get("id") or (raw or {}).get("workflow_id") or "workflow")
        bound = bind_workflow_run(
            project_id=project_id,
            workflow_id=wf_id,
            work_dir=work_dir,
        )
        if not bound.get("ok"):
            return {
                "ok": False,
                "blocked": True,
                "state": "blocked_project_binding",
                "error": bound.get("error") or "project_id_required",
                "project_binding": bound,
                "side_effects": False,
            }

    inputs = dict(inputs or {})
    work_dir.mkdir(parents=True, exist_ok=True)
    store = store or WorkflowReceiptStore(work_dir / "receipts.sqlite")

    validation = validate_workflow(
        raw,
        available_capabilities=available_capabilities,
        strict_capabilities=strict_capabilities,
    )
    wf = validation.get("normalized") or normalize_workflow(raw)

    if not validation.get("ok"):
        return {
            "ok": False,
            "blocked": True,
            "state": "blocked_validation",
            "validation": validation,
            "outputs": {},
            "step_outputs": {},
            "receipts": [],
            "prior_outputs_preserved": True,
        }

    if resume_run_id:
        run_id = resume_run_id
        prior = store.succeeded_steps(run_id)
        existing = store.get_run(run_id)
        if existing and existing.get("inputs"):
            inputs = {**existing["inputs"], **inputs}
    else:
        run_id = store.start_run(wf["id"], wf["format_version"], inputs)
        prior = {}

    slot = store.acquire_slot(max_concurrent=max_concurrent, run_id=run_id)
    if not slot.get("ok"):
        store.finish_run(run_id, state="blocked", error="concurrency_limit")
        return {
            "ok": False,
            "blocked": True,
            "state": "blocked_concurrency",
            "run_id": run_id,
            "detail": slot,
            "step_outputs": {},
            "receipts": [],
        }

    ctx: dict[str, Any] = dict(inputs)
    if human_decision is not None:
        ctx["human_decision"] = human_decision
    if delivery_mode:
        ctx["_delivery_mode"] = delivery_mode
    if model_fixture is not None:
        ctx["_model_fixture"] = model_fixture
    if force_ai_unavailable:
        ctx["_force_ai_unavailable"] = True

    step_outputs: dict[str, Any] = {}
    for sid, info in prior.items():
        if info.get("output"):
            step_outputs[sid] = info["output"]
            ctx.update(info["output"])

    receipts: list[dict[str, Any]] = list(store.list_step_receipts(run_id)) if resume_run_id else []
    smap = {s["id"]: s for s in wf["steps"]}
    order = topological_order(wf)

    blocked_at: str | None = None
    blocked_reason: str | None = None
    interrupted = False
    cancelled = False
    duplicated_suppressed: list[str] = []
    checkpointed_ai: list[str] = []
    unresolved: set[str] = set()
    skipped_dependent: list[str] = []

    def _deps_unresolved(step_id: str) -> bool:
        for dep in smap[step_id].get("depends_on") or []:
            if dep in unresolved:
                return True
        return False

    for sid in order:
        if store.cancel_requested(run_id):
            cancelled = True
            blocked_at = sid
            blocked_reason = "cancelled"
            store.record_step(
                run_id, step_id=sid, kind=smap[sid]["kind"], state="cancelled", error="cancelled"
            )
            break

        step = smap[sid]

        # Resume: skip steps that already succeeded (no duplicate effects)
        if sid in prior and prior[sid].get("output") is not None:
            duplicated_suppressed.append(sid)
            continue

        # Skip work that depends on checkpointed / unresolved AI (or failed) steps
        if _deps_unresolved(sid):
            skipped_dependent.append(sid)
            unresolved.add(sid)
            receipts.append(
                store.record_step(
                    run_id,
                    step_id=sid,
                    kind=step["kind"],
                    state="skipped_waiting_ai",
                    error="depends_on_checkpointed_ai",
                    checkpoint={"waiting_on": list(step.get("depends_on") or [])},
                )
            )
            continue

        if not _eval_condition(step.get("condition"), ctx):
            rec = store.record_step(
                run_id, step_id=sid, kind=step["kind"], state="skipped", output={"skipped": True}
            )
            receipts.append(rec)
            continue

        missing_non_ai = False
        for perm in step.get("permissions") or []:
            if available_capabilities is not None and perm not in available_capabilities:
                # AI inference unavailable → checkpoint and continue independent work
                if step["kind"] == "ai" and perm == "ai.infer":
                    checkpointed_ai.append(sid)
                    unresolved.add(sid)
                    blocked_at = blocked_at or sid
                    blocked_reason = blocked_reason or f"unavailable_capability:{perm}"
                    receipts.append(
                        store.record_step(
                            run_id,
                            step_id=sid,
                            kind="ai",
                            state="checkpointed",
                            error=f"unavailable_capability:{perm}",
                            checkpoint={
                                "ai_type": step.get("ai_type"),
                                "continue_independent_work": True,
                                "promised_meaning_preserved": True,
                            },
                        )
                    )
                    missing_non_ai = False
                    break
                blocked_at = sid
                blocked_reason = f"unavailable_capability:{perm}"
                receipts.append(
                    store.record_step(
                        run_id, step_id=sid, kind=step["kind"], state="blocked", error=blocked_reason
                    )
                )
                missing_non_ai = True
                break
        if sid in unresolved:
            continue
        if missing_non_ai or blocked_at == sid and blocked_reason and blocked_reason.startswith("unavailable_capability:") and step["kind"] != "ai":
            if step["kind"] != "ai":
                break
        if blocked_at == sid and step["kind"] != "ai" and blocked_reason and "unavailable_capability" in blocked_reason:
            break

        handler_name = step.get("handler") or sid
        # Default AI handlers from ai_type
        if step["kind"] == "ai" and handler_name == sid:
            at = step.get("ai_type")
            handler_name = {
                "extract": "ai_extract",
                "classify": "ai_classify",
                "summarize": "ai_summarize",
                "propose_code": "ai_propose_code",
            }.get(at or "", handler_name)

        handler = get_handler(handler_name)
        if handler is None:
            if step["kind"] == "ai":
                # No handler and no inference — checkpoint
                checkpointed_ai.append(sid)
                unresolved.add(sid)
                blocked_at = blocked_at or sid
                blocked_reason = blocked_reason or f"unknown_handler:{handler_name}"
                receipts.append(
                    store.record_step(
                        run_id,
                        step_id=sid,
                        kind="ai",
                        state="checkpointed",
                        error=blocked_reason,
                        checkpoint={"continue_independent_work": True},
                    )
                )
                continue
            blocked_at = sid
            blocked_reason = f"unknown_handler:{handler_name}"
            receipts.append(
                store.record_step(
                    run_id, step_id=sid, kind=step["kind"], state="blocked", error=blocked_reason
                )
            )
            break

        op_id = _stable_operation_id(run_id, sid)
        prior_effect = store.get_effect(op_id)
        if prior_effect and (
            prior_effect.get("outcome") == "succeeded"
            or prior_effect.get("execution_status") == "succeeded"
        ):
            # Effect already applied — reuse without re-running handler
            out = prior.get(sid, {}).get("output") or prior_effect.get("detail") or {}
            if isinstance(out, dict):
                step_outputs[sid] = {**out, "effect_receipt": prior_effect, "operation_id": op_id}
                ctx.update(step_outputs[sid])
            duplicated_suppressed.append(sid)
            receipts.append(
                store.record_step(
                    run_id,
                    step_id=sid,
                    kind=step["kind"],
                    state="succeeded",
                    operation_id=op_id,
                    output=step_outputs.get(sid),
                    effect_receipt={**prior_effect, "duplicate_suppressed": True},
                    delivery_status=prior_effect.get("delivery_status"),
                    checkpoint={"resumed": True, "skipped_duplicate": True},
                )
            )
            continue

        if prior_effect and prior_effect.get("outcome") == "unknown":
            recon = reconcile_before_retry(prior_effect)
            blocked_at = sid
            blocked_reason = "outcome_unknown"
            receipts.append(
                store.record_step(
                    run_id,
                    step_id=sid,
                    kind=step["kind"],
                    state="outcome_unknown",
                    operation_id=op_id,
                    effect_receipt=prior_effect,
                    delivery_status="unknown",
                    error="reconcile_uncertain_write_before_retry",
                    checkpoint={"reconcile": recon},
                )
            )
            break

        retries = int((step.get("retries") or {}).get("max") or 0)
        timeout_ms = int(step.get("timeout_ms") or 30_000)
        loop = step.get("loop")
        max_iter = int((loop or {}).get("max_iterations") or 1)
        last_out: dict[str, Any] | None = None
        attempt = 0
        ok_step = False
        err: str | None = None
        ai_checkpoint = False
        ai_rejected = False

        for _iteration in range(max_iter):
            for attempt_i in range(retries + 1):
                attempt = attempt_i + 1
                t0 = time.perf_counter()
                try:
                    args = dict(step.get("args") or {})
                    args["operation_id"] = op_id
                    if step.get("ai_type"):
                        args.setdefault("ai_type", step["ai_type"])
                    for k in (step.get("inputs") or {}).get("properties") or {}:
                        if k in ctx and k not in args:
                            args[k] = ctx[k]
                    ctx["_operation_id"] = op_id
                    last_out = handler(args, ctx, work_dir)
                    elapsed = (time.perf_counter() - t0) * 1000
                    if elapsed > timeout_ms:
                        raise TimeoutError(f"timeout_ms:{timeout_ms}")
                    if last_out.get("_human_pending"):
                        blocked_at = sid
                        blocked_reason = "human_decision_pending"
                        break
                    # Typed AI: paused → checkpoint; rejected evidence → fail step
                    if step["kind"] == "ai" and (
                        last_out.get("paused") or last_out.get("checkpoint")
                    ) and not last_out.get("ok"):
                        ai_checkpoint = True
                        ok_step = False
                        err = last_out.get("reason") or last_out.get("message") or "ai_checkpointed"
                        break
                    if step["kind"] == "ai" and last_out.get("rejected") and not last_out.get("ok"):
                        ai_rejected = True
                        ok_step = False
                        err = last_out.get("reason") or "ai_evidence_rejected"
                        break
                    if step["kind"] == "ai" and last_out.get("ok"):
                        # AI success may be uncertain — still a completed semantic step
                        ok_step = True
                        break
                    ok_schema, schema_reason = validate_value_against_schema(
                        last_out, step.get("outputs")
                    )
                    if not ok_schema and step["kind"] != "ai":
                        raise ValueError(f"output_schema:{schema_reason}")
                    if not ok_schema and step["kind"] == "ai" and not last_out.get("uncertain"):
                        # Soft: still require schema unless uncertain
                        if (step.get("outputs") or {}).get("required"):
                            raise ValueError(f"output_schema:{schema_reason}")
                    ok_step = True
                    break
                except Exception as exc:  # noqa: BLE001
                    err = f"{type(exc).__name__}:{exc}"
                    decision = should_retry(
                        step,
                        attempt=attempt,
                        error_name=type(exc).__name__,
                        prior_effect=store.get_effect(op_id),
                    )
                    if not decision.get("retry"):
                        ok_step = False
                        if decision.get("requires_reconcile"):
                            blocked_reason = "reconcile_uncertain_write_before_retry"
                            blocked_at = sid
                        break
                    ok_step = False
                    time.sleep(min(0.01 * attempt, 0.05))
            if blocked_at or ai_checkpoint or ai_rejected or not ok_step:
                break
            if loop and loop.get("until_field"):
                if last_out and last_out.get(loop["until_field"]):
                    break

        if ai_checkpoint:
            checkpointed_ai.append(sid)
            unresolved.add(sid)
            blocked_at = blocked_at or sid
            blocked_reason = blocked_reason or err or "ai_step_unavailable_or_paused"
            receipts.append(
                store.record_step(
                    run_id,
                    step_id=sid,
                    kind="ai",
                    state="checkpointed",
                    attempt=attempt,
                    operation_id=op_id,
                    output=redact_diag(last_out) if last_out else None,
                    error=blocked_reason,
                    checkpoint={
                        "ai_type": step.get("ai_type"),
                        "continue_independent_work": True,
                        "promised_meaning_preserved": True,
                        "fallback_used": bool((last_out or {}).get("fallback_used")),
                    },
                )
            )
            continue

        if ai_rejected:
            blocked_at = sid
            blocked_reason = err or "ai_evidence_rejected"
            receipts.append(
                store.record_step(
                    run_id,
                    step_id=sid,
                    kind="ai",
                    state="rejected",
                    attempt=attempt,
                    operation_id=op_id,
                    output=redact_diag(last_out) if last_out else None,
                    error=blocked_reason,
                    checkpoint={"evidence": (last_out or {}).get("evidence")},
                )
            )
            break

        if blocked_at and blocked_at == sid and not ok_step and not ai_checkpoint:
            receipts.append(
                store.record_step(
                    run_id,
                    step_id=sid,
                    kind=step["kind"],
                    state="blocked",
                    attempt=attempt,
                    operation_id=op_id,
                    error=blocked_reason,
                    output=last_out,
                )
            )
            break

        if not ok_step:
            blocked_at = sid
            blocked_reason = err or "step_failed"
            receipts.append(
                store.record_step(
                    run_id,
                    step_id=sid,
                    kind=step["kind"],
                    state="failed",
                    attempt=attempt,
                    operation_id=op_id,
                    error=blocked_reason,
                )
            )
            break

        assert last_out is not None
        last_out = redact_diag(last_out)
        effect = last_out.get("effect_receipt")
        delivery_status = last_out.get("delivery_status") or (
            (effect or {}).get("delivery_status") if effect else None
        )
        step_outputs[sid] = last_out
        ctx.update(last_out)
        checkpoint = {
            "step_id": sid,
            "operation_id": op_id,
            "completed_at_attempt": attempt,
            "artifact_refs": list(step.get("artifact_refs") or []),
            "ai_type": step.get("ai_type"),
        }
        receipts.append(
            store.record_step(
                run_id,
                step_id=sid,
                kind=step["kind"],
                state="succeeded" if not last_out.get("_outcome_unknown") else "outcome_unknown",
                attempt=attempt,
                operation_id=op_id,
                output=last_out,
                artifact_refs=list(step.get("artifact_refs") or []),
                effect_receipt=effect,
                delivery_status=delivery_status,
                checkpoint=checkpoint,
                error="outcome_unknown" if last_out.get("_outcome_unknown") else None,
            )
        )

        if last_out.get("_outcome_unknown"):
            blocked_at = sid
            blocked_reason = "outcome_unknown"
            break

        if last_out.get("_delivery_failed"):
            # Retain failed delivery for review; do not wipe prior outputs
            blocked_at = sid
            blocked_reason = "delivery_failed"
            break

        if interrupt_after and sid == interrupt_after:
            interrupted = True
            store.finish_run(
                run_id,
                state="interrupted",
                outputs=step_outputs,
                error=f"interrupt_after:{sid}",
            )
            return {
                "ok": False,
                "interrupted": True,
                "state": "interrupted",
                "interrupt_after": sid,
                "run_id": run_id,
                "step_outputs": step_outputs,
                "outputs": dict(step_outputs),
                "receipts": store.list_step_receipts(run_id),
                "prior_outputs_preserved": True,
                "duplicated_suppressed": duplicated_suppressed,
                "artifacts_on_disk": _list_artifacts(work_dir),
                "failed_deliveries": store.failed_deliveries(run_id),
                "checkpointed_ai": checkpointed_ai,
                "skipped_dependent": skipped_dependent,
                "compensation_policy": {
                    "delete_local_draft": compensation_for("write_local_draft"),
                    "retract_received_message": compensation_for("retract_received_message"),
                },
                "ownership": {
                    "workflow_semantics": "freeforge",
                    "scheduling_sessions": "openclaw_not_duplicated",
                },
            }

    final_outputs = {
        k: step_outputs[k]
        for k in (wf.get("output_steps") or list(step_outputs.keys()))
        if k in step_outputs
    }
    if "write_report" in step_outputs:
        final_outputs = {**final_outputs, **step_outputs["write_report"]}
    if "deliver" in step_outputs:
        final_outputs = {**final_outputs, **step_outputs["deliver"]}
    if "write_digest" in step_outputs:
        final_outputs = {**final_outputs, **step_outputs["write_digest"]}

    diag = redact_diag(
        {
            "run_id": run_id,
            "step_keys": list(step_outputs.keys()),
            "duplicated_suppressed": duplicated_suppressed,
            "checkpointed_ai": checkpointed_ai,
            "skipped_dependent": skipped_dependent,
        }
    )

    if checkpointed_ai and not cancelled and blocked_reason not in {
        "delivery_failed",
        "outcome_unknown",
        "ai_evidence_rejected",
    }:
        # Partial offline success: independent work done; AI paused for later resume
        if blocked_reason and "ai_evidence_rejected" in (blocked_reason or ""):
            pass
        else:
            state = "ai_checkpointed"
            store.finish_run(
                run_id,
                state=state,
                outputs=final_outputs if final_outputs else step_outputs,
                error=f"checkpointed:{','.join(checkpointed_ai)}:{blocked_reason}",
            )
            return {
                "ok": False,
                "blocked": True,
                "state": state,
                "blocked_step": checkpointed_ai[0],
                "blocked_reason": blocked_reason or "ai_step_unavailable_or_paused",
                "run_id": run_id,
                "step_outputs": step_outputs,
                "outputs": final_outputs if final_outputs else dict(step_outputs),
                "receipts": store.list_step_receipts(run_id),
                "prior_outputs_preserved": True,
                "duplicated_suppressed": duplicated_suppressed,
                "checkpointed_ai": checkpointed_ai,
                "skipped_dependent": skipped_dependent,
                "independent_work_completed": True,
                "failed_deliveries": store.failed_deliveries(run_id),
                "artifacts_on_disk": _list_artifacts(work_dir),
                "diagnostics": diag,
                "compensation_policy": {
                    "delete_local_draft": compensation_for("write_local_draft"),
                    "retract_received_message": compensation_for("retract_received_message"),
                },
                "ownership": {
                    "workflow_semantics": "freeforge",
                    "scheduling_sessions": "openclaw_not_duplicated",
                },
            }

    if blocked_at or cancelled:
        state = "cancelled" if cancelled else (
            "outcome_unknown" if blocked_reason == "outcome_unknown" else "blocked"
        )
        if blocked_reason == "delivery_failed":
            state = "delivery_failed"
        if (
            (blocked_reason and "ai_evidence_rejected" in blocked_reason)
            or blocked_reason == "plausible_but_unsupported_extracted_value"
        ):
            state = "rejected"
        store.finish_run(
            run_id,
            state=state,
            outputs=final_outputs if final_outputs else step_outputs,
            error=f"{blocked_at}:{blocked_reason}",
        )
        return {
            "ok": False,
            "blocked": True,
            "state": state,
            "blocked_step": blocked_at,
            "blocked_reason": blocked_reason,
            "run_id": run_id,
            "step_outputs": step_outputs,
            "outputs": final_outputs if final_outputs else dict(step_outputs),
            "receipts": store.list_step_receipts(run_id),
            "prior_outputs_preserved": True,
            "duplicated_suppressed": duplicated_suppressed,
            "checkpointed_ai": checkpointed_ai,
            "skipped_dependent": skipped_dependent,
            "failed_deliveries": store.failed_deliveries(run_id),
            "outcome_unknown": blocked_reason == "outcome_unknown",
            "artifacts_on_disk": _list_artifacts(work_dir),
            "diagnostics": diag,
            "compensation_policy": {
                "delete_local_draft": compensation_for("write_local_draft"),
                "retract_received_message": compensation_for("retract_received_message"),
            },
            "ownership": {
                "workflow_semantics": "freeforge",
                "scheduling_sessions": "openclaw_not_duplicated",
            },
        }

    store.finish_run(run_id, state="succeeded", outputs=final_outputs or step_outputs)
    return {
        "ok": True,
        "blocked": False,
        "state": "succeeded",
        "run_id": run_id,
        "step_outputs": step_outputs,
        "outputs": final_outputs or step_outputs,
        "receipts": store.list_step_receipts(run_id),
        "prior_outputs_preserved": True,
        "duplicated_suppressed": duplicated_suppressed,
        "checkpointed_ai": checkpointed_ai,
        "skipped_dependent": skipped_dependent,
        "failed_deliveries": [],
        "artifacts_on_disk": _list_artifacts(work_dir),
        "diagnostics": diag,
        "compensation_policy": {
            "delete_local_draft": compensation_for("write_local_draft"),
            "retract_received_message": compensation_for("retract_received_message"),
        },
        "ownership": {
            "workflow_semantics": "freeforge",
            "scheduling_sessions": "openclaw_not_duplicated",
        },
    }


def _list_artifacts(work_dir: Path) -> list[str]:
    return sorted(
        p.name
        for p in work_dir.iterdir()
        if p.is_file()
        and p.suffix in {".json", ".txt", ".md"}
        and p.name != "receipts.sqlite"
        and not p.name.endswith(".tmp")
    )
