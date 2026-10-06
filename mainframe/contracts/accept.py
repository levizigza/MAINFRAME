"""Acceptance: refactor interface preserve; one focused question; routine start."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mainframe.config import ROOT
from mainframe.contracts.build import build_contract, start_contract, verify_refactor_interface

FIXTURE = ROOT / "docs" / "contracts" / "fixtures"


def run_contracts_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    # --- Refactor preserves declared interface ---
    before = (FIXTURE / "refactor_mod_before.py").read_text(encoding="utf-8")
    after_ok = (FIXTURE / "refactor_mod_after_ok.py").read_text(encoding="utf-8")
    after_bad = (FIXTURE / "refactor_mod_after_break.py").read_text(encoding="utf-8")
    iface = {
        "module_path": "refactor_mod.py",
        "symbols": [
            {"name": "public_api", "kind": "function"},
            {"name": "HELPER_CONST", "kind": "assign"},
        ],
    }
    contract = build_contract(
        "Refactor refactor_mod.py to clarify internals without changing the public API",
        interface=iface,
        scope_hint={"paths": ["refactor_mod.py"]},
    )
    c = contract["contract"]
    checks.append(
        {
            "id": "refactor_contract_has_interface_invariant",
            "ok": (
                contract.get("ok")
                and c.get("kind") == "refactor"
                and c.get("status") == "ready"
                and any(i.get("type") == "preserve_interface" for i in c.get("invariants") or [])
                and "preserve_declared_interface" in (c.get("constraints") or [])
            ),
            "detail": {
                "kind": c.get("kind"),
                "status": c.get("status"),
                "invariants": c.get("invariants"),
                "intent": c.get("intent_natural_language"),
            },
        }
    )
    ok_preserve = verify_refactor_interface(
        interface=iface, before_source=before, after_source=after_ok
    )
    bad_preserve = verify_refactor_interface(
        interface=iface, before_source=before, after_source=after_bad
    )
    checks.append(
        {
            "id": "refactor_preserves_declared_interface",
            "ok": ok_preserve.get("preserved") is True and bad_preserve.get("preserved") is False,
            "detail": {"ok": ok_preserve, "break": bad_preserve},
        }
    )

    # --- Ambiguous → exactly one focused question ---
    amb = build_contract("make it better")
    aq = amb["contract"].get("unresolved_questions") or []
    checks.append(
        {
            "id": "ambiguous_one_focused_question",
            "ok": (
                amb.get("ok")
                and amb["contract"].get("status") == "needs_clarification"
                and amb.get("ask_count") == 1
                and len(aq) == 1
                and aq[0].get("focused") is True
            ),
            "detail": {"ask_count": amb.get("ask_count"), "questions": aq},
        }
    )

    # --- Routine known workflow starts without clarification ---
    ready = build_contract("run workspace checksum")
    started = start_contract(ready["contract"])
    checks.append(
        {
            "id": "routine_workflow_starts_without_clarification",
            "ok": (
                ready["contract"].get("status") == "ready"
                and ready["contract"].get("workflow_id") == "workspace_checksum"
                and len(ready["contract"].get("unresolved_questions") or []) == 0
                and started.get("started") is True
                and started.get("without_clarification") is True
                and started.get("ok") is True
                and bool((started.get("output") or {}).get("sha256"))
            ),
            "detail": {
                "workflow_id": ready["contract"].get("workflow_id"),
                "assumptions": ready["contract"].get("assumptions"),
                "started": started.get("started"),
                "assertions": started.get("assertions"),
            },
        }
    )

    # Block start when clarification needed
    blocked = start_contract(amb["contract"])
    checks.append(
        {
            "id": "ambiguous_does_not_start",
            "ok": blocked.get("started") is False and blocked.get("ask_count") == 1,
            "detail": blocked,
        }
    )

    # No separate model label call
    checks.append(
        {
            "id": "no_separate_model_label_call",
            "ok": (
                contract.get("separate_label_call") is False
                and amb.get("separate_label_call") is False
                and ready.get("model_service_used") is False
                and started.get("model_service_used") is False
            ),
            "detail": {
                "deterministic_classification": ready.get("deterministic_classification"),
            },
        }
    )

    # Natural-language intent retained
    checks.append(
        {
            "id": "natural_language_intent_retained",
            "ok": bool(c.get("intent_natural_language"))
            and "Refactor" in c.get("intent_natural_language", ""),
            "detail": c.get("intent_natural_language"),
        }
    )

    passed = sum(1 for x in checks if x["ok"])
    failed = len(checks) - passed
    return {
        "ok": failed == 0,
        "passed": passed,
        "failed": failed,
        "checks": checks,
        "model_service_used": False,
        "separate_label_call": False,
    }
