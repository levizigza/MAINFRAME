"""Compute and publish MAINFRAME IDE completion percentages.

O1–O9 = product checklist progress (engineering judgment + accept evidence).
O10 and public bench cells stay 0 until a measured run exists — never invent competitor scores.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.ai import probe_free_inference
from mainframe.config import ROOT, RUNS_DIR, ensure_state

REPORT_MD = ROOT / "docs" / "eval" / "ide" / "SCOREBOARD.md"
REPORT_JSON = ROOT / "docs" / "eval" / "ide" / "SCOREBOARD.json"

# Checklist baselines — update when accept evidence changes.
_BASE: list[dict[str, Any]] = [
    {"id": "O1", "name": "Free-only contract", "pct": 95, "gate": "accept"},
    {"id": "O2", "name": "Deterministic coding brain", "pct": 90, "gate": "accept"},
    {"id": "O3", "name": "Agent UX", "pct": 75, "gate": "editor agent-accept"},
    {"id": "O4", "name": "Workbench shell", "pct": 35, "gate": "workbench accept + Electron"},
    {"id": "O5", "name": "Mode B local inference", "pct": 40, "gate": "ollama + model"},
    {"id": "O6", "name": "Multi-turn harness parity", "pct": 55, "gate": "propose-until-green"},
    {"id": "O7", "name": "MCP in agent loop", "pct": 20, "gate": "stdio MCP live"},
    {"id": "O8", "name": "Self-upgrade memory", "pct": 55, "gate": "replay zero-model hit"},
    {"id": "O9", "name": "Public bench protocol wired", "pct": 40, "gate": "SWE slice runner"},
    {"id": "O10", "name": "Match/exceed Cursor & Claude Code", "pct": 0, "gate": "measured parity"},
]


def _live_adjustments(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    probe = probe_free_inference()
    pd = probe.to_dict() if hasattr(probe, "to_dict") else {}
    ollama = shutil.which("ollama") is not None
    models: list[str] = []
    if ollama:
        try:
            import subprocess

            p = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            lines = [ln.strip() for ln in (p.stdout or "").splitlines() if ln.strip()]
            # skip header
            for ln in lines[1:]:
                name = ln.split()[0] if ln.split() else ""
                if name and name.upper() != "NAME":
                    models.append(name)
        except Exception:  # noqa: BLE001
            pass

    out = [dict(r) for r in rows]
    by_id = {r["id"]: r for r in out}

    # O5: 40 base with ollama empty; 70 with models but probe paused; 100 when probe available
    if pd.get("status") == "available" and models:
        by_id["O5"]["pct"] = 100
        by_id["O5"]["status"] = "available"
        by_id["O5"]["detail"] = f"models={models[:5]}"
    elif models:
        by_id["O5"]["pct"] = 70
        by_id["O5"]["status"] = "models_present_probe_paused"
        by_id["O5"]["detail"] = f"models={models[:5]} probe={pd.get('status')}"
    elif ollama:
        by_id["O5"]["pct"] = 40
        by_id["O5"]["status"] = "ollama_no_models"
        by_id["O5"]["detail"] = pd.get("detail")
    else:
        by_id["O5"]["pct"] = 10
        by_id["O5"]["status"] = "no_ollama"
        by_id["O5"]["detail"] = pd.get("detail")

    # O6 / O8 / O9: offline until-green + SWE slice evidence
    swe_dir = ROOT / "docs" / "eval" / "swe"
    slice_json = swe_dir / "SLICE.json"
    if slice_json.is_file():
        try:
            sdata = json.loads(slice_json.read_text(encoding="utf-8"))
            rate = float(sdata.get("resolve_rate") or 0)
            by_id["O9"]["pct"] = max(int(by_id["O9"]["pct"]), 55 if rate >= 100 else 40)
            by_id["O9"]["status"] = "local_slice_measured"
            by_id["O9"]["detail"] = {
                "resolved": sdata.get("resolved"),
                "total": sdata.get("total"),
                "resolve_rate": rate,
                "allow_model": sdata.get("allow_model"),
            }
            by_id["O6"]["pct"] = max(int(by_id["O6"]["pct"]), 70)
            by_id["O6"]["status"] = "until_green_offline"
            if rate >= 100 and sdata.get("allow_model") is False:
                by_id["O8"]["pct"] = max(int(by_id["O8"]["pct"]), 70)
                by_id["O8"]["status"] = "verified_patch_memory_offline"
        except Exception:  # noqa: BLE001
            by_id["O9"]["pct"] = max(by_id["O9"]["pct"], 30)
            by_id["O9"]["status"] = "slice_artifacts"
    elif swe_dir.is_dir() and any(swe_dir.glob("*.json")):
        by_id["O9"]["pct"] = max(by_id["O9"]["pct"], 30)
        by_id["O9"]["status"] = "slice_artifacts"
    agent_ux = ROOT / "docs" / "eval" / "ide" / "AGENT_UX.json"
    if agent_ux.is_file():
        by_id["O3"]["status"] = "measured"

    # O7: stdio MCP live when accept artifact / module present
    mcp_server = ROOT / "mainframe" / "mcp" / "servers" / "verified_memory.py"
    if mcp_server.is_file():
        by_id["O7"]["pct"] = max(int(by_id["O7"]["pct"]), 70)
        by_id["O7"]["status"] = "stdio_mcp_verified_memory"
        by_id["O7"]["detail"] = "local verified-patch memory MCP; paid/remote refused"

    # O4: overlay-only = 35; pinned vscode clone + overlay applied = 55 (Electron build still open)
    clone = ROOT / ".workbench-build" / "vscode"
    overlay_applied = clone / "src" / "vs" / "workbench" / "contrib" / "freeforge"
    if clone.is_dir() and (clone / ".git").exists() and overlay_applied.is_dir():
        by_id["O4"]["pct"] = max(int(by_id["O4"]["pct"]), 55)
        by_id["O4"]["status"] = "vscode_pin_cloned_overlay"
    elif (ROOT / "workbench" / "overlay" / "freeforge").is_dir():
        by_id["O4"]["status"] = "overlay_only"

    # O10 stays 0 until explicit measured parity file
    parity = ROOT / "docs" / "eval" / "ide" / "PARITY.json"
    if parity.is_file():
        try:
            pdata = json.loads(parity.read_text(encoding="utf-8"))
            if pdata.get("parity_achieved") is True:
                by_id["O10"]["pct"] = 100
                by_id["O10"]["status"] = "measured_parity"
            elif isinstance(pdata.get("resolve_rate"), (int, float)):
                # Scale reported resolve vs 100% target of our pinned suite — still not Cursor claim
                rate = float(pdata["resolve_rate"])
                by_id["O10"]["pct"] = max(0, min(99, int(round(rate))))
                by_id["O10"]["status"] = "partial_measured"
                by_id["O10"]["detail"] = pdata
        except Exception:  # noqa: BLE001
            pass
    else:
        by_id["O10"]["status"] = "unknown"
        by_id["O10"]["detail"] = "No PARITY.json — competitor comparison unknown"

    live = {
        "ai_status": pd.get("status"),
        "ollama_on_path": ollama,
        "models": models,
        "probe_detail": pd.get("detail"),
    }
    return list(by_id.values()), live


def scoreboard_payload() -> dict[str, Any]:
    ensure_state()
    rows, live = _live_adjustments(_BASE)
    benches = {
        "codingbench_live": "unknown",
        "swe_verified_slice": "unknown",
        "swe_multilingual": "unknown",
        "terminal_bench": "unknown",
        "cursor_claude_parity": "unknown",
    }
    # Fill from files if present
    # Latest codingbench run under .mainframe/runs
    runs = ROOT / ".mainframe" / "runs"
    live_ok = live_n = 0
    if runs.is_dir():
        lives = sorted(runs.glob("codingbench-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in lives[:5]:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if data.get("measurement_kind") != "live_model_quality":
                continue
            attempts = data.get("attempts") or []
            if not attempts:
                continue
            live_n = len(attempts)
            live_ok = sum(1 for a in attempts if a.get("success"))
            rate = round(100.0 * live_ok / live_n) if live_n else 0
            benches["codingbench_live"] = f"{live_ok}/{live_n} ({rate}%)"
            by_id = {r["id"]: r for r in rows}
            # Partial credit only — do not clobber higher offline/SWE status labels
            o9_before = int(by_id["O9"]["pct"])
            live_floor = 75 if live_n and live_ok == live_n else (60 if live_n else 15)
            by_id["O9"]["pct"] = max(o9_before, live_floor)
            by_id["O9"]["status"] = (
                "codingbench_live_full_green" if live_n and live_ok == live_n else "codingbench_live_cell"
            )
            by_id["O9"]["detail"] = {"live_ok": live_ok, "live_n": live_n, "rate_pct": rate}
            o6_before = int(by_id["O6"]["pct"])
            # Live multiturn wired when any attempt used until_green loop
            used_until = any(
                (a.get("agent") or {}).get("loop") == "until_green"
                or (a.get("verify") or {}).get("agent_meta", {}).get("loop") == "until_green"
                for a in attempts
            )
            by_id["O6"]["pct"] = max(o6_before, 80 if used_until else 40)
            by_id["O6"]["status"] = "until_green_live" if used_until else "live_agent_wired"
            rows[:] = list(by_id.values())
            break
    swe = ROOT / "docs" / "eval" / "swe"
    slice_path = swe / "SLICE.json"
    if slice_path.is_file():
        try:
            sdata = json.loads(slice_path.read_text(encoding="utf-8"))
            r = sdata.get("resolved", 0)
            t = sdata.get("total", 0)
            rate = sdata.get("resolve_rate", 0)
            benches["swe_verified_slice"] = f"local {r}/{t} ({rate}%) offline"
        except Exception:  # noqa: BLE001
            benches["swe_verified_slice"] = "artifacts_present"
    elif swe.is_dir() and any(swe.glob("*.json")):
        benches["swe_verified_slice"] = "artifacts_present"

    product = [r for r in rows if r["id"] != "O10"]
    product_avg = round(sum(int(r["pct"]) for r in product) / len(product))
    north = next(r for r in rows if r["id"] == "O10")

    return {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "product_avg_pct": product_avg,
        "north_star_pct": int(north["pct"]),
        "objectives": rows,
        "live": live,
        "benches": benches,
        "note": (
            "Product % is checklist progress. North-star / public benches stay 0 "
            "until measured runs exist. Never copy Cursor/Claude leaderboard numbers."
        ),
    }


def run_scoreboard() -> dict[str, Any]:
    payload = scoreboard_payload()
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# FreeForge IDE scoreboard",
        "",
        f"Generated: `{payload['generated_at']}`",
        f"**Product avg (O1–O9): {payload['product_avg_pct']}%**",
        f"**North star (O10): {payload['north_star_pct']}%**",
        "",
        f"AI: `{payload['live'].get('ai_status')}` · models: `{payload['live'].get('models')}`",
        "",
        "| ID | Objective | % | Status |",
        "|----|-----------|---|--------|",
    ]
    for r in payload["objectives"]:
        lines.append(
            f"| {r['id']} | {r['name']} | **{r['pct']}%** | {r.get('status', '')} |"
        )
    lines.extend(["", payload["note"], ""])
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    REPORT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (RUNS_DIR / f"scoreboard-{stamp}.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    payload["report_md"] = "docs/eval/ide/SCOREBOARD.md"
    payload["report_json"] = "docs/eval/ide/SCOREBOARD.json"
    return payload
