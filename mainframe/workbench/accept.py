"""Acceptance for FreeForge Workbench Python bridge + overlay pin (honest gates)."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from mainframe.codingloop.propose import propose_edits
from mainframe.config import ROOT
from mainframe.workbench.agent import (
    agent_turn,
    apply_or_reject,
    cancel,
    context_chips,
    iter_agent_events,
    propose_from_workspace,
    resume,
    tool_read,
)
from mainframe.workbench.fitness import mode_b_fitness_report
from mainframe.workbench.onboarding import onboarding_guide
from mainframe.workbench.status import WORKBENCH_ROOT, workbench_status


def run_workbench_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    status = workbench_status()
    checks.append(
        {
            "id": "product_truth_positioning",
            "ok": bool(
                status.get("ok")
                and "VS Code-class shell" in (status.get("positioning") or "")
                and status.get("deterministic_core_without_ai") is True
                and status.get("claims", {}).get("exceeds_cursor") == "unknown"
            ),
            "detail": {
                "product": status.get("product"),
                "claims": status.get("claims"),
                "ai_status": status.get("ai", {}).get("status"),
            },
        }
    )

    fitness = mode_b_fitness_report()
    checks.append(
        {
            "id": "mode_b_fitness_report",
            "ok": bool(
                fitness.get("ok")
                and fitness.get("mode_label") == "Mode B"
                and fitness.get("auto_download") is False
                and isinstance(fitness.get("user_pull_steps"), list)
                and fitness.get("competitor_cursor_e2e") == "unknown"
            ),
            "detail": {
                "recommended_ids": fitness.get("recommended_ids"),
                "probe": fitness.get("provider", {}).get("probe_status"),
                "live_coding_quality": fitness.get("live_coding_quality"),
            },
        }
    )

    onboard = onboarding_guide()
    checks.append(
        {
            "id": "onboarding_guide",
            "ok": bool(
                onboard.get("ok")
                and onboard.get("honesty", {}).get("exceeds_cursor") == "unknown"
                and any(s.get("id") == "optional_ollama" for s in onboard.get("steps") or [])
            ),
            "detail": {"step_count": len(onboard.get("steps") or []), "ai_paused": onboard.get("ai_paused")},
        }
    )

    pin_path = WORKBENCH_ROOT / "PINS.json"
    overlay = WORKBENCH_ROOT / "overlay" / "src" / "vs" / "workbench" / "contrib" / "freeforge"
    notice = WORKBENCH_ROOT / "ThirdPartyNotices.txt"
    about = overlay / "browser" / "freeforge.contribution.ts"
    checks.append(
        {
            "id": "workbench_pin_and_overlay",
            "ok": bool(
                pin_path.is_file()
                and overlay.is_dir()
                and notice.is_file()
                and about.is_file()
            ),
            "detail": {
                "pin_present": pin_path.is_file(),
                "overlay_present": overlay.is_dir(),
                "notice_present": notice.is_file(),
                "contribution_present": about.is_file(),
                "windows_electron_build": "documented_not_tested_on_this_linux_host",
            },
        }
    )

    if pin_path.is_file():
        pin = json.loads(pin_path.read_text(encoding="utf-8"))
        checks.append(
            {
                "id": "vscode_pin_fields",
                "ok": bool(
                    pin.get("upstream") == "microsoft/vscode"
                    and pin.get("tag")
                    and pin.get("electron")
                    and pin.get("node")
                ),
                "detail": {
                    "tag": pin.get("tag"),
                    "electron": pin.get("electron"),
                    "node": pin.get("node"),
                },
            }
        )

    ide_report = ROOT / "docs" / "eval" / "ide" / "REPORT.md"
    ide_json = ROOT / "docs" / "eval" / "ide" / "metrics.json"
    checks.append(
        {
            "id": "ide_eval_evidence_gate",
            "ok": bool(ide_report.is_file() and ide_json.is_file()),
            "detail": {"report": str(ide_report), "metrics": str(ide_json)},
        }
    )
    if ide_json.is_file():
        metrics = json.loads(ide_json.read_text(encoding="utf-8"))
        checks.append(
            {
                "id": "no_false_cursor_claims",
                "ok": bool(
                    metrics.get("vs_cursor") == "unknown"
                    and metrics.get("agent_task_success_live") == "unknown"
                ),
                "detail": {
                    "vs_cursor": metrics.get("vs_cursor"),
                    "live": metrics.get("agent_task_success_live"),
                },
            }
        )

    # Fixture propose + agent turn (deterministic; AI may be paused)
    fixture = ROOT / "docs" / "codingloop" / "fixtures" / "multi_repair"
    with tempfile.TemporaryDirectory(prefix="mf_wb_") as tmp:
        ws = Path(tmp) / "ws"
        shutil.copytree(fixture, ws)
        prop = propose_edits(ws, hypothesis="fix multi-file bugs", prefer_model=False)
        checks.append(
            {
                "id": "deterministic_propose_replaces_fixture_only_path",
                "ok": bool(
                    prop.get("ok")
                    and len(prop.get("edits") or []) >= 2
                    and prop.get("proposer") == "deterministic_fixture"
                ),
                "detail": {
                    "proposer": prop.get("proposer"),
                    "edits": len(prop.get("edits") or []),
                },
            }
        )

        turn = agent_turn(
            message="Repair mathutil and greeter fixtures",
            workspace=ws,
            selection={
                "path": "mathutil.py",
                "text": (ws / "mathutil.py").read_text(encoding="utf-8"),
                "start_line": 1,
                "end_line": 4,
            },
            diagnostics=[{"path": "mathutil.py", "severity": "error", "message": "wrong op"}],
            open_files=["mathutil.py", "greeter.py"],
            active_file="mathutil.py",
            auto_propose=True,
        )
        tid = turn.get("task_id")
        chips = context_chips(tid) if tid else {"ok": False}
        events = list(iter_agent_events(turn))
        checks.append(
            {
                "id": "agent_turn_context_chips_and_stream_events",
                "ok": bool(
                    turn.get("ok")
                    and tid
                    and chips.get("ok")
                    and any(c.get("kind") == "selection" for c in chips.get("chips") or [])
                    and any(e.get("type") == "assistant_delta" for e in events)
                    and turn.get("ai", {}).get("status") in ("paused", "available")
                ),
                "detail": {
                    "task_id": tid,
                    "ai": turn.get("ai", {}).get("status"),
                    "chip_kinds": [c.get("kind") for c in chips.get("chips") or []],
                    "event_types": [e.get("type") for e in events[:12]],
                    "proposal_edits": len((turn.get("proposal") or {}).get("edits") or []),
                },
            }
        )

        # Reviewable apply / reject
        if tid and (turn.get("proposal") or {}).get("edits"):
            rej = apply_or_reject(tid, accept=False)
            # Re-propose and apply
            again = propose_from_workspace(tid, workspace=ws, prefer_model=False)
            applied = apply_or_reject(tid, accept=True) if again.get("edits") else {"ok": False}
            math_ok = "return a + b" in (ws / "mathutil.py").read_text(encoding="utf-8")
            checks.append(
                {
                    "id": "apply_reject_no_silent_overwrite",
                    "ok": bool(
                        rej.get("rejected")
                        and applied.get("ok")
                        and math_ok
                    ),
                    "detail": {"reject": rej, "apply_ok": applied.get("ok"), "math_ok": math_ok},
                }
            )
        else:
            checks.append(
                {
                    "id": "apply_reject_no_silent_overwrite",
                    "ok": False,
                    "detail": {"error": "no_proposal_edits", "turn_ok": turn.get("ok")},
                }
            )

        if tid:
            can = cancel(tid)
            res = resume(tid)
            checks.append(
                {
                    "id": "cancel_resume_bridge",
                    "ok": bool(can.get("ok") or can.get("cancelled")),
                    "detail": {"cancel": can.get("ok"), "resume_after_cancel": res},
                }
            )

        read = tool_read(ws / "mathutil.py")
        checks.append(
            {
                "id": "tool_read",
                "ok": bool(read.get("ok") and "def" in (read.get("text") or "")),
                "detail": {"path": read.get("path")},
            }
        )

    docs_wb = ROOT / "docs" / "WORKBENCH.md"
    checks.append(
        {
            "id": "workbench_docs",
            "ok": docs_wb.is_file()
            and "CLI alone is **not** an IDE" in docs_wb.read_text(encoding="utf-8"),
            "detail": str(docs_wb),
        }
    )

    app_wb = ROOT / "dist" / "application" / "workbench"
    # Ensure application surface helper can stage pointer (created by surfaces build or accept staging)
    from mainframe.surfaces.application import stage_workbench_artifact

    staged = stage_workbench_artifact()
    checks.append(
        {
            "id": "application_workbench_artifact",
            "ok": bool(staged.get("ok") and (Path(staged["dest"]) / "README.md").is_file()),
            "detail": staged,
        }
    )

    ok = all(c.get("ok") for c in checks)
    live_note = (
        "Live modeleval/codingbench --live not run — Ollama unavailable or not fitted on this host."
        if status.get("ai", {}).get("status") != "available"
        else "Ollama available — run modeleval/codingbench --live separately; do not invent cells."
    )
    return {
        "ok": ok,
        "passed": sum(1 for c in checks if c.get("ok")),
        "total": len(checks),
        "checks": checks,
        "live_eval": "skipped_or_unknown",
        "live_note": live_note,
        "windows_electron_build": "documented_not_tested_on_this_host",
        "artifact_dir": str(app_wb),
    }
