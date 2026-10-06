"""Acceptance: fixture inventory compare, exclusions, incremental edit work."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from mainframe.config import ROOT, STATE_DIR, ensure_state
from mainframe.inventory.scan import scan_repository
from mainframe.inventory.tools import file_range, overview

FIXTURE_SRC = ROOT / "docs" / "inventory" / "fixtures" / "sample_repo"
EXPECTED_PATH = ROOT / "docs" / "inventory" / "fixtures" / "expected_inventory.json"


def _norm(p: str) -> str:
    return p.replace("\\", "/")


def _paths_set(items: list[Any]) -> set[str]:
    out: set[str] = set()
    for it in items:
        if isinstance(it, dict):
            out.add(_norm(str(it.get("path", ""))))
        else:
            out.add(_norm(str(it)))
    return out


def compare_to_expected(summary: dict[str, Any], expected: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    def check(cid: str, ok: bool, detail: Any) -> None:
        findings.append({"id": cid, "ok": bool(ok), "detail": detail})

    check(
        "file_count_min",
        int(summary.get("file_count") or 0) >= int(expected["file_count_min"]),
        {"actual": summary.get("file_count"), "min": expected["file_count_min"]},
    )
    check(
        "privacy_excluded_count",
        int(summary.get("privacy_excluded_count") or 0)
        >= int(expected["privacy_excluded_count_min"]),
        {
            "actual": summary.get("privacy_excluded_count"),
            "min": expected["privacy_excluded_count_min"],
        },
    )

    pkgs = _paths_set(summary.get("packages") or [])
    for p in expected["packages"]:
        check(
            f"package:{p['path']}",
            _norm(p["path"]) in pkgs,
            {"expected": p, "actual_packages": summary.get("packages")},
        )

    roots = set(summary.get("source_roots") or [])
    for r in expected["source_roots_must_include"]:
        check(f"source_root:{r}", r in roots, {"roots": sorted(roots)})

    for field, key in (
        ("entry_points", "entry_points_must_include"),
        ("tests", "tests_must_include"),
        ("generated", "generated_must_include"),
        ("dependencies", "dependencies_must_include"),
        ("build_config", "build_config_must_include"),
    ):
        actual = {_norm(x) for x in (summary.get(field) or [])}
        for p in expected[key]:
            check(f"{field}:{p}", _norm(p) in actual, {"actual": sorted(actual)})

    langs = set((summary.get("languages") or {}).keys())
    for lang in expected["languages_must_include"]:
        check(f"language:{lang}", lang in langs, {"languages": sorted(langs)})

    visible = (
        list(summary.get("entry_points") or [])
        + list(summary.get("tests") or [])
        + list(summary.get("generated") or [])
        + list(summary.get("dependencies") or [])
        + list(summary.get("build_config") or [])
        + [p["path"] for p in (summary.get("packages") or []) if isinstance(p, dict)]
        + list(summary.get("untracked") or [])
    )
    visible_n = {_norm(x) for x in visible}
    # Also pull kinds paths indirectly via packages/source — ensure ignored absent from summary lists
    all_listed = visible_n | {_norm(p.get("path", "")) for p in (summary.get("packages") or []) if isinstance(p, dict)}
    for bad in expected["ignored_must_not_appear"]:
        check(
            f"ignored_absent:{bad}",
            _norm(bad) not in all_listed
            and _norm(bad) not in {_norm(x) for x in (summary.get("untracked") or [])},
            {"path": bad},
        )

    check(
        "no_embedding_service",
        summary.get("embedding_service_used") is False
        and expected.get("embedding_service_used") is False,
        summary.get("embedding_service_used"),
    )
    check(
        "no_model_request",
        summary.get("model_request_used") is False and expected.get("model_request_used") is False,
        summary.get("model_request_used"),
    )
    return findings


def run_inventory_accept() -> dict[str, Any]:
    ensure_state()
    checks: list[dict[str, Any]] = []

    if not FIXTURE_SRC.is_dir():
        return {
            "ok": False,
            "passed": 0,
            "failed": 1,
            "checks": [{"id": "fixture_present", "ok": False, "detail": str(FIXTURE_SRC)}],
        }

    expected = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
    work = STATE_DIR / "tmp" / f"inventory_accept_{int(time.time())}"
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(FIXTURE_SRC, work)

    # Full scan
    scan1 = scan_repository(work, incremental=False)
    checks.append(
        {
            "id": "scan_ok",
            "ok": bool(scan1.get("ok")),
            "detail": {
                "entry_count": scan1.get("entry_count"),
                "work": (scan1.get("summary") or {}).get("work"),
            },
        }
    )
    summary1 = scan1.get("summary") or {}
    checks.extend(compare_to_expected(summary1, expected))

    # Privacy paths must not have content hashes in store overview path
    ov = overview(work)
    checks.append(
        {
            "id": "overview_bounded",
            "ok": (
                ov.get("ok") is True
                and ov.get("bounded") is True
                and ov.get("embedding_service_used") is False
                and ov.get("model_request_used") is False
                and "duplicated_whole_repo" not in ov
            ),
            "detail": {
                "file_count": ov.get("file_count"),
                "max_list": ov.get("max_list"),
                "privacy_excluded_count": ov.get("privacy_excluded_count"),
            },
        }
    )

    fr = file_range(work, "src/app/util.py", 1, 5)
    checks.append(
        {
            "id": "file_range_bounded",
            "ok": (
                fr.get("ok") is True
                and fr.get("duplicated_whole_repo") is False
                and len(fr.get("lines") or []) <= 80
                and fr.get("max_range_lines") == 80
            ),
            "detail": {"lines": fr.get("lines"), "total_lines": fr.get("total_lines")},
        }
    )

    fr_priv = file_range(work, ".env", 1, 2)
    checks.append(
        {
            "id": "file_range_privacy_denied",
            "ok": fr_priv.get("ok") is False and fr_priv.get("error") == "privacy_excluded",
            "detail": fr_priv,
        }
    )

    # One-file edit → incremental work measurement
    target = work / "src" / "app" / "util.py"
    target.write_text(
        target.read_text(encoding="utf-8") + "\n# edited for incremental accept\n",
        encoding="utf-8",
    )
    # Ensure mtime advances on coarse FS clocks
    time.sleep(0.05)
    scan2 = scan_repository(work, incremental=True)
    work2 = (scan2.get("summary") or {}).get("work") or {}
    hashed = int(work2.get("hashed") or 0)
    reused = int(work2.get("reused") or 0)
    listed = int(work2.get("listed") or 0)
    checks.append(
        {
            "id": "incremental_one_file_edit_work",
            "ok": (
                scan2.get("ok") is True
                and hashed >= 1
                and hashed <= 3
                and reused >= max(0, listed - hashed - int(work2.get("skipped_privacy") or 0) - 2)
                and reused > hashed
            ),
            "detail": {
                "hashed": hashed,
                "reused": reused,
                "listed": listed,
                "skipped_privacy": work2.get("skipped_privacy"),
                "embedding_service_used": (scan2.get("summary") or {}).get(
                    "embedding_service_used"
                ),
                "model_request_used": (scan2.get("summary") or {}).get("model_request_used"),
            },
        }
    )

    # Casefold path key identity (Windows)
    from mainframe.inventory.scan import normalize_path_key

    checks.append(
        {
            "id": "windows_path_casing",
            "ok": normalize_path_key("Src/App/Util.py") == normalize_path_key("src/app/util.py"),
            "detail": {
                "a": normalize_path_key("Src/App/Util.py"),
                "b": normalize_path_key("src/app/util.py"),
            },
        }
    )

    # Cleanup work copy (best-effort)
    try:
        shutil.rmtree(work, ignore_errors=True)
    except OSError:
        pass

    passed = sum(1 for c in checks if c["ok"])
    failed = len(checks) - passed
    return {
        "ok": failed == 0,
        "passed": passed,
        "failed": failed,
        "checks": checks,
        "fixture": str(FIXTURE_SRC.relative_to(ROOT)).replace("\\", "/"),
        "embedding_service_used": False,
        "model_request_used": False,
    }
