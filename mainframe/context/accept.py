"""Acceptance: constrained pack keeps fix-critical evidence; omits noise; token report."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mainframe.config import ROOT
from mainframe.context.assemble import assemble_context
from mainframe.context.docs_cache import installed_api_excerpt, record_fetched_excerpt
from mainframe.contracts.build import build_contract

FIXTURE = ROOT / "docs" / "context" / "fixtures" / "constrained_fix"


def run_context_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    request = (
        "Repair compute_total in buggy.py — AssertionError assert 10 == 60; "
        "should sum prices not min."
    )
    built = build_contract(request, scope_hint={"paths": ["buggy.py"]})
    contract = built.get("contract")

    pack = assemble_context(
        FIXTURE,
        request_text=request,
        goal="Fix compute_total to sum prices",
        contract=contract,
        constrained=True,
        include_docs_module="json",
        include_docs_attr="loads",
        probe_inference=True,
    )

    text = pack.get("assembled_text") or ""
    items = pack.get("pack", {}).get("items") or pack.get("items") or []
    paths = {it.get("path") for it in (pack.get("pack") or {}).get("ranges", [])}
    # Also scan all items
    all_paths = {it.get("path") for it in (pack.get("pack", {}).get("items") or [])}
    all_paths |= paths
    content_blob = text

    # Critical for correct fix
    has_sig = "compute_total" in content_blob and (
        "def compute_total" in content_blob or any(
            (it.get("signature") or "").find("compute_total") >= 0
            for section in (pack.get("pack") or {}).values()
            if isinstance(section, list)
            for it in section
        )
    )
    # Flatten preserved signatures
    preserved_sigs = pack.get("preserved", {}).get("complete_signatures") or []
    has_sig = has_sig or any("compute_total" in (s or "") for s in preserved_sigs)
    has_diag = "AssertionError" in content_blob or "10 == 60" in content_blob
    has_bug_pointer = "buggy.py" in content_blob
    sections = (pack.get("pack") or {}).get("sections") or {}
    items_flat = (pack.get("pack") or {}).get("items") or []
    has_contract = bool(sections.get("contract")) or any(
        it.get("kind") == "contract" for it in items_flat
    )

    checks.append(
        {
            "id": "retains_fix_critical_info",
            "ok": pack.get("ok") and has_sig and has_diag and has_bug_pointer and has_contract,
            "detail": {
                "has_sig": has_sig,
                "has_diag": has_diag,
                "has_bug_pointer": has_bug_pointer,
                "has_contract": has_contract,
                "preserved_sigs": preserved_sigs,
                "pointers": pack.get("preserved", {}).get("source_pointers"),
            },
        }
    )

    # Irrelevant files omitted from selected ranges/symbols (may appear in omitted list)
    selected_paths = set()
    for key in ("ranges", "symbols"):
        for it in (pack.get("pack") or {}).get(key) or []:
            if it.get("path"):
                selected_paths.add(it["path"])
    irrelevant_selected = {
        p for p in selected_paths if p and "irrelevant" in p
    }
    checks.append(
        {
            "id": "omits_irrelevant_files",
            "ok": len(irrelevant_selected) == 0,
            "detail": {
                "selected_paths": sorted(selected_paths),
                "irrelevant_selected": sorted(irrelevant_selected),
                "omitted": [
                    o for o in (pack.get("omitted") or []) if "irrelevant" in str(o.get("path"))
                ],
            },
        }
    )

    # Repeated logs not fully dumped
    spam_count = content_blob.count("TRACE spam line irrelevant")
    checks.append(
        {
            "id": "omits_repeated_logs",
            "ok": spam_count <= 5,
            "detail": {"spam_count": spam_count, "omitted_log_reasons": [
                o for o in (pack.get("omitted") or []) if "log" in str(o.get("reason", "")) or "novelty" in str(o.get("reason", ""))
            ]},
        }
    )

    checks.append(
        {
            "id": "never_silently_drops_critical",
            "ok": pack.get("silently_dropped_critical") is False,
            "detail": {
                "critical_overflow": pack.get("critical_overflow"),
                "additional_reads": pack.get("additional_reads"),
            },
        }
    )

    # Token use reported (estimated always; actual only if inference available)
    tu = pack.get("token_use") or {}
    checks.append(
        {
            "id": "reports_estimated_tokens",
            "ok": isinstance(tu.get("estimated_tokens"), int) and tu["estimated_tokens"] > 0,
            "detail": tu,
        }
    )
    # actual_tokens may be None when inference paused — that is honest
    checks.append(
        {
            "id": "actual_tokens_honest",
            "ok": (
                tu.get("actual_available") is True
                and isinstance(tu.get("actual_tokens"), int)
            )
            or (
                tu.get("actual_available") is False
                and tu.get("actual_tokens") is None
                and tu.get("inference_status") in {"paused", "disabled", "available", "probe_error", "not_probed"}
            ),
            "detail": {
                "actual_tokens": tu.get("actual_tokens"),
                "actual_available": tu.get("actual_available"),
                "inference_status": tu.get("inference_status"),
            },
        }
    )

    # Installed types preferred; fetched marked untrusted
    inst = installed_api_excerpt("json", "loads")
    fetched = record_fetched_excerpt(
        url="https://example.invalid/json.loads",
        body="unofficial scraped text",
        claimed_version="99",
    )
    checks.append(
        {
            "id": "prefer_installed_types_fetched_untrusted",
            "ok": (
                inst.get("ok")
                and inst.get("trust") == "installed_types"
                and inst.get("untrusted") is False
                and fetched.get("untrusted") is True
                and fetched.get("trust") == "untrusted_fetched"
            ),
            "detail": {"installed": inst.get("trust"), "fetched": fetched.get("trust")},
        }
    )

    checks.append(
        {
            "id": "budget_reserves_output_reasoning_tools",
            "ok": (
                pack.get("budget", {}).get("reserve_output", 0) > 0
                and pack.get("budget", {}).get("reserve_reasoning", 0) > 0
                and pack.get("budget", {}).get("reserve_tool_protocol", 0) > 0
                and pack.get("capacity", 0) < pack.get("budget", {}).get("total", 0)
            ),
            "detail": pack.get("budget"),
        }
    )

    passed = sum(1 for c in checks if c["ok"])
    failed = len(checks) - passed
    return {
        "ok": failed == 0,
        "passed": passed,
        "failed": failed,
        "checks": checks,
        "token_use": tu,
        "model_service_used": False,
        "fixture": str(FIXTURE.relative_to(ROOT)).replace("\\", "/"),
    }
