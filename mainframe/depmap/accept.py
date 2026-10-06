"""Acceptance: cross-package dependent tests; unresolved dynamic widens plan."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mainframe.config import ROOT
from mainframe.depmap.cache import get_or_build
from mainframe.depmap.plan import plan_verification

FIXTURE = ROOT / "docs" / "depmap" / "fixtures" / "cross_pkg"


def run_depmap_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    m1 = get_or_build(FIXTURE, force=True)
    checks.append(
        {
            "id": "map_built",
            "ok": m1.get("ok") is True and m1.get("graph_service_used") is False,
            "detail": {
                "modules": len(m1.get("modules") or {}),
                "edges": len(m1.get("edges") or {}),
                "tests": list((m1.get("tests") or {}).keys()),
                "incomplete": m1.get("incomplete"),
                "cache_key": m1.get("cache_key"),
            },
        }
    )

    m2 = get_or_build(FIXTURE, force=False)
    checks.append(
        {
            "id": "cache_hit_by_hashes",
            "ok": m2.get("cache_hit") is True
            and m2.get("cache_key") == m1.get("cache_key")
            and m2.get("graph_service_used") is False,
            "detail": {"cache_hit": m2.get("cache_hit"), "key": m2.get("cache_key")},
        }
    )

    # Cross-package: change core widget → dependent app test selected
    plan = plan_verification(FIXTURE, ["pkg_core/widget.py"], force_rebuild=False)
    cmds = [c.get("command") for c in plan.get("commands") or []]
    kinds = [c.get("kind") for c in plan.get("commands") or []]
    targets = [c.get("target") for c in plan.get("commands") or []]
    has_direct = any(
        c.get("kind") == "changed_module_compile" and "widget.py" in (c.get("target") or "")
        for c in plan.get("commands") or []
    )
    has_dep_test = "tests/test_pkg_app.py" in (plan.get("dependent_tests") or []) or any(
        "test_pkg_app" in (c.get("target") or "") for c in plan.get("commands") or []
    )
    # Also expect core's own test when it imports widget
    has_core_test = "tests/test_pkg_core.py" in (plan.get("dependent_tests") or []) or any(
        "test_pkg_core" in (c.get("target") or "") for c in plan.get("commands") or []
    )
    checks.append(
        {
            "id": "cross_package_selects_dependent_test",
            "ok": plan.get("ok") and has_direct and has_dep_test,
            "detail": {
                "dependent_tests": plan.get("dependent_tests"),
                "affected": plan.get("affected_modules"),
                "commands": plan.get("commands"),
                "has_direct": has_direct,
                "has_dep_test": has_dep_test,
                "has_core_test": has_core_test,
            },
        }
    )

    # Dynamic loader change → unresolved + widened plan
    dyn = plan_verification(FIXTURE, ["pkg_app/loader.py"], force_rebuild=False)
    unresolved = dyn.get("unresolved_dynamic") or []
    checks.append(
        {
            "id": "dynamic_remains_unresolved",
            "ok": (
                dyn.get("ok")
                and dyn.get("plan_widened") is True
                and len(unresolved) >= 1
                and all(u.get("status") == "unresolved" for u in unresolved)
                and dyn.get("absence_not_proven") is True
            ),
            "detail": {
                "plan_widened": dyn.get("plan_widened"),
                "unresolved_dynamic": unresolved,
                "commands": dyn.get("commands"),
                "uncertainties_relevant": dyn.get("uncertainties_relevant"),
            },
        }
    )

    widened_cmd = any(
        c.get("kind") == "widened_due_to_uncertainty" for c in dyn.get("commands") or []
    )
    checks.append(
        {
            "id": "incomplete_map_widens_plan",
            "ok": widened_cmd and "python -m pytest -q" in [
                c.get("command") for c in dyn.get("commands") or []
            ],
            "detail": {"commands": dyn.get("commands")},
        }
    )

    checks.append(
        {
            "id": "no_graph_service_no_model",
            "ok": plan.get("graph_service_used") is False
            and plan.get("model_service_used") is False,
            "detail": {
                "graph_service_used": plan.get("graph_service_used"),
                "model_service_used": plan.get("model_service_used"),
            },
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
        "graph_service_used": False,
        "model_service_used": False,
    }
