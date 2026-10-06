"""Build and start task contracts — deterministic first; no separate model label call."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from mainframe.contracts.ask import decide_questions_and_assumptions
from mainframe.contracts.assertions import run_assertions
from mainframe.contracts.classify import classify_request
from mainframe.contracts.schema import validate_against_schema
from mainframe.contracts.types import TaskContract
from mainframe.contracts.workflows import get_workflow, match_workflow
from mainframe.cost_gate import authorize


def build_contract(
    request_text: str,
    *,
    scope_hint: dict[str, Any] | None = None,
    interface: dict[str, Any] | None = None,
    model_interpretation: dict[str, Any] | None = None,
    already_needed_ai_turn: bool = False,
) -> dict[str, Any]:
    """
    Build a task contract from natural language.

    ``model_interpretation`` may refine wording only when provided as part of an
    already-needed AI turn (``already_needed_ai_turn=True``). Classification itself
    stays deterministic — never spends a separate model call just to label.
    """
    gate = authorize("tool", "local.task_contract", local=True)
    if not gate.allowed:
        return {"ok": False, "cost_gate": gate.to_dict()}

    text = (request_text or "").strip()
    classification = classify_request(text)
    workflow_id = match_workflow(text)
    kind = classification["kind"]
    if workflow_id:
        wf = get_workflow(workflow_id) or {}
        kind = wf.get("kind") or kind

    # Optional model polish — only if caller already needed an AI turn
    model_used = False
    separate_label = False
    desired = _default_desired(kind, text)
    if model_interpretation and already_needed_ai_turn:
        model_used = True
        desired = str(model_interpretation.get("desired_behavior") or desired)
        # Model must not override deterministic kind unless unknown
        if kind == "unknown" and model_interpretation.get("kind") in {
            "explanation",
            "repair",
            "feature",
            "refactor",
            "ui",
            "automation",
        }:
            kind = model_interpretation["kind"]
    elif model_interpretation and not already_needed_ai_turn:
        # Ignore — would be a separate label spend
        separate_label = False
        model_interpretation = None

    qa = decide_questions_and_assumptions(
        text, kind=kind, workflow_id=workflow_id, classification=classification
    )

    scope = dict(scope_hint or {})
    if interface:
        scope["interface"] = interface
    # Extract .py paths mentioned
    for m in re.finditer(r"([\w./\\-]+\.py)", text):
        scope.setdefault("paths", []).append(m.group(1).replace("\\", "/"))

    constraints = ["local_free_only", "no_paid_services"]
    invariants: list[dict[str, Any]] = []
    acceptance: list[dict[str, Any]] = []
    side_effects = ["write_workspace_files_in_scope"]
    exec_assertions: list[dict[str, Any]] = []
    input_schema = None
    output_schema = None

    if workflow_id:
        wf = get_workflow(workflow_id) or {}
        desired = wf.get("desired_behavior") or desired
        scope = {**wf.get("scope", {}), **scope}
        constraints = list(wf.get("constraints") or constraints)
        invariants = list(wf.get("invariants") or [])
        acceptance = list(wf.get("acceptance_checks") or [])
        side_effects = list(wf.get("permitted_side_effects") or ["none"])
        exec_assertions = list(wf.get("executable_assertions") or [])
        input_schema = wf.get("input_schema")
        output_schema = wf.get("output_schema")

    if kind == "refactor":
        constraints.append("preserve_declared_interface")
        iface = interface or scope.get("interface")
        if iface:
            inv = {
                "id": "interface_stable",
                "type": "preserve_interface",
                "interface": iface,
            }
            invariants.append(inv)
            exec_assertions.append(
                {"id": "preserve_interface", "type": "preserve_interface", "interface": iface}
            )
            acceptance.append(
                {
                    "id": "interface_preserved",
                    "type": "preserve_interface",
                    "interface": iface,
                }
            )
        side_effects = ["edit_files_in_scope", "no_public_api_break"]
    elif kind == "explanation":
        side_effects = ["none"]
        constraints.append("read_only")
    elif kind == "repair":
        constraints.append("minimal_diff")
        acceptance.append({"id": "failure_resolved", "type": "manual_or_test"})
    elif kind == "ui":
        side_effects = ["edit_ui_assets_in_scope"]
    elif kind == "automation":
        side_effects = side_effects if workflow_id else ["run_local_commands", "write_run_logs"]

    if not acceptance and kind != "unknown":
        acceptance.append(
            {
                "id": "behavior_matches_desired",
                "type": "review",
                "text": desired,
            }
        )

    contract = TaskContract(
        intent_natural_language=text,
        kind=kind,  # type: ignore[arg-type]
        desired_behavior=desired,
        scope=scope,
        constraints=constraints,
        invariants=invariants,
        acceptance_checks=acceptance,
        permitted_side_effects=side_effects,
        unresolved_questions=qa["unresolved_questions"],
        assumptions=qa["assumptions"],
        classification=classification,
        workflow_id=workflow_id,
        input_schema=input_schema,
        output_schema=output_schema,
        executable_assertions=exec_assertions,
        status=qa["status"],
        model_service_used=model_used,
        separate_label_call=separate_label,
    )
    return {
        "ok": True,
        "contract": contract.to_dict(),
        "ask_count": qa["ask_count"],
        "model_service_used": model_used,
        "separate_label_call": False,
        "deterministic_classification": True,
    }


def start_contract(
    contract: dict[str, Any] | None = None,
    *,
    request_text: str | None = None,
    inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Start a ready contract / known workflow: validate inputs, run automation if any,
    execute assertions. Does not re-ask when status is ready.
    """
    gate = authorize("tool", "local.task_contract_start", local=True)
    if not gate.allowed:
        return {"ok": False, "cost_gate": gate.to_dict()}

    if contract is None:
        built = build_contract(request_text or "")
        if not built.get("ok"):
            return built
        contract = built["contract"]

    if contract.get("status") == "needs_clarification":
        return {
            "ok": False,
            "started": False,
            "reason": "needs_clarification",
            "questions": contract.get("unresolved_questions") or [],
            "ask_count": len(contract.get("unresolved_questions") or []),
            "model_service_used": False,
        }

    inputs = dict(inputs or {})
    wf_id = contract.get("workflow_id")
    if wf_id:
        from mainframe.contracts.workflows import get_workflow
        from mainframe.automation import run_task

        wf = get_workflow(wf_id) or {}
        defaults = dict(wf.get("default_inputs") or {})
        defaults.update(inputs)
        inputs = defaults
        vin = validate_against_schema(inputs, contract.get("input_schema"))
        if not vin["ok"]:
            return {
                "ok": False,
                "started": False,
                "reason": "input_schema_invalid",
                "errors": vin["errors"],
            }
        task = wf.get("automation_task")
        result = run_task(task, inputs) if task else None
        output = result.output if result and result.ok else {}
        if result and not result.ok:
            return {
                "ok": False,
                "started": True,
                "workflow_id": wf_id,
                "error": result.error,
                "model_service_used": False,
            }
        vout = validate_against_schema(output, contract.get("output_schema"))
        asserts = run_assertions(contract.get("executable_assertions") or [], output=output)
        return {
            "ok": vout["ok"] and asserts["ok"],
            "started": True,
            "without_clarification": True,
            "workflow_id": wf_id,
            "inputs": inputs,
            "output": output,
            "input_validation": vin,
            "output_validation": vout,
            "assertions": asserts,
            "intent_natural_language": contract.get("intent_natural_language"),
            "model_service_used": False,
            "separate_label_call": False,
        }

    # Non-workflow: contract is ready to execute by agent — no clarification loop
    return {
        "ok": True,
        "started": True,
        "without_clarification": True,
        "contract": contract,
        "model_service_used": False,
        "separate_label_call": False,
    }


def verify_refactor_interface(
    *,
    interface: dict[str, Any],
    before_source: str,
    after_source: str,
    root: Path | None = None,
) -> dict[str, Any]:
    """Acceptance helper: refactor must preserve declared interface."""
    asserts = run_assertions(
        [{"id": "preserve_interface", "type": "preserve_interface", "interface": interface}],
        context={
            "before_source": before_source,
            "after_source": after_source,
            "root": str(root or Path(".")),
            "interface": interface,
        },
    )
    return {
        "ok": asserts["ok"],
        "preserved": asserts["ok"],
        "assertions": asserts,
        "model_service_used": False,
    }


def _default_desired(kind: str, text: str) -> str:
    if kind == "refactor":
        return f"Refactor as requested while preserving declared interfaces: {text}"
    if kind == "repair":
        return f"Repair the stated defect: {text}"
    if kind == "feature":
        return f"Deliver the requested feature: {text}"
    if kind == "ui":
        return f"Update UI as requested: {text}"
    if kind == "automation":
        return f"Automate as requested: {text}"
    if kind == "explanation":
        return f"Explain: {text}"
    return text
