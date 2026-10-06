"""Acceptance: no simultaneous overspend; deny shows reason + retry or unknown reset."""

from __future__ import annotations

import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from mainframe.quota.admit import AdmissionController
from mainframe.quota.identity import capacity_not_multiplied, refuse_identity_rotation
from mainframe.quota.retry import from_provider_headers, parse_retry_after
from mainframe.quota.schedule import reset_fairness_for_tests, schedule_order
from mainframe.quota.types import ActualUsage, UsageEstimate


def run_quota_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    tmp = Path(tempfile.mkdtemp(prefix="mf-quota-"))
    db = tmp / "ledger.sqlite"
    ctl = AdmissionController(path=db)
    limits = {
        "limit_requests": 100,
        "limit_tokens": 10,
        "limit_context": 100,
        "limit_concurrency": 10,
    }
    reset_fairness_for_tests()

    # --- Simultaneous admits cannot overspend token ledger ---
    results: list[Any] = []
    lock = threading.Lock()

    def one(_: int) -> dict[str, Any]:
        d = ctl.admit(
            provider_id="ollama_local",
            estimate=UsageEstimate(requests=1, tokens=3, context_tokens=0),
            priority="interactive",
            window_id="sim",
            limits=limits,
        )
        with lock:
            results.append(d)
        return d.to_dict()

    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(one, i) for i in range(8)]
        for f in as_completed(futs):
            f.result()

    allowed = [d for d in results if d.allowed]
    denied = [d for d in results if not d.allowed]
    # 10 token cap / 3 each → at most 3 admits
    charged = sum(3 for _ in allowed)
    snap = ctl.ledger.snapshot(ctl.bind_bucket(provider_id="ollama_local", window_id="sim", limits=limits))
    checks.append(
        {
            "id": "simultaneous_no_overspend",
            "ok": (
                len(allowed) <= 3
                and charged <= 10
                and snap["in_flight"]["tokens"] <= 10
                and len(allowed) + len(denied) == 8
                and all(d.denied_code and d.reason for d in denied)
            ),
            "detail": {
                "allowed": len(allowed),
                "denied": len(denied),
                "in_flight_tokens": snap["in_flight"]["tokens"],
                "deny_sample": denied[0].to_dict() if denied else None,
            },
        }
    )

    # --- Denied response has reason + retry estimate OR reset_unknown ---
    deny = ctl.admit(
        provider_id="ollama_local",
        estimate=UsageEstimate(tokens=100),
        window_id="sim",
        limits=limits,
    )
    checks.append(
        {
            "id": "deny_reason_and_retry_or_unknown",
            "ok": (
                deny.allowed is False
                and bool(deny.reason)
                and (
                    (deny.retry_after_s is not None and deny.reset_unknown is False)
                    or deny.reset_unknown is True
                )
            ),
            "detail": deny.to_dict(),
        }
    )

    # --- Retry-After parsed; missing → unknown ---
    ra = parse_retry_after("5")
    unknown = parse_retry_after(None)
    hdr = from_provider_headers(429, {"Retry-After": "12"})
    hdr_unk = from_provider_headers(429, {})
    checks.append(
        {
            "id": "retry_after_and_unknown_reset",
            "ok": (
                ra["retry_after_s"] == 5.0
                and ra["reset_unknown"] is False
                and unknown["reset_unknown"] is True
                and unknown["retry_after_s"] is None
                and hdr["retry_after_s"] == 12.0
                and hdr_unk["reset_unknown"] is True
            ),
            "detail": {"ra": ra, "unknown": unknown, "hdr": hdr, "hdr_unk": hdr_unk},
        }
    )

    # --- Apply cooldown from 429; next admit explains retry ---
    bucket = ctl.bind_bucket(provider_id="test_prov", window_id="cd", limits={**limits, "limit_tokens": 1000})
    sig = ctl.note_provider_response(bucket, status=429, headers={"Retry-After": "3"})
    blocked = ctl.admit(
        provider_id="test_prov",
        estimate=UsageEstimate(tokens=1),
        window_id="cd",
        limits={**limits, "limit_tokens": 1000},
    )
    checks.append(
        {
            "id": "429_cooldown_blocks_with_retry",
            "ok": (
                sig.get("apply_cooldown") is True
                and blocked.allowed is False
                and blocked.denied_code == "cooldown"
                and blocked.retry_after_s is not None
                and blocked.reset_unknown is False
            ),
            "detail": {"signal": sig, "blocked": blocked.to_dict()},
        }
    )

    # --- Cancel releases reservation ---
    ctl2 = AdmissionController(path=tmp / "cancel.sqlite")
    a = ctl2.admit(
        provider_id="ollama_local",
        estimate=UsageEstimate(tokens=4),
        window_id="c",
        limits={"limit_requests": 10, "limit_tokens": 10, "limit_context": 10, "limit_concurrency": 2},
    )
    bkey = ctl2.bind_bucket(
        provider_id="ollama_local",
        window_id="c",
        limits={"limit_requests": 10, "limit_tokens": 10, "limit_context": 10, "limit_concurrency": 2},
    )
    ctl2.note_provider_response(bkey, cancelled=True, reservation_id=a.reservation_id)
    snap2 = ctl2.ledger.snapshot(bkey)
    checks.append(
        {
            "id": "cancel_releases_reservation",
            "ok": a.allowed and snap2["in_flight"]["reservations"] == 0,
            "detail": {"before_ok": a.allowed, "in_flight": snap2["in_flight"]},
        }
    )

    # --- Unknown usage kept conservatively ---
    ctl3 = AdmissionController(path=tmp / "unk.sqlite")
    lim3 = {"limit_requests": 10, "limit_tokens": 20, "limit_context": 20, "limit_concurrency": 2}
    r = ctl3.admit(
        provider_id="ollama_local",
        estimate=UsageEstimate(tokens=8, tool_overhead_tokens=2, reasoning_overhead_tokens=2),
        window_id="u",
        limits=lim3,
    )
    rec = ctl3.reconcile(r.reservation_id or "", ActualUsage(requests=1, unknown=True))
    # After reconcile with unknown, reservation leaves in-flight but charged amounts preserved in row
    checks.append(
        {
            "id": "unknown_usage_conservative",
            "ok": rec.get("ok") is True and rec.get("unknown_usage") is True and rec["charged"]["tokens"] == 8,
            "detail": rec,
        }
    )

    # --- Persist across restart ---
    ctl4 = AdmissionController(path=tmp / "persist.sqlite")
    lim4 = {"limit_requests": 10, "limit_tokens": 10, "limit_context": 10, "limit_concurrency": 4}
    p1 = ctl4.admit(
        provider_id="ollama_local",
        estimate=UsageEstimate(tokens=6),
        window_id="p",
        limits=lim4,
    )
    ctl4.reload()
    snap_p = ctl4.ledger.snapshot(ctl4.bind_bucket(provider_id="ollama_local", window_id="p", limits=lim4))
    p2 = ctl4.admit(
        provider_id="ollama_local",
        estimate=UsageEstimate(tokens=6),
        window_id="p",
        limits=lim4,
    )
    checks.append(
        {
            "id": "persist_reservations_across_restart",
            "ok": (
                p1.allowed
                and snap_p["in_flight"]["tokens"] == 6
                and p2.allowed is False
                and p2.reset_unknown is True or p2.denied_code is not None
            ),
            "detail": {"snap": snap_p, "p2": p2.to_dict()},
        }
    )

    # Fix operator precedence for persist check clarity in ok field
    checks[-1]["ok"] = bool(
        p1.allowed and snap_p["in_flight"]["tokens"] == 6 and p2.allowed is False and bool(p2.reason)
    )

    # --- Interactive ahead of background ---
    reset_fairness_for_tests()
    ordered = schedule_order(
        [
            {"priority": "background", "id": "bg"},
            {"priority": "interactive", "id": "ui"},
        ]
    )
    checks.append(
        {
            "id": "interactive_before_background",
            "ok": ordered[0]["id"] == "ui" and ordered[1]["id"] == "bg",
            "detail": [x["id"] for x in ordered],
        }
    )

    # Anti-starvation: after enough deferred, background boosted
    reset_fairness_for_tests()
    from mainframe.quota import schedule as sched

    for _ in range(3):
        sched.record_background_deferred()
    ordered2 = schedule_order(
        [
            {"priority": "interactive", "id": "ui2"},
            {"priority": "background", "id": "bg2"},
        ]
    )
    checks.append(
        {
            "id": "background_not_starved",
            "ok": ordered2[0]["id"] == "bg2",
            "detail": [x["id"] for x in ordered2],
        }
    )

    # --- Identity rotation refused; more providers ≠ unlimited ---
    rot = refuse_identity_rotation(
        provider_id="groq_cloud",
        requested_identity="key-b",
        active_identity="key-a",
        purpose="evade rate limit",
    )
    cap = capacity_not_multiplied(3, global_token_cap=100, per_provider_caps=[80, 80, 80])
    checks.append(
        {
            "id": "no_identity_rotation_no_unlimited",
            "ok": (
                rot.get("refused") is True
                and cap["effective_cap"] == 100
                and cap["unlimited"] is False
                and cap["naive_sum_caps"] == 240
            ),
            "detail": {"rot": rot, "cap": cap},
        }
    )

    # --- Reconcile lower actual frees capacity for next admit ---
    ctl5 = AdmissionController(path=tmp / "rec.sqlite")
    lim5 = {"limit_requests": 10, "limit_tokens": 10, "limit_context": 10, "limit_concurrency": 2}
    a1 = ctl5.admit(
        provider_id="ollama_local",
        estimate=UsageEstimate(tokens=8, tool_overhead_tokens=0),
        window_id="r",
        limits=lim5,
    )
    ctl5.reconcile(a1.reservation_id or "", ActualUsage(requests=1, tokens=2, context_tokens=0, tool_overhead_tokens=0, reasoning_overhead_tokens=0))
    a2 = ctl5.admit(
        provider_id="ollama_local",
        estimate=UsageEstimate(tokens=8),
        window_id="r",
        limits=lim5,
    )
    checks.append(
        {
            "id": "reconcile_actual_including_overhead_path",
            "ok": a1.allowed and a2.allowed is True,
            "detail": {"a1": a1.reservation_id, "a2_allowed": a2.allowed},
        }
    )

    passed = sum(1 for c in checks if c["ok"])
    failed = len(checks) - passed
    return {
        "ok": failed == 0,
        "passed": passed,
        "failed": failed,
        "checks": checks,
        "ledger_dir": str(tmp),
    }
