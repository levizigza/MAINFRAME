"""Acceptance: repeated read-only does less work; source/permission/freshness invalidate."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from mainframe.cache import store
from mainframe.cache.facades import (
    authorization_never_cached,
    cached_model_response,
    cached_repo_scan,
    cached_retrieve,
    cached_tool_output,
    store_workflow_artifact,
)
from mainframe.cache.invalidate import (
    invalidate_for_freshness,
    invalidate_on_permission_change,
    invalidate_on_source_change,
)
from mainframe.cache.keys import content_version, permission_version
from mainframe.cache.policy import approximate_lookup_refused, may_exact_cache
from mainframe.cache.prompt_cache import prefer_avoid_request, prompt_cache_status
from mainframe.cache.runtime import refuse_approximate
from mainframe.cache.redact import redact_for_storage
from mainframe.config import ROOT

FIX = ROOT / "docs" / "cache" / "fixtures" / "readonly_task"
WORK = ROOT / ".mainframe" / "cache_work"


def _prep() -> Path:
    dest = WORK / "readonly_task"
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(FIX, dest)
    return dest


def run_cache_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    store.clear_all_for_tests()
    ws = _prep()

    # --- Exact vs approximate separation ---
    approx = refuse_approximate("similar query")
    checks.append(
        {
            "id": "approximate_separated_and_refused",
            "ok": (
                approx.get("approximate") is True
                and approx.get("allowed") is False
                and approximate_lookup_refused()["enabled"] is False
            ),
            "detail": approx,
        }
    )

    # --- Secrets redacted ---
    red = redact_for_storage(
        {"api_key": "sk-secret-value-here", "ok": True, "note": "bearer TOKEN1234567890abcdef"}
    )
    checks.append(
        {
            "id": "secrets_redacted",
            "ok": (
                red.get("api_key") == "[REDACTED]"
                and "sk-secret" not in str(red)
                and "[REDACTED]" in str(red.get("note", ""))
            ),
            "detail": red,
        }
    )

    # --- Repeated read-only: less work, identical results ---
    s1 = cached_repo_scan(ws)
    s2 = cached_repo_scan(ws)
    checks.append(
        {
            "id": "repeated_scan_less_work_identical",
            "ok": (
                s1["exact_cache"]["hit"] is False
                and s1["exact_cache"]["work_units"] == 1
                and s2["exact_cache"]["hit"] is True
                and s2["exact_cache"]["work_units"] == 0
                and s1["exact_cache"]["cache_key"] == s2["exact_cache"]["cache_key"]
                and s1.get("entry_count") == s2.get("entry_count")
                and s1.get("entry_count", 0) >= 1
            ),
            "detail": {
                "first": s1.get("exact_cache"),
                "second": s2.get("exact_cache"),
                "entry_count": s1.get("entry_count"),
            },
        }
    )

    r1 = cached_retrieve(ws, issue_text="bug in demo.py add", goal="find add")
    r2 = cached_retrieve(ws, issue_text="bug in demo.py add", goal="find add")
    checks.append(
        {
            "id": "repeated_retrieve_less_work_identical",
            "ok": (
                r1["exact_cache"]["work_units"] == 1
                and r2["exact_cache"]["hit"] is True
                and r2["exact_cache"]["work_units"] == 0
                and r1.get("ok", True) == r2.get("ok", True)
            ),
            "detail": {"first": r1.get("exact_cache"), "second": r2.get("exact_cache")},
        }
    )

    # Tool read-only
    from mainframe.tools.invoke import reset_audit

    reset_audit()
    t1 = cached_tool_output(
        "file_range",
        {"path": "demo.py", "start": 1, "end": 20},
        root=ws,
        call_id="cache-tool-1",
    )
    reset_audit()
    t2 = cached_tool_output(
        "file_range",
        {"path": "demo.py", "start": 1, "end": 20},
        root=ws,
        call_id="cache-tool-2",
    )
    checks.append(
        {
            "id": "repeated_tool_read_less_work",
            "ok": (
                t1["exact_cache"]["work_units"] == 1
                and t2["exact_cache"]["hit"] is True
                and t2["exact_cache"]["work_units"] == 0
            ),
            "detail": {"first": t1.get("exact_cache"), "second": t2.get("exact_cache")},
        }
    )

    # Workflow artifact
    w1 = store_workflow_artifact(
        ws,
        workflow_id="workspace_checksum",
        artifact={"sha256": "a" * 64, "file_count": 1},
        accepted=True,
    )
    w2 = store_workflow_artifact(
        ws,
        workflow_id="workspace_checksum",
        artifact={"sha256": "a" * 64, "file_count": 1},
        accepted=True,
    )
    checks.append(
        {
            "id": "workflow_artifact_exact_reuse",
            "ok": w1["cache_hit"] is False and w2["cache_hit"] is True and w2["work_units"] == 0,
            "detail": {"w1": w1, "w2_hit": w2.get("cache_hit")},
        }
    )

    # Model response — avoid request on repeat
    model = {"provider_id": "ollama_local", "model_id": "fixture", "model_version": "1"}
    calls = {"n": 0}

    def _gen() -> dict[str, Any]:
        calls["n"] += 1
        return {"text": "hello", "n": calls["n"]}

    m1 = cached_model_response(ws, prompt="hi", model=model, compute_response=_gen)
    m2 = cached_model_response(ws, prompt="hi", model=model, compute_response=_gen)
    checks.append(
        {
            "id": "model_response_avoids_request_on_hit",
            "ok": (
                m1["cache_hit"] is False
                and m1["work_units"] == 1
                and m2["cache_hit"] is True
                and m2["request_avoided"] is True
                and m2["work_units"] == 0
                and calls["n"] == 1
                and m2["result"]["text"] == "hello"
                and prefer_avoid_request()["policy"].startswith("prefer_exact")
                and prompt_cache_status("ollama_local")["use"] is False
            ),
            "detail": {"calls": calls["n"], "m2": {k: m2[k] for k in ("cache_hit", "request_avoided", "work_units")}},
        }
    )

    # Authorization never cached as current
    auth = authorization_never_cached({"allowed": True, "token": "ephemeral"}, ws)
    checks.append(
        {
            "id": "authorization_not_cached",
            "ok": (
                auth["cache_stored"] is False
                and auth["cache_hit"] is False
                and auth["policy"].get("code") == "authorization"
            ),
            "detail": auth.get("policy"),
        }
    )

    # Time-sensitive / freshness refused
    fresh_policy = may_exact_cache("model_response", freshness_required=True)
    m_fresh = cached_model_response(
        ws, prompt="now?", model=model, freshness_required=True, compute_response=lambda: {"text": "now"}
    )
    checks.append(
        {
            "id": "freshness_requirement_no_reuse_as_current",
            "ok": (
                fresh_policy["allowed"] is False
                and m_fresh["cache_hit"] is False
                and m_fresh.get("policy", {}).get("code") == "time_sensitive"
            ),
            "detail": {"policy": fresh_policy, "run": m_fresh.get("policy")},
        }
    )

    # --- Source change invalidates ---
    prev_hash = content_version(ws)["content_hash"]
    (ws / "demo.py").write_text(
        (ws / "demo.py").read_text(encoding="utf-8") + "\n# changed\n",
        encoding="utf-8",
    )
    inv_src = invalidate_on_source_change(ws, previous_content_hash=prev_hash)
    s3 = cached_repo_scan(ws)
    checks.append(
        {
            "id": "source_change_invalidates",
            "ok": (
                inv_src["changed"] is True
                and inv_src["removed"] >= 1
                and s3["exact_cache"]["hit"] is False
                and s3["exact_cache"]["work_units"] == 1
            ),
            "detail": {"inv": inv_src, "scan": s3.get("exact_cache")},
        }
    )

    # --- Permission change invalidates ---
    # Seed an entry under current permissions, then invalidate with a synthetic previous ver
    store.clear_all_for_tests()
    ws2 = _prep()
    cached_retrieve(ws2, issue_text="x", goal="y")
    prev_perm = permission_version()
    # Simulate permission change by invalidating with a different previous and new_permissions
    inv_perm = invalidate_on_permission_change(
        ws2,
        previous_permission_ver=prev_perm,
        new_permissions={"role": "restricted", "version": "changed-for-test"},
    )
    r3 = cached_retrieve(ws2, issue_text="x", goal="y")
    # After permission change, entries removed; new key uses new permission → miss then store
    checks.append(
        {
            "id": "permission_change_invalidates",
            "ok": (
                inv_perm["changed"] is True
                and inv_perm["removed"] >= 1
                and r3["exact_cache"]["hit"] is False
            ),
            "detail": {"inv": inv_perm, "retrieve": r3.get("exact_cache")},
        }
    )

    # Freshness invalidation API
    cached_model_response(ws2, prompt="a", model=model, compute_response=lambda: {"text": "a"})
    inv_f = invalidate_for_freshness(ws2, kind="model_response")
    checks.append(
        {
            "id": "freshness_invalidation_drops_entries",
            "ok": inv_f["removed"] >= 1 and inv_f["reason"] == "freshness_required",
            "detail": inv_f,
        }
    )

    # Project isolation — different roots do not share entries
    other = WORK / "other_project"
    if other.exists():
        shutil.rmtree(other, ignore_errors=True)
    shutil.copytree(FIX, other)
    store.clear_all_for_tests()
    a1 = cached_retrieve(ws2, issue_text="iso", goal="iso")
    b1 = cached_retrieve(other, issue_text="iso", goal="iso")
    checks.append(
        {
            "id": "projects_isolated",
            "ok": (
                a1["exact_cache"]["hit"] is False
                and b1["exact_cache"]["hit"] is False
                and a1["exact_cache"].get("cache_key") != b1["exact_cache"].get("cache_key")
            ),
            "detail": {
                "a": a1["exact_cache"].get("cache_key"),
                "b": b1["exact_cache"].get("cache_key"),
            },
        }
    )

    passed = sum(1 for c in checks if c["ok"])
    failed = len(checks) - passed
    return {"ok": failed == 0, "passed": passed, "failed": failed, "checks": checks}
