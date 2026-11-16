"""Accept: pin present, local fail-to-pass resolve, no copied upstream scores."""

from __future__ import annotations

from typing import Any

from mainframe.editor.until_green import run_until_green
from mainframe.memory.verified_patches import fingerprint_goal, lookup_verified
from mainframe.swebench.pin import PIN_PATH, load_pin
from mainframe.swebench.runner import run_swe_slice


def run_swebench_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    pin = load_pin()
    checks.append(
        {
            "id": "pin_present",
            "ok": PIN_PATH.is_file() and pin.get("protocol") == "swebench_style_resolve",
            "detail": {"version": pin.get("version"), "path": str(PIN_PATH)},
        }
    )
    checks.append(
        {
            "id": "no_copied_upstream_scores",
            "ok": pin.get("upstream_scores_copied") is False,
            "detail": pin.get("upstream_scores_copied"),
        }
    )

    slice_out = run_swe_slice(allow_model=False, max_turns=3)
    checks.append(
        {
            "id": "local_slice_resolves_offline",
            "ok": bool(slice_out.get("ok") and slice_out.get("resolved") == slice_out.get("total") and slice_out.get("total", 0) >= 1),
            "detail": {
                "resolved": slice_out.get("resolved"),
                "total": slice_out.get("total"),
                "rate": slice_out.get("resolve_rate"),
            },
        }
    )

    # Memory replay: same goal should hit verified memory with zero model calls
    from pathlib import Path
    import shutil
    import tempfile
    from mainframe.config import ROOT

    fx = ROOT / "docs" / "eval" / "swe" / "fixtures" / "mf_swe_local_add"
    with tempfile.TemporaryDirectory(prefix="mf_mem_") as tmp:
        ws = Path(tmp) / "ws"
        shutil.copytree(fx, ws)
        goal = (ws / "PROBLEM.md").read_text(encoding="utf-8")
        # Ensure memory from prior slice exists for this goal
        fp = fingerprint_goal(goal=goal)
        hit1 = lookup_verified(goal=goal)
        # Re-break file and replay from memory
        (ws / "mathutil.py").write_text(
            "def add(a, b):\n    return a * b  # bug: should add\n",
            encoding="utf-8",
        )
        loop2 = run_until_green(ws, goal=goal, max_turns=2, allow_model=False)
        checks.append(
            {
                "id": "verified_memory_replay_zero_model",
                "ok": bool(
                    hit1.get("hit")
                    and loop2.get("green")
                    and (loop2.get("model_calls_total") or 0) == 0
                    and any(t.get("memory_hit") for t in (loop2.get("turns") or []))
                ),
                "detail": {
                    "prior_hit": hit1.get("hit"),
                    "fp": fp,
                    "green": loop2.get("green"),
                    "model_calls": loop2.get("model_calls_total"),
                    "turns": loop2.get("turns"),
                },
            }
        )

    passed = sum(1 for c in checks if c.get("ok"))
    return {
        "ok": passed == len(checks),
        "passed": passed,
        "failed": len(checks) - passed,
        "checks": checks,
        "slice": {
            "resolve_rate": slice_out.get("resolve_rate"),
            "report_json": slice_out.get("report_json"),
        },
    }
