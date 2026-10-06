"""Publish recommended FreeForge configuration from accumulated evidence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from mainframe.ai import probe_free_inference
from mainframe.config import ROOT, RUNS_DIR, ensure_state
from mainframe.doctor import run_doctor
from mainframe.recommend.demos import (
    demo_coding_task,
    demo_codingbench_logic,
    demo_reusable_automation,
)
from mainframe.recommend.evidence import load_evidence
from mainframe.recommend.matrix import build_capability_matrix, summarize_workloads
from mainframe.recommend.modes import build_modes

REPORT_MD = ROOT / "docs" / "FREEFORGE_RECOMMENDED.md"
REPORT_JSON = ROOT / "docs" / "FREEFORGE_RECOMMENDED.json"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_md(payload: dict[str, Any]) -> None:
    modes = payload.get("modes") or {}
    matrix = payload.get("capability_matrix") or {}
    workloads = payload.get("workloads") or {}
    demos = payload.get("demos") or {}
    hw = payload.get("hardware") or {}

    lines = [
        "# Recommended FreeForge configuration",
        "",
        f"Generated: `{payload.get('generated_at')}`",
        f"Recommended mode: **`{modes.get('recommended_mode_id')}`**",
        "",
        "## Objective",
        "",
        "Optimize **correct completed work per available resource** "
        "(CPU, RAM, disk, time, verified free quota) — not agent count, "
        "model size, or a cosmetic frontier label.",
        "",
        "Unlimited frontier performance is **not claimed**.",
        "",
        "## Three modes",
        "",
    ]
    for mid, m in (modes.get("modes") or {}).items():
        avail = m.get("available_now")
        avail_s = "" if avail is None else f" — available_now=`{avail}`"
        lines.extend(
            [
                f"### `{mid}` — {m.get('title')}{avail_s}",
                "",
                f"- Inference: `{m.get('inference')}`",
                f"- Behavior: {m.get('behavior')}",
                f"- When inference unavailable: {m.get('when_inference_unavailable')}",
                "",
            ]
        )
    lines.extend(
        [
            f"**Rationale:** {modes.get('rationale')}",
            "",
            "## Capability matrix (concise)",
            "",
            "| Capability | Status | Note |",
            "|------------|--------|------|",
        ]
    )
    for cid, cell in (matrix.get("cells") or {}).items():
        lines.append(
            f"| `{cid}` | `{cell.get('status')}` | {(cell.get('note') or ('not claimed' if cell.get('explicitly_not_claimed') else ''))} |"
        )

    lines.extend(
        [
            "",
            "## Measured workloads (held-out)",
            "",
            "| Workload | FreeForge | Minimal | Manual | Outperforms minimal? |",
            "|----------|-----------|---------|--------|----------------------|",
        ]
    )
    for wid, row in (workloads.get("measured_workloads") or {}).items():
        lines.append(
            f"| {wid} | {row.get('freeforge_correct_rate')} (n={row.get('n')}, small_sample) | "
            f"{row.get('minimal_correct_rate')} | {row.get('manual_correct_rate')} | "
            f"{row.get('outperforms_minimal')} |"
        )

    lines.extend(
        [
            "",
            "## Sustainable quotas",
            "",
            f"- {(workloads.get('sustainable_quotas') or {}).get('note')}",
            f"- Default AI bucket (when Mode B used): "
            f"`{(workloads.get('sustainable_quotas') or {}).get('operational_guidance', {}).get('ai_requests_per_window', {}).get('ollama_local_default')}`",
            f"- Interactive daily capacity: **unknown** (not wall-clock theoretical volume)",
            "",
            "## Hardware observations (this host)",
            "",
            f"- CPU: `{hw.get('cpu_name')}` ({hw.get('logical_cpus')} logical)",
            f"- RAM available GiB: `{hw.get('available_gib')}` / total `{hw.get('total_gib')}`",
            f"- Optional CPU inference budget GiB: `{hw.get('cpu_inference_budget_gib')}`",
            f"- Free disk GiB: `{hw.get('free_disk_gib')}`",
            f"- AI probe: `{hw.get('ai_probe_status')}`",
            "",
            "## Where this build outperforms measured baselines",
            "",
        ]
    )
    for item in (workloads.get("vs_baselines") or {}).get("outperforms_measured_baselines") or []:
        lines.append(f"- {item}")
    lines.extend(["", "## Where it does not / unmeasured", ""])
    for item in (workloads.get("vs_baselines") or {}).get("does_not_outperform_or_unmeasured") or []:
        lines.append(f"- {item}")

    lines.extend(["", "## Unresolved weaknesses", ""])
    for w in workloads.get("unresolved_weaknesses") or []:
        lines.append(f"- **{w.get('id')}** ({w.get('severity')}): {w.get('finding')}")

    lines.extend(["", "## Prioritized next improvements", ""])
    for n in workloads.get("prioritized_next_improvements") or []:
        lines.append(f"{n.get('priority')}. **{n.get('id')}** — {n.get('action')}")

    lines.extend(
        [
            "",
            "## Acceptance demos (this run)",
            "",
            f"- Coding (W1 repair): `{'PASS' if (demos.get('coding') or {}).get('ok') else 'FAIL/BLOCKED'}` "
            f"— {(demos.get('coding') or {}).get('blocker')}",
            f"- Coding (cb_hold_logic): `{'PASS' if (demos.get('codingbench') or {}).get('ok') else 'FAIL/BLOCKED'}`",
            f"- Reusable automation (input_to_report): "
            f"`{'PASS' if (demos.get('automation') or {}).get('ok') else 'FAIL/BLOCKED'}` "
            f"— {(demos.get('automation') or {}).get('blocker')}",
            "",
            "## Strict contract reminder",
            "",
            "No required paid account, trial, promo credit, or hosted component for Mode A. "
            "Mode B pauses without local model. Mode C has zero currently eligible hosted providers.",
            "",
        ]
    )
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


def run_recommend() -> dict[str, Any]:
    ensure_state()
    generated_at = _utc()
    doctor = run_doctor()
    probe = probe_free_inference()
    probe_d = probe.to_dict() if hasattr(probe, "to_dict") else dict(probe or {})
    ollama_ok = probe_d.get("status") in ("ok", "available")

    modes = build_modes(ollama_reachable=ollama_ok, llamacpp_reachable=False)
    evidence = load_evidence()
    mem = doctor.get("memory") or {}
    cpu = doctor.get("cpu") or {}
    disk = doctor.get("disk") or {}
    limits = doctor.get("resource_limits") or {}
    hardware = {
        "cpu_name": cpu.get("name"),
        "logical_cpus": cpu.get("logical_cpus"),
        "available_gib": mem.get("available_gib"),
        "total_gib": mem.get("total_gib"),
        "free_disk_gib": disk.get("free_gib"),
        "cpu_inference_budget_gib": (limits.get("optional_cpu_inference") or {}).get(
            "ram_budget_gib"
        ),
        "ai_probe_status": probe_d.get("status"),
        "ai_probe_detail": probe_d.get("detail"),
        "host_context": (doctor.get("host_context") or {}).get("kind"),
    }

    matrix = build_capability_matrix(
        modes=modes, evidence=evidence, hardware=hardware, ai_probe=probe_d
    )
    workloads = summarize_workloads(evidence)

    # Live quota snapshot
    try:
        from mainframe.quota.admit import AdmissionController

        ctl = AdmissionController()
        snap = ctl.ledger.snapshot(
            ctl.bind_bucket(
                provider_id="ollama_local",
                window_id="default",
                limits={
                    "limit_requests": 60,
                    "limit_tokens": 100000,
                    "limit_context": 32000,
                    "limit_concurrency": 4,
                },
            )
        )
        workloads["sustainable_quotas"]["live_bucket_snapshot"] = snap
    except Exception as exc:  # noqa: BLE001
        workloads["sustainable_quotas"]["live_bucket_snapshot_error"] = str(exc)

    coding = demo_coding_task()
    codingbench = demo_codingbench_logic()
    automation = demo_reusable_automation()

    acceptance = {
        "recommended_mode_published": True,
        "three_modes_explicit": len(modes.get("modes") or {}) == 3,
        "unavailable_routes_described": True,
        "coding_demo_ok": bool(coding.get("ok")),
        "automation_demo_ok": bool(automation.get("ok")),
        "unmeasured_marked_unknown": True,
        "no_frontier_unlimited_claim": True,
        "mode_c_honest_empty": not (modes.get("modes") or {})
        .get("deterministic_plus_eligible_free_hosted_ai", {})
        .get("available_now"),
    }

    payload = {
        "ok": all(
            [
                acceptance["three_modes_explicit"],
                acceptance["coding_demo_ok"],
                acceptance["automation_demo_ok"],
                acceptance["mode_c_honest_empty"],
            ]
        ),
        "generated_at": generated_at,
        "modes": modes,
        "capability_matrix": matrix,
        "workloads": workloads,
        "hardware": hardware,
        "demos": {
            "coding": coding,
            "codingbench": codingbench,
            "automation": automation,
        },
        "acceptance": acceptance,
        "evidence_sources": evidence.get("sources"),
        "report_md": "docs/FREEFORGE_RECOMMENDED.md",
        "report_json": "docs/FREEFORGE_RECOMMENDED.json",
    }
    _write_md(payload)
    REPORT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (RUNS_DIR / f"recommend-{stamp}.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    return payload
