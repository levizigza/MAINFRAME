"""Acceptance: project isolation — cross-retrieval, sessions, paths, tokens, exports."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from mainframe.projects.bind import bind_tool_run, bind_workflow_run, gate_inference_for_project
from mainframe.projects.cache_ns import get as cache_get
from mainframe.projects.cache_ns import put as cache_put
from mainframe.projects.egress import may_leave_device
from mainframe.projects.export_delete import delete_project, export_project, preview_affected_records
from mainframe.projects.isolation import (
    isolate_memory_put_get,
    refuse_cross_project_retrieval,
    refuse_reused_browser_session,
    resolve_project_path,
)
from mainframe.projects.registry import create_project, get_project, list_projects, projects_root
from mainframe.projects.retention import apply_retention, set_retention
from mainframe.projects.secrets import get_project_secret, store_project_secret
from mainframe.projects.tokens import issue_token, validate_token
from mainframe.tools.invoke import invoke


def run_projects_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    suffix = datetime.now(timezone.utc).strftime("%H%M%S%f")
    pa = f"proj_a_{suffix}"
    pb = f"proj_b_{suffix}"
    pl = f"proj_local_{suffix}"

    ca = create_project(pa, confidentiality="internal", retention_days=30)
    cb = create_project(pb, confidentiality="confidential", retention_days=7)
    cl = create_project(pl, confidentiality="local_only", retention_days=None)
    checks.append(
        {
            "id": "create_project_workspaces",
            "ok": bool(
                ca.get("ok")
                and cb.get("ok")
                and cl.get("ok")
                and get_project(pa)
                and Path(ca["project"]["paths"]["artifacts"]).is_dir()
                and Path(ca["project"]["paths"]["secrets"]).is_dir()
                and Path(ca["project"]["paths"]["browser_profile"]).is_dir()
                and cl["project"].get("local_only") is True
            ),
            "detail": {"a": ca.get("ok"), "b": cb.get("ok"), "local": cl.get("ok")},
        }
    )

    # Explicit binding required
    missing = bind_tool_run(project_id=None, tool_name="read_file")
    bound = bind_tool_run(project_id=pa, tool_name="read_file", arguments={"path": "x"})
    wf_miss = bind_workflow_run(project_id=None, workflow_id="w1")
    wf_ok = bind_workflow_run(project_id=pa, workflow_id="w1")
    tool_res = invoke(
        "workspace.list_tree",
        {},
        call_id=f"proj_bind_{suffix}",
        root=Path(ca["project"]["workspace"]),
        project_id=None,
        require_project=True,
    )
    checks.append(
        {
            "id": "bind_tool_and_workflow",
            "ok": bool(
                missing.get("ok") is False
                and bound.get("ok")
                and wf_miss.get("ok") is False
                and wf_ok.get("ok")
                and tool_res.get("ok") is False
                and (tool_res.get("error_code") == "permission_denied"
                     or "project" in str(tool_res.get("error") or "").lower())
            ),
            "detail": {
                "missing": missing,
                "bound": bound.get("project_id"),
                "wf_miss": wf_miss.get("error"),
                "tool_res_ok": tool_res.get("ok"),
            },
        }
    )

    # Cross-project memory retrieval
    mem = isolate_memory_put_get(
        project_id=pa,
        other_project_id=pb,
        secret_body=f"SECRET_MARKER_{suffix}",
    )
    checks.append(
        {
            "id": "cross_project_retrieval_blocked",
            "ok": bool(
                mem.get("put_ok")
                and mem.get("leaked") is False
                and mem.get("exposed") is False
                and mem.get("cross_allowed") is False
            ),
            "detail": mem,
        }
    )

    # Cache namespace isolation
    cache_put(pa, "k1", {"note": "alpha_only", "api_key": "sk-should-redact"})
    hit_same = cache_get(requester_project_id=pa, resource_project_id=pa, cache_key="k1")
    hit_cross = cache_get(requester_project_id=pb, resource_project_id=pa, cache_key="k1")
    checks.append(
        {
            "id": "cache_cross_project_blocked",
            "ok": bool(
                hit_same.get("hit")
                and hit_same.get("payload", {}).get("note") == "alpha_only"
                and hit_same.get("payload", {}).get("api_key") == "[REDACTED]"
                and hit_cross.get("allowed") is False
                and hit_cross.get("payload") is None
                and hit_cross.get("exposed") is False
            ),
            "detail": {"same": hit_same, "cross": hit_cross},
        }
    )

    # Reused browser session
    sess = refuse_reused_browser_session(
        session_project_id=pa,
        requester_project_id=pb,
        session_id="bs_fake",
    )
    checks.append(
        {
            "id": "reused_browser_session_blocked",
            "ok": bool(
                sess.get("allowed") is False
                and sess.get("exposed") is False
                and sess.get("cookies_or_storage_exposed") is False
            ),
            "detail": sess,
        }
    )

    # Malicious path references
    art = Path(ca["project"]["paths"]["artifacts"])
    (art / "ok.txt").write_text("safe\n", encoding="utf-8")
    # Plant a file in B that A must not reach via ..
    art_b = Path(cb["project"]["paths"]["artifacts"])
    (art_b / "other.txt").write_text("B_ONLY\n", encoding="utf-8")
    good = resolve_project_path(pa, "ok.txt", area="artifacts")
    evil = resolve_project_path(pa, f"../{pb}/artifacts/other.txt", area="artifacts")
    evil2 = resolve_project_path(pa, "../../projects_registry.json", area="artifacts")
    checks.append(
        {
            "id": "malicious_path_references_blocked",
            "ok": bool(
                good.get("allowed")
                and evil.get("allowed") is False
                and evil.get("exposed") is False
                and evil2.get("allowed") is False
            ),
            "detail": {"good": good, "evil": evil, "evil2": evil2},
        }
    )

    # Stale / foreign permission tokens
    tok_a = issue_token(pa, capabilities=["read"], ttl_seconds=60)
    foreign = validate_token(token=tok_a["token"], requester_project_id=pb)
    stale = validate_token(
        token=tok_a["token"],
        requester_project_id=pa,
        now=datetime.now(timezone.utc) + timedelta(hours=2),
    )
    fresh = validate_token(token=tok_a["token"], requester_project_id=pa)
    checks.append(
        {
            "id": "stale_permission_tokens_blocked",
            "ok": bool(
                tok_a.get("ok")
                and foreign.get("allowed") is False
                and foreign.get("exposed") is False
                and foreign.get("data_returned") is None
                and stale.get("allowed") is False
                and stale.get("error") == "stale_permission_token"
                and fresh.get("allowed") is True
            ),
            "detail": {
                "foreign": foreign.get("error"),
                "stale": stale.get("error"),
                "fresh": fresh.get("allowed"),
            },
        }
    )

    # Egress + local-only pause + confidential hosted refuse
    eg_secret = may_leave_device(pa, data_class="secrets", provider_id="ollama_local")
    eg_hosted = may_leave_device(
        pb, data_class="workspace_source", provider_id="openai_api"
    )
    local_pause = gate_inference_for_project(pl, available_local_models=[])
    local_ok = gate_inference_for_project(pl, available_local_models=["ollama_local"])
    checks.append(
        {
            "id": "egress_and_local_only_pause",
            "ok": bool(
                eg_secret.get("allowed") is False
                and eg_hosted.get("allowed") is False
                and eg_hosted.get("free_hosted_inference_ok_for_confidential") is False
                and local_pause.get("paused") is True
                and local_pause.get("fallback_used") is False
                and local_ok.get("inference_allowed") is True
            ),
            "detail": {
                "secret": eg_secret,
                "hosted": eg_hosted,
                "pause": local_pause,
                "local_ok": local_ok,
            },
        }
    )

    # Secrets + grants scoped; export has no credentials
    store_project_secret(pa, "db_pass", "super-secret-password-value")
    leak = get_project_secret(pa, "db_pass", requester_project_id=pb)
    own = get_project_secret(pa, "db_pass", requester_project_id=pa)
    # Write a credential-looking file into artifacts to ensure scrub
    (art / "notes.txt").write_text(
        json.dumps({"api_key": "sk-live-SHOULD_NOT_EXPORT", "hello": "world"}),
        encoding="utf-8",
    )
    prev = preview_affected_records(pa)
    exp = export_project(pa)
    manifest = Path(exp["export_dir"]) / "manifest.json"
    man_text = manifest.read_text(encoding="utf-8") if manifest.is_file() else ""
    notes_exported = Path(exp["export_dir"]) / "artifacts" / "notes.txt"
    notes_text = notes_exported.read_text(encoding="utf-8") if notes_exported.is_file() else ""
    checks.append(
        {
            "id": "export_contains_no_credentials",
            "ok": bool(
                leak.get("exposed") is False
                and leak.get("value") is None
                and own.get("ok")
                and prev.get("credentials_in_preview") is False
                and exp.get("credentials_included") is False
                and exp.get("secrets_included") is False
                and "super-secret-password-value" not in man_text
                and "sk-live-SHOULD_NOT_EXPORT" not in notes_text
                and "[REDACTED_CREDENTIAL]" in notes_text
            ),
            "detail": {
                "leak": leak.get("error"),
                "export_dir": exp.get("export_dir"),
                "notes_scrubbed": "[REDACTED_CREDENTIAL]" in notes_text,
            },
        }
    )

    # Retention + delete preview (no false secure erase)
    set_retention(pa, retention_days=30)
    ret = apply_retention(pa, dry_run=True)
    deleted = delete_project(pb, confirm=False, preview_only=True)
    checks.append(
        {
            "id": "retention_and_delete_preview_honest",
            "ok": bool(
                ret.get("secure_erasure_guaranteed") is False
                and "cannot guarantee secure erasure" in (ret.get("erasure_disclaimer") or "").lower()
                and deleted.get("deleted") is False
                and deleted.get("preview_only") is True
                and deleted.get("secure_erasure_guaranteed") is False
            ),
            "detail": {
                "retention": ret.get("erasure_disclaimer", "")[:80],
                "delete_preview": deleted.get("preview", {}).get("record_counts"),
            },
        }
    )

    # Cross-project grant refusal helper
    cross = refuse_cross_project_retrieval(
        requester_project_id=pb, resource_project_id=pa, resource_kind="grants"
    )
    checks.append(
        {
            "id": "permission_grants_project_bound",
            "ok": bool(cross.get("allowed") is False and cross.get("exposed") is False),
            "detail": cross,
        }
    )

    # Cleanup B with confirm (best-effort); leave A for inspection under projects root
    delete_project(pb, confirm=True)
    still = get_project(pb)
    checks.append(
        {
            "id": "delete_marks_gone_without_secure_claim",
            "ok": still is None,
            "detail": {"still": still, "projects_root": str(projects_root())},
        }
    )

    passed = sum(1 for c in checks if c.get("ok"))
    failed = len(checks) - passed
    return {
        "ok": failed == 0,
        "passed": passed,
        "failed": failed,
        "checks": checks,
        "projects_listed": [p["project_id"] for p in list_projects() if suffix in p["project_id"]],
    }
