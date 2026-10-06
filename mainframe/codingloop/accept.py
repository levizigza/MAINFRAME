"""Acceptance: multi-file e2e, impossible stop, resume after interrupt."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from mainframe.codingloop.lifecycle import LIFECYCLE_PHASES, engine_binding
from mainframe.codingloop.loop import load_checkpoint, run_coding_loop
from mainframe.config import ROOT

FIX_MULTI = ROOT / "docs" / "codingloop" / "fixtures" / "multi_repair"
FIX_IMP = ROOT / "docs" / "codingloop" / "fixtures" / "impossible"
WORK = ROOT / ".mainframe" / "codingloop_work"


def _prep(src: Path, name: str) -> Path:
    dest = WORK / name
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(src, dest)
    return dest


def run_codingloop_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    eng = engine_binding()
    checks.append(
        {
            "id": "reuses_selected_engine_lifecycle",
            "ok": (
                eng["selected_engine"] == "openclaw_embedded_agent_runtime"
                and eng["nested_independent_supervisor"] is False
                and list(LIFECYCLE_PHASES)
                == ["reproduce", "investigate", "propose", "apply", "check", "report"]
            ),
            "detail": eng,
        }
    )

    # --- Multi-file e2e ---
    multi = _prep(FIX_MULTI, "multi_repair")
    report = run_coding_loop(
        multi,
        goal=(
            "Repair mathutil.add and greeter.greet so tests pass: "
            "add returns sum; greet joins with '; '."
        ),
        max_attempts=3,
    )
    checks.append(
        {
            "id": "multi_file_fixture_e2e",
            "ok": (
                report.get("ok") is True
                and report.get("applied") is True
                and report.get("verified") is True
                and report.get("status_label") == "implemented_and_verified"
                and report.get("proposal_only") is False
                and bool(report.get("actual_diffs"))
                and report.get("checks") is not None
                and report.get("claims", {}).get("generated_proposal_described_as_implemented") is False
                and report.get("claims", {}).get("generated_proposal_described_as_verified") is False
            ),
            "detail": {
                "status_label": report.get("status_label"),
                "stop": report.get("stop_reason"),
                "diffs_n": len(report.get("actual_diffs") or []),
                "phases": [p.get("phase") for p in report.get("phase_log") or []],
            },
        }
    )

    # --- Impossible stops without claiming verified fix ---
    imp = _prep(FIX_IMP, "impossible")
    impossible = run_coding_loop(
        imp,
        goal="Make oracle.self_check pass by decrypting with external oracle.",
        max_attempts=2,
    )
    checks.append(
        {
            "id": "impossible_task_stops",
            "ok": (
                impossible.get("ok") is False
                and impossible.get("verified") is False
                and impossible.get("applied") is False
                and impossible.get("stop_reason") == "impossible_unavailable_dependency"
                and (impossible.get("proposal") or {}).get("impossible") is True
                and impossible.get("status_label") == "proposal_not_implemented"
            ),
            "detail": {
                "stop": impossible.get("stop_reason"),
                "status_label": impossible.get("status_label"),
                "proposal": impossible.get("proposal"),
            },
        }
    )

    # --- Resume after interruption ---
    multi2 = _prep(FIX_MULTI, "multi_resume")
    interrupted = run_coding_loop(
        multi2,
        goal="Repair mathutil and greeter for tests.",
        interrupt_after_phase="investigate",
    )
    cid = interrupted.get("resume_checkpoint_id")
    loaded = load_checkpoint(str(cid)) if cid else None
    resumed = run_coding_loop(
        multi2,
        goal="Repair mathutil and greeter for tests.",
        resume_from=loaded,
    )
    checks.append(
        {
            "id": "resume_after_interruption",
            "ok": (
                interrupted.get("interrupted") is True
                and interrupted.get("applied") is False
                and loaded is not None
                and resumed.get("ok") is True
                and resumed.get("verified") is True
                and resumed.get("resumed") is True
            ),
            "detail": {
                "interrupted_phase": interrupted.get("phase"),
                "checkpoint": cid,
                "resumed_ok": resumed.get("ok"),
                "resumed_status": resumed.get("status_label"),
            },
        }
    )

    # --- Proposal honesty on interrupt before apply ---
    multi3 = _prep(FIX_MULTI, "multi_interrupt_apply")
    before_apply = run_coding_loop(
        multi3,
        goal="Repair mathutil and greeter.",
        interrupt_after_phase="apply",
    )
    checks.append(
        {
            "id": "interrupt_before_apply_not_claimed_implemented",
            "ok": (
                before_apply.get("interrupted") is True
                and before_apply.get("applied") is False
                and before_apply.get("verified") is False
                and before_apply.get("proposal_only") is True
            ),
            "detail": before_apply,
        }
    )

    passed = sum(1 for c in checks if c["ok"])
    failed = len(checks) - passed
    return {"ok": failed == 0, "passed": passed, "failed": failed, "checks": checks}
