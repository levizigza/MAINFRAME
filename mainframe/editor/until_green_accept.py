"""Accept: offline propose-until-green + verified-patch memory replay (no model)."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from mainframe.config import ROOT
from mainframe.editor.until_green import run_until_green
from mainframe.memory.verified_patches import fingerprint_goal, lookup_verified


def run_until_green_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    fx = ROOT / "docs" / "eval" / "swe" / "fixtures" / "mf_swe_local_add"
    if not fx.is_dir():
        return {"ok": False, "error": "fixture_missing", "path": str(fx)}

    with tempfile.TemporaryDirectory(prefix="mf_ug_") as tmp:
        ws = Path(tmp) / "ws"
        shutil.copytree(fx, ws)
        goal = (ws / "PROBLEM.md").read_text(encoding="utf-8")

        # First pass: deterministic propose → green → remember
        loop1 = run_until_green(ws, goal=goal, max_turns=3, allow_model=False)
        checks.append(
            {
                "id": "offline_until_green",
                "ok": bool(loop1.get("green") and loop1.get("ok")),
                "detail": {
                    "green": loop1.get("green"),
                    "source": loop1.get("source"),
                    "model_calls": loop1.get("model_calls_total"),
                    "turns": len(loop1.get("turns") or []),
                },
            }
        )

        hit = lookup_verified(goal=goal)
        checks.append(
            {
                "id": "memory_saved_after_green",
                "ok": bool(hit.get("hit") and hit.get("edits")),
                "detail": {"fingerprint": fingerprint_goal(goal=goal), "hit": hit.get("hit")},
            }
        )

        # Re-break and replay from memory — zero model calls
        (ws / "mathutil.py").write_text(
            "def add(a, b):\n    return a * b  # bug: should add\n",
            encoding="utf-8",
        )
        loop2 = run_until_green(ws, goal=goal, max_turns=2, allow_model=False)
        checks.append(
            {
                "id": "memory_replay_zero_model",
                "ok": bool(
                    loop2.get("green")
                    and (loop2.get("model_calls_total") or 0) == 0
                    and any(t.get("memory_hit") for t in (loop2.get("turns") or []))
                ),
                "detail": {
                    "green": loop2.get("green"),
                    "source": loop2.get("source"),
                    "model_calls": loop2.get("model_calls_total"),
                    "turns": loop2.get("turns"),
                },
            }
        )

        # allow_model=False must still work when AI would be needed for unknown bugs
        empty = Path(tmp) / "empty"
        empty.mkdir()
        (empty / "readme.txt").write_text("no bug pattern\n", encoding="utf-8")
        loop3 = run_until_green(
            empty,
            goal="fix something unknown with no deterministic pattern",
            max_turns=1,
            allow_model=False,
        )
        checks.append(
            {
                "id": "offline_no_edits_without_model",
                "ok": bool(loop3.get("no_edits") or loop3.get("paused") or not loop3.get("green")),
                "detail": {
                    "green": loop3.get("green"),
                    "no_edits": loop3.get("no_edits"),
                    "paused": loop3.get("paused"),
                },
            }
        )

    passed = sum(1 for c in checks if c.get("ok"))
    return {
        "ok": passed == len(checks),
        "passed": passed,
        "failed": len(checks) - passed,
        "checks": checks,
    }
