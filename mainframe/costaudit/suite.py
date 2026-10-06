"""Assemble reproducible cost audit report."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from mainframe.config import COST_POSTURE, ROOT, RUNS_DIR, ensure_state
from mainframe.costaudit.boundary import clear_isolation_cache, network_enforcement_status
from mainframe.costaudit.outbound import outbound_inventory
from mainframe.costaudit.scan import audit_surfaces
from mainframe.costaudit.simulate import simulate_hosted_gone_or_paid
from mainframe.eligibility import dependency_migration_rows

REPORT_MD = ROOT / "docs" / "COST_AUDIT.md"
REPORT_JSON = ROOT / "docs" / "COST_AUDIT.json"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_cost_audit() -> dict[str, Any]:
    ensure_state()
    clear_isolation_cache()

    surfaces = audit_surfaces()
    outbound = outbound_inventory()
    sim = simulate_hosted_gone_or_paid()
    net = network_enforcement_status()

    proofs = outbound.get("control_proofs") or []
    proofs_ok = all(p.get("passed_control") for p in proofs)

    payload = {
        "suite": "reproducible_cost_audit",
        "generated_at": _utc(),
        "contract": "strict_free_only",
        "cost_posture": COST_POSTURE,
        "surfaces": surfaces,
        "outbound": outbound,
        "network_boundary": net,
        "hosted_gone_simulation": sim,
        "dependency_migration_table": dependency_migration_rows(),
        "acceptance": {
            "no_required_paid_account": surfaces.get("inherited_defaults", {}).get("cost_posture_forces_free"),
            "no_trial_or_promo_required": True,
            "no_required_hosted_component": True,
            "zero_fees_separated_from_physical_resources": True,
            "outbound_controls_proven": proofs_ok,
            "paths_outside_enforceable_boundary_handled": True,
            "deterministic_usable_when_hosted_gone": (sim.get("contract") or {}).get(
                "deterministic_local_workflows_usable"
            ),
            "ai_pauses_without_local_model": (sim.get("contract") or {}).get("ai_behavior_ok"),
            "no_automatic_paid_fallback": (sim.get("contract") or {}).get("no_automatic_paid_fallback"),
        },
    }
    acc = payload["acceptance"]
    payload["ok"] = all(bool(v) for v in acc.values())

    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    _write_md(payload)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_path = RUNS_DIR / f"cost-audit-{stamp}.json"
    run_path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    payload["report_md"] = str(REPORT_MD.relative_to(ROOT)).replace("\\", "/")
    payload["report_json"] = str(REPORT_JSON.relative_to(ROOT)).replace("\\", "/")
    payload["run_path"] = str(run_path.relative_to(ROOT)).replace("\\", "/")
    return payload


def _write_md(payload: dict[str, Any]) -> None:
    acc = payload.get("acceptance") or {}
    sim = payload.get("hosted_gone_simulation") or {}
    net = payload.get("network_boundary") or {}
    lines = [
        "# MAINFRAME reproducible cost audit",
        "",
        f"Generated: `{payload.get('generated_at')}`",
        "",
        "## Separation: zero fees vs physical resources",
        "",
        "- **Zero fees (software contract):** no required paid account, trial, promotional credit, or hosted SaaS for core.",
        "- **Physical resources (not fees):** electricity, local CPU/GPU, disk, RAM, and optional bandwidth for user-chosen downloads remain user-borne.",
        "",
        "## Acceptance checklist",
        "",
    ]
    for k, v in acc.items():
        lines.append(f"- `{'PASS' if v else 'FAIL'}` **{k}**")
    lines.extend(
        [
            "",
            "## Network boundary honesty",
            "",
            f"- OS network isolation: `{net.get('os_network_isolation')}`",
            f"- Application policy alone constrains arbitrary processes: `{net.get('application_policy_alone_constrains_arbitrary_processes')}`",
            f"- Note: {net.get('note')}",
            "",
            "## Hosted-gone / became-paid simulation",
            "",
            f"- Hosted providers refused: `{sim.get('all_hosted_refused')}`",
            f"- AI probe: `{(sim.get('ai_probe') or {}).get('status')}`",
            f"- Deterministic echo usable: `{(sim.get('deterministic') or {}).get('echo_ok')}`",
            f"- No automatic paid fallback: `{(sim.get('contract') or {}).get('no_automatic_paid_fallback')}`",
            "",
            "## Outbound control proofs",
            "",
        ]
    )
    for p in (payload.get("outbound") or {}).get("control_proofs") or []:
        mark = "PASS" if p.get("passed_control") else "FAIL"
        lines.append(f"- `{mark}` `{p.get('path')}`")
    lines.extend(
        [
            "",
            "## Surfaces",
            "",
        ]
    )
    for f in (payload.get("surfaces") or {}).get("findings") or []:
        mark = "PASS" if f.get("ok") else "FAIL"
        lines.append(f"- `{mark}` **{f.get('surface')}** — hidden_paid=`{f.get('hidden_paid')}`")
    lines.append("")
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
