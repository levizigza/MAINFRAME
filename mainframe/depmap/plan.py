"""Select affected modules and verification commands from the dependency map."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mainframe.cost_gate import authorize
from mainframe.depmap.cache import get_or_build


def _norm(p: str) -> str:
    return p.replace("\\", "/")


def plan_verification(
    root: Path,
    changed_paths: list[str],
    *,
    observed_runs: list[dict[str, Any]] | None = None,
    force_rebuild: bool = False,
) -> dict[str, Any]:
    """
    Identify likely affected modules and verification commands for changed files.

    When the map is incomplete (dynamic imports, reflection, generated code,
    external services), widen the check plan rather than treating unobserved
    dependencies as absent.
    """
    gate = authorize("tool", "local.depmap_plan", local=True)
    if not gate.allowed:
        return {"ok": False, "cost_gate": gate.to_dict()}

    root = root.resolve()
    dep_map = get_or_build(root, observed_runs=observed_runs, force=force_rebuild)
    changed = [_norm(p) for p in changed_paths]

    affected: set[str] = set(changed)
    dependent_tests: set[str] = set()
    reasons: list[dict[str, Any]] = []

    # Reverse edges: who imports a changed module?
    for ch in changed:
        reasons.append({"path": ch, "reason": "directly_changed"})
        for edge in dep_map.get("edges") or []:
            if edge.get("kind") not in {"static_import", "observed_test_run"}:
                continue
            to_path = edge.get("to_path")
            to_mod = edge.get("to_module") or ""
            ch_mod = (dep_map.get("modules") or {}).get(ch, {}).get("module")
            hits = False
            if to_path and _norm(to_path) == ch:
                hits = True
            elif ch_mod and (to_mod == ch_mod or to_mod.startswith(ch_mod + ".")):
                hits = True
            if hits:
                src = _norm(edge.get("from") or "")
                if src:
                    affected.add(src)
                    reasons.append(
                        {
                            "path": src,
                            "reason": "depends_on_changed",
                            "via": edge.get("kind"),
                            "edge_to": to_path or to_mod,
                        }
                    )
                    if src in (dep_map.get("tests") or {}):
                        dependent_tests.add(src)

    # Transitive: modules/tests that depend on anything already affected
    # (cross-package: test → app.service → core.widget)
    changed_wave = True
    while changed_wave:
        changed_wave = False
        snapshot = set(affected)
        for edge in dep_map.get("edges") or []:
            if edge.get("kind") not in {"static_import", "observed_test_run"}:
                continue
            to_path = _norm(edge.get("to_path") or "")
            to_mod = edge.get("to_module") or ""
            src = _norm(edge.get("from") or "")
            if not src or src in affected:
                continue
            hit = False
            if to_path and to_path in snapshot:
                hit = True
            else:
                for aff in snapshot:
                    aff_mod = (dep_map.get("modules") or {}).get(aff, {}).get("module")
                    if aff_mod and (to_mod == aff_mod or to_mod.startswith(aff_mod + ".")):
                        hit = True
                        break
            if hit:
                affected.add(src)
                changed_wave = True
                reasons.append(
                    {
                        "path": src,
                        "reason": "transitive_depends_on_affected",
                        "via": edge.get("kind"),
                        "edge_to": to_path or to_mod,
                    }
                )
                if src in (dep_map.get("tests") or {}):
                    dependent_tests.add(src)

    # Tests that import changed or affected modules
    for tpath, tmeta in (dep_map.get("tests") or {}).items():
        for imp in tmeta.get("imports") or []:
            for aff in list(affected):
                aff_mod = (dep_map.get("modules") or {}).get(aff, {}).get("module")
                if not aff_mod:
                    continue
                if imp == aff_mod or aff_mod.startswith(imp + ".") or imp.startswith(aff_mod):
                    if tpath not in dependent_tests:
                        dependent_tests.add(tpath)
                        affected.add(tpath)
                        reasons.append(
                            {
                                "path": tpath,
                                "reason": "test_imports_affected_module",
                                "import": imp,
                                "affected_module": aff_mod,
                            }
                        )

    # Direct checks for changed modules (non-test)
    direct_commands: list[dict[str, Any]] = []
    for ch in changed:
        if ch in (dep_map.get("tests") or {}):
            direct_commands.append(
                {
                    "command": (dep_map["tests"][ch].get("verify_command")),
                    "target": ch,
                    "kind": "changed_test",
                }
            )
        else:
            # Module-level compile/check
            direct_commands.append(
                {
                    "command": f'python -m py_compile "{ch}"',
                    "target": ch,
                    "kind": "changed_module_compile",
                }
            )
            # Prefer co-located / package tests already linked
            pkg = (dep_map.get("modules") or {}).get(ch, {}).get("package")
            for tpath, tmeta in (dep_map.get("tests") or {}).items():
                if tmeta.get("package") == pkg and tpath not in dependent_tests:
                    # Same package test — likely relevant
                    if any(
                        (dep_map.get("modules") or {}).get(ch, {}).get("module", "").startswith(
                            (imp or "")
                        )
                        or imp
                        in {
                            (dep_map.get("modules") or {}).get(ch, {}).get("module"),
                            (dep_map.get("modules") or {}).get(ch, {}).get("package"),
                        }
                        for imp in tmeta.get("imports") or []
                    ):
                        dependent_tests.add(tpath)

    for t in sorted(dependent_tests):
        direct_commands.append(
            {
                "command": (dep_map.get("tests") or {}).get(t, {}).get("verify_command"),
                "target": t,
                "kind": "dependent_test",
            }
        )

    # Uncertainty → widen plan
    unresolved = [
        u
        for u in (dep_map.get("uncertainties") or [])
        if u.get("widens_plan") and not u.get("resolved")
    ]
    # Also unresolved dynamic edges touching affected packages
    dyn_edges = [
        e
        for e in (dep_map.get("edges") or [])
        if e.get("kind") == "dynamic_import_unresolved"
    ]
    widen = bool(dep_map.get("incomplete")) and (
        any(_path_related(u.get("path"), changed, affected, dep_map) for u in unresolved)
        or any(_path_related(e.get("from"), changed, affected, dep_map) for e in dyn_edges)
        or any(_path_related(u.get("path"), changed, affected, dep_map) for u in unresolved)
    )

    # Always widen if a changed file itself has unresolved dynamic deps
    changed_has_dynamic = any(
        (u.get("path") in changed or _norm(u.get("path") or "") in changed)
        and u.get("kind") in {"dynamic_import", "reflection", "generated_code", "external_service"}
        and u.get("widens_plan")
        for u in (dep_map.get("uncertainties") or [])
    )
    if changed_has_dynamic:
        widen = True

    widened_commands: list[dict[str, Any]] = []
    if widen:
        # Broader package / all tests — do not claim unobserved deps are absent
        widened_commands.append(
            {
                "command": "python -m pytest -q",
                "target": "*",
                "kind": "widened_due_to_uncertainty",
                "detail": "Map incomplete; unobserved dependencies are not proven absent",
            }
        )
        if any(u.get("kind") == "external_service" for u in unresolved):
            widened_commands.append(
                {
                    "command": "python -m mainframe inspect",
                    "target": "*",
                    "kind": "widened_external_inspection",
                    "detail": "External service usage unresolved — inspect rather than assume isolation",
                }
            )

    # Dedup commands by command string
    seen: set[str] = set()
    commands: list[dict[str, Any]] = []
    for c in direct_commands + widened_commands:
        cmd = c.get("command")
        if not cmd or cmd in seen:
            continue
        seen.add(cmd)
        commands.append(c)

    unresolved_dynamic = [
        {
            **e,
            "status": "unresolved",
            "note": "Remains unresolved until broader test or inspection establishes impact",
        }
        for e in dyn_edges
        if _path_related(e.get("from"), changed, affected, dep_map) or not changed
    ]
    # Include dynamic uncertainties on changed files even if edge list incomplete
    for u in dep_map.get("uncertainties") or []:
        if u.get("kind") == "dynamic_import" and u.get("widens_plan") and not u.get("resolved"):
            if u.get("path") in changed or _path_related(u.get("path"), changed, affected, dep_map):
                unresolved_dynamic.append(
                    {
                        "from": u.get("path"),
                        "kind": "dynamic_import_unresolved",
                        "status": "unresolved",
                        "uncertainty": u,
                        "note": "Remains unresolved until broader test or inspection establishes impact",
                    }
                )

    return {
        "ok": True,
        "changed": changed,
        "affected_modules": sorted(affected),
        "dependent_tests": sorted(dependent_tests),
        "commands": commands,
        "reasons": reasons,
        "plan_widened": widen or changed_has_dynamic,
        "unresolved_dynamic": unresolved_dynamic,
        "uncertainties_relevant": [
            u
            for u in (dep_map.get("uncertainties") or [])
            if _path_related(u.get("path"), changed, affected, dep_map)
        ],
        "absence_not_proven": True,
        "cache_hit": dep_map.get("cache_hit"),
        "cache_key": dep_map.get("cache_key"),
        "graph_service_used": False,
        "model_service_used": False,
        "map_incomplete": bool(dep_map.get("incomplete")),
    }


def _path_related(
    path: str | None,
    changed: list[str],
    affected: set[str],
    dep_map: dict[str, Any],
) -> bool:
    if not path:
        return False
    p = _norm(path)
    if p in changed or p in affected:
        return True
    pkg = (dep_map.get("modules") or {}).get(p, {}).get("package")
    for ch in changed:
        if (dep_map.get("modules") or {}).get(ch, {}).get("package") == pkg:
            return True
    return False
