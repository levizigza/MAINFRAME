"""Run pinned local SWE-style instances with fail-to-pass resolve rule."""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.config import ROOT, RUNS_DIR, ensure_state
from mainframe.editor.until_green import run_until_green
from mainframe.swebench.pin import FIXTURES, load_pin, list_local_instances

REPORT_DIR = ROOT / "docs" / "eval" / "swe"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_swe_slice(
    *,
    allow_model: bool = False,
    max_turns: int = 3,
) -> dict[str, Any]:
    """
    Resolve local pinned instances. Default allow_model=False (offline / no RAM load).
    Official resolve: tests that failed before must pass after.
    """
    ensure_state()
    pin = load_pin()
    instances = list_local_instances()
    rows: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="mf_swe_") as tmp:
        base = Path(tmp)
        for inst in instances:
            iid = str(inst.get("instance_id") or "")
            fx = FIXTURES / str(inst.get("fixture") or "")
            row: dict[str, Any] = {
                "instance_id": iid,
                "fixture": inst.get("fixture"),
                "started_at": _utc(),
            }
            if not fx.is_dir():
                row.update({"ok": False, "resolved": False, "error": "fixture_missing"})
                rows.append(row)
                continue
            ws = base / iid
            shutil.copytree(fx, ws)
            # Pre: tests must fail
            from mainframe.tools.invoke import invoke, reset_audit

            reset_audit()
            pre = invoke(
                "tests",
                {"target": "tests"},
                call_id=f"pre_{iid}",
                root=ws,
            )
            pre_body = pre.get("result") if isinstance(pre.get("result"), dict) else {}
            pre_failed = not bool(pre_body.get("passed"))
            if not pre_failed:
                row.update(
                    {
                        "ok": False,
                        "resolved": False,
                        "error": "precondition_tests_already_passing",
                        "pre": pre_body,
                    }
                )
                rows.append(row)
                continue

            goal = (ws / "PROBLEM.md").read_text(encoding="utf-8") if (ws / "PROBLEM.md").is_file() else iid
            # Map SWE local fixture bugs to codingloop deterministic proposer when shapes match
            # until_green uses propose_fixes; for add-bug use mathutil pattern if present
            loop = run_until_green(
                ws,
                goal=goal,
                max_turns=max_turns,
                allow_model=allow_model,
            )
            post = invoke(
                "tests",
                {"target": "tests"},
                call_id=f"post_{iid}",
                root=ws,
            )
            post_body = post.get("result") if isinstance(post.get("result"), dict) else {}
            resolved = bool(post_body.get("passed")) and bool(loop.get("green"))
            row.update(
                {
                    "ok": True,
                    "resolved": resolved,
                    "pre_failed": True,
                    "post_passed": bool(post_body.get("passed")),
                    "loop": {
                        "green": loop.get("green"),
                        "turns": len(loop.get("turns") or []),
                        "source": loop.get("source"),
                        "memory_saved": loop.get("memory_saved"),
                        "model_calls_total": loop.get("model_calls_total"),
                    },
                    "allow_model": allow_model,
                }
            )
            rows.append(row)

    resolved_n = sum(1 for r in rows if r.get("resolved"))
    payload = {
        "ok": True,
        "protocol": pin.get("protocol"),
        "pin_version": pin.get("version"),
        "upstream_scores_copied": bool(pin.get("upstream_scores_copied")),
        "allow_model": allow_model,
        "instances": rows,
        "resolved": resolved_n,
        "total": len(rows),
        "resolve_rate": round(100.0 * resolved_n / len(rows), 1) if rows else 0.0,
        "generated_at": _utc(),
        "note": "MAINFRAME-measured local slice only — not an official SWE-bench leaderboard submission.",
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = REPORT_DIR / "SLICE.json"
    out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (RUNS_DIR / f"swe-slice-{stamp}.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    payload["report_json"] = "docs/eval/swe/SLICE.json"
    return payload
