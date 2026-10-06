"""Three labeled non-AI deterministic automation demonstrations."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import url2pathname

from mainframe.config import ROOT
from mainframe.cost_gate import authorize
from mainframe.demos.broker import Broker

FIXTURES = ROOT / "docs" / "demo" / "fixtures"
WORK = ROOT / ".mainframe" / "demo_work"


def _reset(name: str) -> Path:
    path = WORK / name
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def demo_repo_inspect_and_test() -> dict[str, Any]:
    """Non-AI automation: inspect a local repo fixture and run its tests."""
    gate = authorize("tool", "local.demo_repo_inspect", local=True)
    if not gate.allowed:
        return {"ok": False, "automation_kind": "non_ai_deterministic", "cost_gate": gate.to_dict()}

    work = _reset("repo_inspect")
    src = FIXTURES / "repo_inspect"
    shutil.copytree(src, work, dirs_exist_ok=True)
    broker = Broker(work)
    tree = broker.list_tree()
    tests = broker.run_tests("test_app.py")
    return {
        "ok": tree.ok and tests.ok and bool(tests.detail.get("passed")),
        "name": "demo_repo_inspect_and_test",
        "automation_kind": "non_ai_deterministic",
        "label": "Non-AI automation: repository inspect + test",
        "files": tree.detail.get("files"),
        "tests_passed": tests.detail.get("passed"),
        "broker_log_len": len(broker.log),
        "workspace": str(work.relative_to(ROOT)).replace("\\", "/"),
    }


def demo_records_to_report() -> dict[str, Any]:
    """Non-AI automation: transform structured records into a validated report."""
    gate = authorize("tool", "local.demo_records_report", local=True)
    if not gate.allowed:
        return {"ok": False, "automation_kind": "non_ai_deterministic", "cost_gate": gate.to_dict()}

    work = _reset("records_report")
    src = FIXTURES / "records_report"
    shutil.copytree(src, work, dirs_exist_ok=True)
    broker = Broker(work)
    raw = broker.read_file("records.json")
    schema_r = broker.read_file("schema.json")
    if not (raw.ok and schema_r.ok):
        return {"ok": False, "automation_kind": "non_ai_deterministic", "error": "read_failed"}

    records = json.loads(str(raw.detail["content"]))
    schema = json.loads(str(schema_r.detail["content"]))
    source_sha = hashlib.sha256(str(raw.detail["content"]).encode()).hexdigest()
    report = {
        "title": "Structured records report",
        "source_sha256": source_sha,
        "rows": records,
        "row_count": len(records),
        "generated_by": "mainframe.demos.deterministic.demo_records_to_report",
        "automation_kind": "non_ai_deterministic",
    }
    # Lightweight validation against required keys / const (stdlib only).
    required = schema.get("required") or []
    missing = [k for k in required if k not in report]
    const_ok = report.get("automation_kind") == "non_ai_deterministic"
    rows_ok = isinstance(report["rows"], list) and len(report["rows"]) >= 1
    valid = not missing and const_ok and rows_ok and report["row_count"] == len(records)

    written = broker.write_file("report.json", json.dumps(report, indent=2) + "\n")
    return {
        "ok": valid and written.ok,
        "name": "demo_records_to_report",
        "automation_kind": "non_ai_deterministic",
        "label": "Non-AI automation: records → validated report",
        "missing_keys": missing,
        "report_path": "report.json",
        "row_count": report["row_count"],
        "workspace": str(work.relative_to(ROOT)).replace("\\", "/"),
    }


def demo_browser_local_fixture() -> dict[str, Any]:
    """Non-AI automation: Playwright click against a local HTML fixture (no external net)."""
    gate = authorize("tool", "local.demo_browser", local=True)
    if not gate.allowed:
        return {"ok": False, "automation_kind": "non_ai_deterministic", "cost_gate": gate.to_dict()}

    work = _reset("browser_local")
    src = FIXTURES / "browser_local" / "index.html"
    target = work / "index.html"
    shutil.copy2(src, target)
    file_url = target.resolve().as_uri()

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "name": "demo_browser_local_fixture",
            "automation_kind": "non_ai_deterministic",
            "label": "Non-AI automation: local browser fixture",
            "paused": True,
            "detail": f"Playwright unavailable ({type(exc).__name__}: {exc})",
        }

    # Ensure URL is file:// local path only
    parsed = urlparse(file_url)
    if parsed.scheme != "file":
        return {"ok": False, "automation_kind": "non_ai_deterministic", "error": "not_file_url"}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(file_url)
        before = page.locator("#heading").inner_text()
        page.locator("#go").click()
        after = page.locator("#heading").inner_text()
        browser.close()

    ok = before == "Before click" and after == "Clicked offline"
    return {
        "ok": ok,
        "name": "demo_browser_local_fixture",
        "automation_kind": "non_ai_deterministic",
        "label": "Non-AI automation: browser interaction on local fixture",
        "before": before,
        "after": after,
        "file_url_host": parsed.netloc or "local",
        "path": url2pathname(parsed.path),
        "workspace": str(work.relative_to(ROOT)).replace("\\", "/"),
    }
