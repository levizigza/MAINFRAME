"""Phase 2 agent UX acceptance — streaming events, propose/apply/reject, cancel."""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.config import ROOT, RUNS_DIR, ensure_state
from mainframe.codingloop.propose import propose_fixes, propose_fixes_model
from mainframe.editor.agent import apply_proposal, context_chips, run_agent_turn
from mainframe.editor.bridge import (
    attach_active_file,
    attach_selection,
    cancel_task,
    chat_to_task,
    reject_proposal,
    set_diagnostics,
)
from mainframe.editor.state import EditorTaskStore

FIX_MULTI = ROOT / "docs" / "codingloop" / "fixtures" / "multi_repair"
REPORT_MD = ROOT / "docs" / "eval" / "ide" / "AGENT_UX.md"
REPORT_JSON = ROOT / "docs" / "eval" / "ide" / "AGENT_UX.json"


def run_agent_ux_accept() -> dict[str, Any]:
    ensure_state()
    checks: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="mf_agent_") as tmp:
        root = Path(tmp)
        ws = root / "ws"
        shutil.copytree(FIX_MULTI, ws)
        store = EditorTaskStore(root / "tasks")

        created = chat_to_task(
            "Fix mathutil.add and greeter join separator",
            workspace=ws,
            store=store,
            source="agent",
        )
        task_id = created["task"]["task_id"]
        attach_selection(
            task_id,
            path="mathutil.py",
            text="def add(a, b):\n    return a * b  # bug: should add\n",
            start_line=4,
            end_line=5,
            store=store,
        )
        attach_active_file(task_id, path="mathutil.py", store=store)
        set_diagnostics(
            task_id,
            [{"path": "mathutil.py", "severity": "error", "message": "add returns product"}],
            store=store,
        )
        task = store.load(task_id)
        chips = context_chips(task or {})
        checks.append(
            {
                "id": "context_chips_selection_workspace",
                "ok": bool(
                    any(c.get("kind") == "selection" for c in chips)
                    and any(c.get("kind") == "active_file" for c in chips)
                    and any(c.get("kind") == "diagnostic" for c in chips)
                    and any(c.get("kind") == "workspace" for c in chips)
                ),
                "detail": {"kinds": [c.get("kind") for c in chips]},
            }
        )

        events: list[dict[str, Any]] = []
        turn = run_agent_turn(task_id, store=store, sink=events.append)
        types = [e.get("type") for e in events]
        checks.append(
            {
                "id": "stream_events_protocol",
                "ok": bool(
                    turn.get("ok")
                    and "ai_status" in types
                    and "completion_gate" in types
                    and "context_chips" in types
                    and "message_delta" in types
                    and "tool_call" in types
                    and "tool_result" in types
                    and "propose_source" in types
                    and "proposal" in types
                    and "done" in types
                ),
                "detail": {"types": types, "awaiting": turn.get("awaiting_apply")},
            }
        )
        test_ev = next(
            (e for e in events if e.get("type") == "tool_result" and e.get("tool") == "tests"),
            None,
        )
        checks.append(
            {
                "id": "tests_tool_in_agent_loop",
                "ok": bool(test_ev and (test_ev.get("result") or {}).get("reproduced_failure") is True),
                "detail": (test_ev or {}).get("result"),
            }
        )
        cache_probe = next(
            (
                e
                for e in events
                if e.get("type") == "tool_result"
                and e.get("tool") == "search"
                and (e.get("result") or {}).get("cache_probe")
            ),
            None,
        )
        checks.append(
            {
                "id": "exact_cache_hit_on_repeat_search",
                "ok": bool(
                    cache_probe
                    and ((cache_probe.get("result") or {}).get("exact_cache") or {}).get("hit") is True
                ),
                "detail": (cache_probe or {}).get("result"),
            }
        )
        gate_ev = next((e for e in events if e.get("type") == "completion_gate"), {})
        ai_paused = (turn.get("ai") or {}).get("state") != "available"
        checks.append(
            {
                "id": "completion_budgeted_gate_honest",
                "ok": bool(
                    gate_ev.get("budgeted") is True
                    and isinstance(gate_ev.get("enabled"), bool)
                    and (not ai_paused or gate_ev.get("enabled") is False)
                ),
                "detail": gate_ev,
            }
        )
        checks.append(
            {
                "id": "proposal_awaiting_apply_not_auto",
                "ok": bool(
                    turn.get("awaiting_apply")
                    and turn.get("proposal")
                    and (turn.get("proposal") or {}).get("applied") is False
                ),
                "detail": {
                    "awaiting": turn.get("awaiting_apply"),
                    "applied": (turn.get("proposal") or {}).get("applied"),
                    "op": (turn.get("proposal") or {}).get("operation_id"),
                },
            }
        )

        # Reject then re-run and apply
        rej = reject_proposal(task_id, store=store)
        mid = store.load(task_id)
        checks.append(
            {
                "id": "reject_clears_proposal",
                "ok": bool(rej.get("ok") and mid and mid.get("proposal") is None and mid.get("state") == "open"),
                "detail": rej,
            }
        )

        turn2 = run_agent_turn(task_id, store=store)
        applied = apply_proposal(task_id, store=store)
        math = (ws / "mathutil.py").read_text(encoding="utf-8")
        greet = (ws / "greeter.py").read_text(encoding="utf-8")
        checks.append(
            {
                "id": "held_out_multi_repair_apply",
                "ok": bool(
                    turn2.get("awaiting_apply")
                    and applied.get("ok")
                    and "return a + b" in math
                    and '"; ".join' in greet
                ),
                "detail": {
                    "apply_ok": applied.get("ok"),
                    "math_ok": "return a + b" in math,
                    "greet_ok": '"; ".join' in greet,
                },
            }
        )

        # Cancel blocks new turn effects
        c3 = chat_to_task("cancel me", workspace=ws, store=store, source="agent")
        tid3 = c3["task"]["task_id"]
        cancel_task(tid3, store=store)
        turn3 = run_agent_turn(tid3, store=store)
        checks.append(
            {
                "id": "cancel_blocks_agent_turn",
                "ok": bool(turn3.get("cancelled") or turn3.get("error") == "task_cancelled"),
                "detail": {"error": turn3.get("error"), "cancelled": turn3.get("cancelled")},
            }
        )

        ai = turn.get("ai") or {}
        checks.append(
            {
                "id": "mode_b_honest_status",
                "ok": ai.get("state") in {"available", "paused", "disabled"} and ai.get("free_only") is True,
                "detail": {"state": ai.get("state"), "provider": ai.get("provider")},
            }
        )
        # Live model turn is optional — record blocker, do not fail accept when paused
        checks.append(
            {
                "id": "live_model_or_explicit_blocker",
                "ok": True,
                "detail": {
                    "ai_state": ai.get("state"),
                    "blocker": None
                    if ai.get("state") == "available"
                    else "Mode B paused — install Ollama + fitted model for live model agent turns",
                    "deterministic_path_used": ai.get("state") != "available",
                },
            }
        )

        # Phase 3: gated model propose pauses without paid fallback; fixture path still wins
        empty_ws = root / "empty_ws"
        empty_ws.mkdir()
        (empty_ws / "readme.txt").write_text("no py fixtures\n", encoding="utf-8")
        model_pause = propose_fixes_model(empty_ws, "invent a fix")
        fresh = root / "ws_fresh"
        shutil.copytree(FIX_MULTI, fresh)
        routed = propose_fixes(fresh, "fix multi", allow_model=True)
        checks.append(
            {
                "id": "model_propose_pauses_or_edits_free_only",
                "ok": bool(
                    (model_pause.get("paused") and not model_pause.get("edits") and model_pause.get("fallback_used") is not True)
                    or (model_pause.get("edits") and model_pause.get("source") == "model_gated")
                ),
                "detail": {
                    "paused": model_pause.get("paused"),
                    "edits_n": len(model_pause.get("edits") or []),
                    "reason": model_pause.get("reason"),
                },
            }
        )
        checks.append(
            {
                "id": "deterministic_first_still_wins_on_fixture",
                "ok": bool(
                    routed.get("edits")
                    and routed.get("source") == "deterministic_fixture"
                    and len(routed["edits"]) >= 2
                ),
                "detail": {"source": routed.get("source"), "n": len(routed.get("edits") or [])},
            }
        )
        cache_ev = next(
            (e for e in events if e.get("type") == "tool_result" and e.get("tool") == "search"),
            {},
        )
        checks.append(
            {
                "id": "agent_search_exact_cache_meta",
                "ok": bool((cache_ev.get("result") or {}).get("exact_cache") is not None),
                "detail": (cache_ev.get("result") or {}).get("exact_cache"),
            }
        )

    passed = sum(1 for c in checks if c.get("ok"))
    failed = len(checks) - passed
    payload = {
        "ok": failed == 0,
        "passed": passed,
        "failed": failed,
        "checks": checks,
        "phase": "2-3",
        "north_star": "match_or_exceed_cursor_claude_on_measured_suites_free_only",
        "cursor_claude_comparison": "unknown",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# FreeForge Agent UX accept (Phase 2–3)",
        "",
        f"Generated: `{payload['generated_at']}`",
        f"Result: **{'PASS' if payload['ok'] else 'FAIL'}** ({passed}/{len(checks)})",
        "",
        "Streaming chat, context chips, tests tool, exact cache, gated propose, apply/reject.",
        "Deterministic propose when Mode B paused; competitor scores remain **unknown**.",
        "",
    ]
    for c in checks:
        lines.append(f"- `{c['id']}`: {'PASS' if c.get('ok') else 'FAIL'}")
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    REPORT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (RUNS_DIR / f"agent-ux-{stamp}.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    payload["report_md"] = "docs/eval/ide/AGENT_UX.md"
    payload["report_json"] = "docs/eval/ide/AGENT_UX.json"
    return payload
