"""Acceptance: visual create+execute ≡ CLI; Node-RED eval; removable; no dual trigger."""

from __future__ import annotations

import json
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from mainframe.visual.bridge import (
    bridge_status,
    create_simple_reporting_workflow,
    describe_workflow,
    invoke_workflow,
    refuse_nodered_independent_trigger,
    remove_visual_leaves_workflows,
)
from mainframe.visual.eval_nodered import evaluate_nodered_optional
from mainframe.visual.nodered_flow import export_nodered_flow
from mainframe.visual.server import start_bridge
from mainframe.visual.store import list_workflows, load_saved, save_workflow, strip_inline_secrets
from mainframe.workflows.runner import run_workflow


def _http_json(url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 — loopback only in accept
        return json.loads(resp.read().decode("utf-8"))


def run_visual_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    # 1) Node-RED evaluation — Apache-2.0 core; no required paid nodes; prefer simple form
    ev = evaluate_nodered_optional()
    checks.append(
        {
            "id": "nodered_core_license_and_costs",
            "ok": bool(
                ev.get("ok")
                and ev["core"]["license"] == "Apache-2.0"
                and ev["core"]["local_runtime_fee"] is False
                and ev["core"]["hosted_service_required"] is False
                and ev.get("install_required") is False
                and ev.get("required_to_run_freeforge") is False
                and ev.get("verdict") == "optional_not_required"
                and ev.get("paid_fallback") is False
            ),
            "detail": {
                "verdict": ev.get("verdict"),
                "license": ev["core"]["license"],
                "service_cost_local": ev["core"]["service_cost_local"],
                "additional_nodes": ev.get("additional_nodes"),
                "recommendation": ev.get("recommendation"),
            },
        }
    )

    with tempfile.TemporaryDirectory(prefix="visual_accept_") as tmp:
        tmp_path = Path(tmp)
        wf_root = tmp_path / "workflows"
        work_root = tmp_path / "work"
        wf_root.mkdir()
        work_root.mkdir()

        status = bridge_status()
        checks.append(
            {
                "id": "simple_form_not_second_stack",
                "ok": bool(
                    status.get("visual_kind") == "simple_local_form"
                    and status.get("dual_trigger_forbidden") is True
                    and status.get("removable") is True
                    and status.get("scheduler_owner") == "openclaw_gateway"
                    and status.get("secrets", {}).get("store_in_exported_flows") is False
                ),
                "detail": {
                    k: status.get(k)
                    for k in (
                        "visual_kind",
                        "scheduler_owner",
                        "effect_ledger",
                        "dual_trigger_forbidden",
                        "removable",
                    )
                },
            }
        )

        # 2) Start visual bridge; create + execute via HTTP (visual path)
        server, _thread = start_bridge(
            host="127.0.0.1",
            port=0,
            workflows_root=wf_root,
            work_root=work_root,
        )
        port = server.server_address[1]
        base = f"http://127.0.0.1:{port}"
        try:
            created = _http_json(
                f"{base}/api/create",
                {"workflow_id": "visual_reporting", "title": "Visual bridge report"},
            )
            described = _http_json(f"{base}/api/describe?id=visual_reporting")
            visual_run = _http_json(
                f"{base}/api/run",
                {
                    "workflow_id": "visual_reporting",
                    "title": "Visual bridge report",
                    "records": [
                        {"id": "a1", "label": "Alpha", "value": 10},
                        {"id": "b2", "label": "Beta", "value": 20},
                    ],
                },
            )

            checks.append(
                {
                    "id": "visual_create_exposes_schemas_permissions_blocked_ai",
                    "ok": bool(
                        created.get("ok")
                        and described.get("ok")
                        and described.get("schemas")
                        and described.get("permissions")
                        and isinstance(described.get("blocked_ai_steps"), list)
                    ),
                    "detail": {
                        "permissions": described.get("permissions"),
                        "blocked_ai_steps": described.get("blocked_ai_steps"),
                        "step_schemas": len((described.get("schemas") or {}).get("steps") or []),
                    },
                }
            )

            checks.append(
                {
                    "id": "visual_execute_ok",
                    "ok": bool(
                        visual_run.get("ok")
                        and (visual_run.get("exposed") or {}).get("results", {}).get("ok")
                        and visual_run.get("effect_ledger_used") is True
                        and visual_run.get("scheduler_owner") == "openclaw_gateway"
                    ),
                    "detail": {
                        "results": (visual_run.get("exposed") or {}).get("results"),
                        "outputs": (visual_run.get("execution") or {}).get("outputs"),
                    },
                }
            )

            # 3) Equivalent CLI behavior (same workflow + records via run_workflow)
            loaded = load_saved("visual_reporting", wf_root)
            cli_work = tmp_path / "cli_work"
            cli_work.mkdir()
            (cli_work / "records.json").write_text(
                json.dumps(
                    [
                        {"id": "a1", "label": "Alpha", "value": 10},
                        {"id": "b2", "label": "Beta", "value": 20},
                    ],
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            cli_out = run_workflow(
                loaded["workflow"],
                inputs={"title": "Visual bridge report"},
                work_dir=cli_work,
                available_capabilities={
                    "local.read",
                    "local.write",
                    "local.artifact",
                    "human.decide",
                },
                strict_capabilities=True,
            )
            v_sha = ((visual_run.get("execution") or {}).get("outputs") or {}).get("sha256")
            c_sha = (cli_out.get("outputs") or {}).get("sha256")
            # Titles frozen in transform args may differ if visual used args title —
            # compare row_count and artifact presence for equivalence of behavior
            v_report = ((visual_run.get("execution") or {}).get("step_outputs") or {}).get("transform", {}).get(
                "report"
            ) or {}
            c_report = ((cli_out.get("step_outputs") or {}).get("transform") or {}).get("report") or {}
            checks.append(
                {
                    "id": "visual_equivalent_cli",
                    "ok": bool(
                        cli_out.get("ok")
                        and visual_run.get("ok")
                        and v_report.get("row_count") == c_report.get("row_count") == 2
                        and (cli_work / "report.json").is_file()
                        and (work_root / "visual_reporting" / "report.json").is_file()
                        and bool(v_sha)
                        and bool(c_sha)
                    ),
                    "detail": {
                        "visual_sha256": v_sha,
                        "cli_sha256": c_sha,
                        "visual_rows": v_report.get("row_count"),
                        "cli_rows": c_report.get("row_count"),
                        "note": "Same FreeForge runner path; effect ledger shared model.",
                    },
                }
            )

            # 4) Dual trigger refused
            refused = refuse_nodered_independent_trigger(
                {"trigger_kind": "inject_repeat", "scheduler_owner": "nodered"}
            )
            http_refused = _http_json(
                f"{base}/api/refuse-dual-trigger",
                {"kind": "nodered_cron"},
            )
            checks.append(
                {
                    "id": "refuse_nodered_independent_trigger",
                    "ok": bool(
                        refused.get("refused")
                        and http_refused.get("refused")
                        and refused.get("scheduler_owner") == "openclaw_gateway"
                    ),
                    "detail": {"refused": refused, "http": http_refused},
                }
            )

            # 5) Node-RED export has no repeat/cron; secrets scrubbed
            exported = export_nodered_flow(
                bridge_base_url=base,
                workflow_id="visual_reporting",
                workflow={
                    **loaded["workflow"],
                    "password": "should-not-persist",
                    "api_key": "leak",
                },
            )
            nodes = (exported.get("flow") or {}).get("nodes") or []
            inject = next((n for n in nodes if n.get("type") == "inject"), {})
            flow_text = json.dumps(exported.get("flow"))
            checks.append(
                {
                    "id": "nodered_export_no_schedule_no_secrets",
                    "ok": bool(
                        exported.get("ok")
                        and exported.get("repeat_configured") is False
                        and inject.get("repeat") == ""
                        and inject.get("crontab") == ""
                        and "should-not-persist" not in flow_text
                        and (exported.get("flow") or {}).get("freeforge", {}).get("secrets_in_flow") is False
                    ),
                    "detail": {
                        "inject_repeat": inject.get("repeat"),
                        "crontab": inject.get("crontab"),
                        "freeforge": (exported.get("flow") or {}).get("freeforge"),
                    },
                }
            )

            # 6) Inline secret strip on save
            dirty = create_simple_reporting_workflow(workflow_id="secret_test")
            dirty["api_key"] = "raw-secret-value"
            scrubbed = strip_inline_secrets(dirty)
            saved = save_workflow(dirty, wf_root)
            on_disk = json.loads((wf_root / "secret_test" / "workflow.json").read_text(encoding="utf-8"))
            checks.append(
                {
                    "id": "secrets_outside_exported_flows",
                    "ok": bool(
                        "raw-secret-value" not in json.dumps(scrubbed)
                        and on_disk.get("api_key", "").startswith("secret_ref:")
                        and saved.get("secrets_inline") is False
                    ),
                    "detail": {"api_key_on_disk": on_disk.get("api_key")},
                }
            )

        finally:
            server.shutdown()
            server.server_close()

        # 7) Removing visual interface: workflows + schedule owner remain
        # (server stopped = visual removed; saved workflows still listed)
        rem = remove_visual_leaves_workflows(wf_root)
        still = load_saved("visual_reporting", wf_root)
        # Re-run saved workflow without visual server (CLI path)
        post_work = tmp_path / "post_remove"
        post_work.mkdir()
        (post_work / "records.json").write_text(
            json.dumps([{"id": "z", "label": "Z", "value": 1}], indent=2) + "\n",
            encoding="utf-8",
        )
        post = run_workflow(
            still["workflow"],
            inputs={},
            work_dir=post_work,
            available_capabilities={
                "local.read",
                "local.write",
                "local.artifact",
                "human.decide",
            },
        )
        checks.append(
            {
                "id": "remove_visual_workflows_and_schedule_remain",
                "ok": bool(
                    rem.get("visual_package_required") is False
                    and rem.get("saved_workflows_remain") is True
                    and still.get("ok")
                    and post.get("ok")
                    and rem.get("scheduled_execution_owner") == "openclaw_gateway"
                    and len(list_workflows(wf_root)) >= 1
                ),
                "detail": {
                    "workflow_count": rem.get("workflow_count"),
                    "post_remove_run_ok": post.get("ok"),
                    "scheduler_owner": rem.get("scheduled_execution_owner"),
                },
            }
        )

    passed = sum(1 for c in checks if c["ok"])
    return {
        "suite": "visual-accept",
        "passed": passed,
        "failed": len(checks) - passed,
        "ok": passed == len(checks),
        "checks": checks,
        "note": "Optional Node-RED; simple local form is the FreeForge visual bridge.",
    }
