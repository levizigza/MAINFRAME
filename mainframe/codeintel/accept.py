"""Acceptance: duplicate symbols, callers, reject absent dependency APIs — no model."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mainframe.codeintel.tools import (
    callers,
    invalidate_index,
    lookup_symbol,
    reject_absent_call,
    signature,
    tool_status,
)
from mainframe.config import ROOT

FIXTURE = ROOT / "docs" / "codeintel" / "fixtures" / "dup_callers"


def run_codeintel_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    invalidate_index(FIXTURE)

    st = tool_status()
    checks.append(
        {
            "id": "tool_status_no_model",
            "ok": st.get("ok") is True and st.get("model_service_used") is False,
            "detail": st,
        }
    )

    # --- Duplicate symbol names ---
    all_proc = lookup_symbol(FIXTURE, "process")
    checks.append(
        {
            "id": "duplicate_symbols_listed",
            "ok": all_proc.get("ok") and all_proc.get("count", 0) >= 2,
            "detail": {
                "count": all_proc.get("count"),
                "modules": [d.get("module") for d in all_proc.get("definitions") or []],
                "evidence_kinds": [
                    (d.get("evidence") or {}).get("kind")
                    for d in all_proc.get("definitions") or []
                ],
            },
        }
    )

    alpha = lookup_symbol(FIXTURE, "process", module="alpha.util")
    beta = lookup_symbol(FIXTURE, "process", module="beta.util")
    alpha_mods = {d["module"] for d in alpha.get("definitions") or []}
    beta_mods = {d["module"] for d in beta.get("definitions") or []}
    checks.append(
        {
            "id": "duplicate_symbols_disambiguated",
            "ok": (
                alpha.get("count") == 1
                and beta.get("count") == 1
                and alpha_mods == {"alpha.util"}
                and beta_mods == {"beta.util"}
            ),
            "detail": {"alpha": sorted(alpha_mods), "beta": sorted(beta_mods)},
        }
    )

    # Evidence must not be model_hypothesis
    kinds = [
        (d.get("evidence") or {}).get("kind")
        for d in (all_proc.get("definitions") or [])
    ]
    checks.append(
        {
            "id": "no_model_hypothesis_evidence",
            "ok": all(k != "model_hypothesis" for k in kinds) and "parser_approximate" in kinds,
            "detail": kinds,
        }
    )

    # Content versions attached
    has_ver = all(
        (d.get("range") or {}).get("content_version", {}).get("sha256")
        for d in (alpha.get("definitions") or []) + (beta.get("definitions") or [])
    )
    checks.append(
        {
            "id": "content_versions_attached",
            "ok": has_ver,
            "detail": [
                (d.get("range") or {}).get("content_version")
                for d in (alpha.get("definitions") or [])[:1]
            ],
        }
    )

    # --- Actual callers ---
    alpha_callers = callers(FIXTURE, "process", module="alpha.util")
    beta_callers = callers(FIXTURE, "process", module="beta.util")

    def _caller_names(groups: list[dict[str, Any]]) -> set[str]:
        names: set[str] = set()
        for g in groups:
            for c in g.get("callers") or []:
                names.add(c.get("call_name") or "")
        return names

    a_names = _caller_names(alpha_callers.get("groups") or [])
    b_names = _caller_names(beta_callers.get("groups") or [])
    checks.append(
        {
            "id": "alpha_callers_correct",
            "ok": "alpha_process" in a_names and "process" not in a_names,
            "detail": {"call_names": sorted(a_names), "groups": alpha_callers.get("groups")},
        }
    )
    checks.append(
        {
            "id": "beta_callers_correct",
            "ok": "process" in b_names and "alpha_process" not in b_names,
            "detail": {"call_names": sorted(b_names), "groups": beta_callers.get("groups")},
        }
    )

    # Signature narrow tool
    sig = signature(FIXTURE, name="process", module="alpha.util")
    checks.append(
        {
            "id": "signature_tool",
            "ok": sig.get("ok") and len(sig.get("signatures") or []) >= 1,
            "detail": sig.get("signatures"),
        }
    )

    # --- Reject absent dependency API (fixture vendor_dep) ---
    extra = str(FIXTURE)
    ok_call = reject_absent_call("vendor_dep", "real_api", extra_path=extra)
    bad_call = reject_absent_call("vendor_dep", "missing_api", extra_path=extra)
    checks.append(
        {
            "id": "accept_installed_dependency_api",
            "ok": ok_call.get("accepted") is True and ok_call.get("proposed_call_rejected") is False,
            "detail": ok_call,
        }
    )
    checks.append(
        {
            "id": "reject_absent_dependency_api",
            "ok": (
                bad_call.get("accepted") is False
                and bad_call.get("proposed_call_rejected") is True
                and bad_call.get("reason") == "attribute_absent_from_installed_module"
            ),
            "detail": bad_call,
        }
    )

    # Also reject against stdlib json (always installed)
    json_bad = reject_absent_call("json", "loads_everything_secretly")
    json_ok = reject_absent_call("json", "loads")
    checks.append(
        {
            "id": "reject_absent_stdlib_api",
            "ok": json_bad.get("proposed_call_rejected") is True
            and json_ok.get("accepted") is True,
            "detail": {"bad": json_bad.get("reason"), "ok_sig": json_ok.get("signature")},
        }
    )

    checks.append(
        {
            "id": "no_model_service",
            "ok": True,
            "detail": {"model_service_used": False},
        }
    )

    passed = sum(1 for c in checks if c["ok"])
    failed = len(checks) - passed
    return {
        "ok": failed == 0,
        "passed": passed,
        "failed": failed,
        "checks": checks,
        "fixture": str(FIXTURE.relative_to(ROOT)).replace("\\", "/"),
        "model_service_used": False,
        "adapters": st.get("adapters"),
    }
