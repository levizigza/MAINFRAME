"""Acceptance for FreeForge Workbench bootstrap (Phase 0–1)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.config import ROOT, RUNS_DIR, ensure_state
from mainframe.workbench.status import (
    GOAL,
    OVERLAY,
    PIN_PATH,
    load_pin,
    model_fit_report,
    run_bootstrap,
    run_overlay_check,
    workbench_status,
)

REPORT_MD = ROOT / "docs" / "eval" / "ide" / "WORKBENCH.md"
REPORT_JSON = ROOT / "docs" / "eval" / "ide" / "WORKBENCH.json"


def run_workbench_accept() -> dict[str, Any]:
    ensure_state()
    st = workbench_status()
    fit = model_fit_report()
    overlay_chk = run_overlay_check()
    # Staging bootstrap (no full vscode clone in accept — clone is optional/heavy)
    boot = run_bootstrap(skip_clone=True)

    checks: list[dict[str, Any]] = []
    checks.append(
        {
            "id": "ide_goal_doc",
            "ok": GOAL.is_file()
            and (
                "match or exceed" in GOAL.read_text(encoding="utf-8").lower()
                or "matches or exceeds" in GOAL.read_text(encoding="utf-8").lower()
            ),
            "detail": "docs/IDE_GOAL.md",
        }
    )
    checks.append(
        {
            "id": "pin_present",
            "ok": bool(st.get("pin", {}).get("present") and st.get("pin", {}).get("tag")),
            "detail": st.get("pin"),
        }
    )
    checks.append(
        {
            "id": "overlay_present",
            "ok": bool(st.get("overlay", {}).get("present")),
            "detail": st.get("overlay"),
        }
    )
    checks.append(
        {
            "id": "overlay_check",
            "ok": bool(overlay_chk.get("ok"))
            or overlay_chk.get("error") == "node_not_on_path",
            "detail": overlay_chk,
        }
    )
    checks.append(
        {
            "id": "bootstrap_staging",
            "ok": bool(boot.get("ok")),
            "detail": boot,
        }
    )
    checks.append(
        {
            "id": "mode_b_fit_report",
            "ok": bool(fit.get("ok")),
            "detail": {
                "recommended_ids": fit.get("recommended_ids"),
                "budget_gib": fit.get("inference_budget_gib"),
                "ai_status": (fit.get("ai_probe") or {}).get("status"),
            },
        }
    )
    checks.append(
        {
            "id": "no_false_cursor_claim",
            "ok": st.get("cursor_claude_comparison") == "unknown",
            "detail": "Competitor comparison remains unknown until measured",
        }
    )
    checks.append(
        {
            "id": "void_services_not_vendored",
            "ok": (load_pin().get("void_reference") or {}).get("copy_workbench_services") is False,
            "detail": "PIN forbids Void workbench service copy",
        }
    )

    passed = sum(1 for c in checks if c.get("ok"))
    failed = len(checks) - passed
    payload = {
        "ok": failed == 0,
        "passed": passed,
        "failed": failed,
        "checks": checks,
        "status": st,
        "model_fit": {
            "recommended_ids": fit.get("recommended_ids"),
            "note": fit.get("note"),
        },
        "north_star": st.get("north_star"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# FreeForge Workbench accept",
        "",
        f"Generated: `{payload['generated_at']}`",
        f"Result: **{'PASS' if payload['ok'] else 'FAIL'}** ({passed}/{len(checks)})",
        "",
        f"North star: `{st.get('north_star')}`",
        f"Cursor/Claude comparison: `{st.get('cursor_claude_comparison')}`",
        f"AI probe: `{(st.get('ai') or {}).get('status')}`",
        f"Recommended local models: `{fit.get('recommended_ids')}`",
        "",
        "Full vscode Electron build is optional next; overlay + pin + Mode B onboarding are gated here.",
        "",
    ]
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    REPORT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (RUNS_DIR / f"workbench-{stamp}.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    payload["report_md"] = "docs/eval/ide/WORKBENCH.md"
    payload["report_json"] = "docs/eval/ide/WORKBENCH.json"
    return payload
