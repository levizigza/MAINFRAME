"""Local website-maintenance demo: detect break, patch HTML, verify layout/behavior."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any
from mainframe.browser.locators import semantic_control_present
from mainframe.browser.probe import playwright_available
from mainframe.browser.session import ephemeral_session
from mainframe.browser.submit_guard import guard_external_submission
from mainframe.browser.waits import wait_for_load
from mainframe.capabilities.store import CapabilityStore
from mainframe.config import ROOT

FIXTURES = ROOT / "docs" / "demo" / "fixtures" / "site_maintenance"

PATCH_OLD = """    <!-- legacy #legacy-submit removed — fix must restore semantic control -->
  </main>"""

PATCH_NEW = """    <button type="button" role="button" aria-label="Apply fix" id="apply-fix">Apply fix</button>
  </main>
  <script>
    document.getElementById("apply-fix").addEventListener("click", function () {
      var el = document.getElementById("status");
      el.textContent = "healthy";
      el.className = "status-healthy";
    });
  </script>"""


def _apply_coding_patch(target: Path) -> dict[str, Any]:
    text = target.read_text(encoding="utf-8")
    if PATCH_OLD not in text:
        return {"ok": False, "error": "patch_anchor_missing"}
    updated = text.replace(PATCH_OLD, PATCH_NEW, 1)
    target.write_text(updated, encoding="utf-8")
    return {"ok": True, "path": str(target), "tool": "patch"}


def run_website_maintenance_demo(
    store: CapabilityStore | None = None,
    *,
    project_id: str = "site_maintenance_demo",
) -> dict[str, Any]:
    if not playwright_available():
        return {
            "ok": False,
            "paused": True,
            "name": "website_maintenance_demo",
            "detail": "Playwright unavailable",
        }

    work = Path(tempfile.mkdtemp(prefix="mf-site-maint-"))
    index = work / "index.html"
    shutil.copy2(FIXTURES / "index_broken.html", index)
    file_url = index.resolve().as_uri()
    store = store or CapabilityStore(work / "caps.sqlite")

    store.grant(
        project_id=project_id,
        capabilities=["reading", "editing", "browsing", "sending_messages"],
        destinations=["local", "reports@example.com"],
        operations=["read_file", "edit_file", "browse_local", "send_report"],
    )

    with ephemeral_session(project_id=project_id) as page:
        page.goto(file_url, wait_until="domcontentloaded")
        wait_for_load(page)
        missing = semantic_control_present(page, role="button", name="Apply fix")
        status_before = page.locator("#status").inner_text()
        form_action = page.locator("#notify").get_attribute("action") or ""
        guard_before_fix = guard_external_submission(
            store, project_id=project_id, form_action=form_action
        )

        patch = _apply_coding_patch(index)
        if not patch.get("ok"):
            return {"ok": False, "patch": patch, "missing_control": missing}

        page.reload(wait_until="domcontentloaded")
        wait_for_load(page)
        page.get_by_role("button", name="Apply fix").click()
        page.locator("#status").wait_for(state="visible")
        status_after = page.locator("#status").inner_text()
        main_box = page.locator("#app-main").bounding_box()

    return {
        "ok": (
            missing.get("present") is False
            and status_before == "broken"
            and status_after == "healthy"
            and patch.get("ok")
            and guard_before_fix.get("held") is True
            and guard_before_fix.get("paused") is True
        ),
        "name": "website_maintenance_demo",
        "missing_control_before": missing,
        "status_before": status_before,
        "status_after": status_after,
        "patch": patch,
        "layout_box": main_box,
        "external_submit_guard": {
            "held": guard_before_fix.get("held"),
            "paused": guard_before_fix.get("paused"),
        },
        "workspace": str(work),
    }


def verify_layout_variant(project_id: str = "site_layout_v2") -> dict[str, Any]:
    if not playwright_available():
        return {"ok": False, "paused": True}
    work = Path(tempfile.mkdtemp(prefix="mf-layout-v2-"))
    target = work / "index.html"
    shutil.copy2(FIXTURES / "index_layout_v2.html", target)
    url = target.resolve().as_uri()
    with ephemeral_session(project_id=project_id) as page:
        page.goto(url, wait_until="domcontentloaded")
        wait_for_load(page)
        present = semantic_control_present(page, role="button", name="Apply fix")
        page.get_by_role("button", name="Apply fix").click()
        page.locator("#status").wait_for(state="visible")
        status = page.locator("#status").inner_text()
        layout_marker = page.locator(".layout-v2").count()
    return {
        "ok": present.get("present") and status == "healthy" and layout_marker == 1,
        "present": present,
        "status": status,
        "layout_v2": layout_marker,
    }
