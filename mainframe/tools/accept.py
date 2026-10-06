"""Acceptance: bad calls no side effects; valid calls auditable."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from mainframe.config import ROOT
from mainframe.tools.invoke import expose_for_task, invoke, reset_audit
from mainframe.tools.mcp_bridge import evaluate_mcp_tool, fingerprint_schema
from mainframe.tools.registry import list_tools, register_mcp_tool, reset_registry_for_tests

FIXTURE = ROOT / "docs" / "tools" / "fixtures" / "tool_lab"


def run_tools_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    reset_registry_for_tests()
    reset_audit()

    FIXTURE.mkdir(parents=True, exist_ok=True)
    target = FIXTURE / "sample.py"
    original = "def add(a, b):\n    return a + b\n"
    target.write_text(original, encoding="utf-8")
    probe = FIXTURE / "side_effect_probe.txt"
    probe.write_text("untouched\n", encoding="utf-8")
    probe_hash = hashlib.sha256(probe.read_bytes()).hexdigest()

    def probe_ok() -> bool:
        return (
            probe.is_file()
            and hashlib.sha256(probe.read_bytes()).hexdigest() == probe_hash
            and probe.read_text(encoding="utf-8") == "untouched\n"
        )

    # --- Wrong tool name ---
    bad_name = invoke("not_a_real_tool", {"query": "x"}, call_id="c-unknown", root=FIXTURE)
    checks.append(
        {
            "id": "unknown_tool_no_side_effects",
            "ok": (
                bad_name.get("ok") is False
                and bad_name.get("error_code") == "unknown_tool"
                and bad_name.get("side_effects") is False
                and probe_ok()
            ),
            "detail": bad_name,
        }
    )

    # --- Invented parameters ---
    invent = invoke(
        "search",
        {"query": "add", "invented_param": True},
        call_id="c-invent",
        root=FIXTURE,
    )
    checks.append(
        {
            "id": "invented_params_no_side_effects",
            "ok": (
                invent.get("ok") is False
                and invent.get("error_code") == "invalid_input"
                and probe_ok()
            ),
            "detail": invent,
        }
    )

    # --- Malformed JSON ---
    malformed = invoke("search", "{not-json", call_id="c-malformed", root=FIXTURE)
    checks.append(
        {
            "id": "malformed_json_no_side_effects",
            "ok": (
                malformed.get("ok") is False
                and malformed.get("error_code") == "malformed_json"
                and probe_ok()
            ),
            "detail": malformed,
        }
    )

    # --- Incomplete streaming ---
    incomplete = invoke(
        "search",
        {"__streaming_incomplete__": True},
        call_id="c-stream",
        root=FIXTURE,
    )
    checks.append(
        {
            "id": "incomplete_streaming_no_side_effects",
            "ok": (
                incomplete.get("ok") is False
                and incomplete.get("error_code") == "incomplete_streaming_args"
                and probe_ok()
            ),
            "detail": incomplete,
        }
    )

    # --- Valid call ---
    good = invoke(
        "file_range",
        {"path": "sample.py", "start": 1, "end": 2},
        call_id="c-good-range",
        root=FIXTURE,
    )
    checks.append(
        {
            "id": "valid_call_invokes_implementation",
            "ok": (
                good.get("ok") is True
                and good.get("call_id") == "c-good-range"
                and good.get("tool") == "file_range"
                and isinstance(good.get("result"), dict)
                and "add" in "\n".join((good.get("result") or {}).get("lines") or [])
            ),
            "detail": {"call_id": good.get("call_id"), "audit": good.get("audit")},
        }
    )

    # --- Duplicate operation ID ---
    dup = invoke(
        "file_range",
        {"path": "sample.py", "start": 1, "end": 1},
        call_id="c-good-range",
        root=FIXTURE,
    )
    checks.append(
        {
            "id": "duplicate_operation_id_no_side_effects",
            "ok": (
                dup.get("ok") is False
                and dup.get("error_code") == "duplicate_operation_id"
                and probe_ok()
            ),
            "detail": dup,
        }
    )

    # --- Bounded correction (string int) ---
    corr = invoke(
        "file_range",
        {"path": "sample.py", "start": "1", "end": "2"},
        call_id="c-correct",
        root=FIXTURE,
    )
    checks.append(
        {
            "id": "bounded_argument_correction",
            "ok": corr.get("ok") is True and corr.get("corrected_args") is not None,
            "detail": {"corrected_args": corr.get("corrected_args"), "audit": corr.get("audit")},
        }
    )

    # --- Stale file on patch ---
    sha = hashlib.sha256(target.read_bytes()).hexdigest()
    stale = invoke(
        "patch",
        {
            "path": "sample.py",
            "old": "return a + b",
            "new": "return a + b  # x",
            "content_sha256": "0" * 64,
        },
        call_id="c-stale",
        root=FIXTURE,
    )
    checks.append(
        {
            "id": "stale_file_error_no_patch",
            "ok": (
                stale.get("ok") is False
                and stale.get("error_code") == "stale_file"
                and target.read_text(encoding="utf-8") == original
            ),
            "detail": stale,
        }
    )

    # --- Valid patch side effect + audit ---
    patched = invoke(
        "patch",
        {
            "path": "sample.py",
            "old": "return a + b",
            "new": "return a + b  # fixed",
            "content_sha256": sha,
        },
        call_id="c-patch",
        root=FIXTURE,
    )
    checks.append(
        {
            "id": "valid_patch_auditable",
            "ok": (
                patched.get("ok") is True
                and patched.get("side_effects") is True
                and "# fixed" in target.read_text(encoding="utf-8")
                and patched.get("audit", {}).get("side_effects_executed") is True
            ),
            "detail": patched,
        }
    )

    # --- Task-relevant exposure ---
    exposed = expose_for_task("explanation")
    names = {t["name"] for t in exposed.get("tools") or []}
    checks.append(
        {
            "id": "task_relevant_tools_only",
            "ok": "search" in names and "file_range" in names and "patch" not in names,
            "detail": sorted(names),
        }
    )

    # --- MCP fingerprint + fee re-eval ---
    schema1 = {
        "type": "object",
        "properties": {"q": {"type": "string"}},
        "required": ["q"],
        "additionalProperties": False,
    }
    ev1 = evaluate_mcp_tool(
        name="demo_search",
        purpose="demo",
        input_schema=schema1,
        fee_token_price_usd=None,
        endpoint="stdio:demo",
    )
    reg1 = register_mcp_tool(ev1)
    schema2 = {
        "type": "object",
        "properties": {"q": {"type": "string"}, "paid_flag": {"type": "boolean"}},
        "required": ["q"],
        "additionalProperties": False,
    }
    ev2 = evaluate_mcp_tool(
        name="demo_search",
        purpose="demo",
        input_schema=schema2,
        fee_token_price_usd=0.0,
        endpoint="https://api.openai.com/v1",
        prior_fingerprint=ev1["schema_fingerprint"],
    )
    checks.append(
        {
            "id": "mcp_fingerprint_and_fee_reeval",
            "ok": (
                reg1.get("ok")
                and ev1.get("available") is True
                and ev2.get("fingerprint_changed") is True
                and ev2.get("available") is False
                and fingerprint_schema(schema1) != fingerprint_schema(schema2)
            ),
            "detail": {
                "fp1": ev1.get("schema_fingerprint"),
                "fp2": ev2.get("schema_fingerprint"),
                "available2": ev2.get("available"),
                "gate2": (ev2.get("gate") or {}).get("denied_code"),
            },
        }
    )

    # Restore sample for cleanliness
    target.write_text(original, encoding="utf-8")

    checks.append(
        {
            "id": "probe_untouched_after_failures",
            "ok": probe_ok(),
            "detail": {"probe_hash": probe_hash},
        }
    )

    passed = sum(1 for c in checks if c["ok"])
    failed = len(checks) - passed
    return {
        "ok": failed == 0,
        "passed": passed,
        "failed": failed,
        "checks": checks,
        "tool_count": len(list_tools()),
    }
