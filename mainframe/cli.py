"""MAINFRAME command-line interface — stdlib argparse only."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from mainframe import __version__
from mainframe.ai import invoke_disabled, probe_free_inference, provider_audit, run_ai_step
from mainframe.automation import list_tasks, run_task
from mainframe.config import COST_POSTURE, ROOT, ensure_state, load_config
from mainframe.cost_gate import gate_self_test
from mainframe.demos import run_all_demos
from mainframe.doctor import run_doctor
from mainframe.eligibility import dependency_migration_rows, is_loopback_url
from mainframe.connectors import call_operation, list_connectors, run_connectors_accept
from mainframe.docreport import run_docreport_accept, run_pipeline as run_docreport_pipeline
from mainframe.promote import (
    build_reporting_trace,
    promote_trace,
    run_promote_accept,
    run_promoted,
)
from mainframe.visual import bridge_status, evaluate_nodered_optional, run_visual_accept
from mainframe.faults import publish_failure_matrix, run_faults_accept
from mainframe.editor import (
    apply_verified_patch,
    attach_selection,
    attach_unsaved_buffer,
    cancel_task,
    chat_to_task,
    propose_reviewable_diffs,
    resume_task,
    run_editor_accept,
    void_evaluation_summary,
)
from mainframe.dashboard import (
    build_dashboard,
    resume_task as dashboard_resume,
    run_dashboard_accept,
    start_dashboard,
    stop_task as dashboard_stop,
    task_detail,
)
from mainframe.projects import (
    apply_retention,
    create_project,
    delete_project,
    export_project,
    get_project,
    list_projects,
    preview_affected_records,
    run_projects_accept,
    set_retention,
    update_egress,
)
from mainframe.workload_eval import run_heldout_eval, run_workload_eval_accept
from mainframe.costaudit import run_cost_audit, run_costaudit_accept
from mainframe.release import run_release_accept, run_release_package
from mainframe.recommend import run_recommend, run_recommend_accept
from mainframe.surfaces import run_surfaces, run_surfaces_accept
from mainframe.discovery import (
    activate_connector,
    list_shortlist_ids,
    run_discovery_accept,
    search_catalog,
    snapshot_status,
)
from mainframe.freeforge import discover_apis, freeforge_status, load_pins, run_spike
from mainframe.scorecard import run_scorecard
from mainframe.codeintel import (
    callers as codeintel_callers,
    definition_at,
    dependency_api,
    diagnostics as codeintel_diagnostics,
    file_imports,
    lookup_symbol,
    reject_absent_call,
    run_codeintel_accept,
    signature as codeintel_signature,
    tool_status as codeintel_status,
)
from mainframe.contracts import build_contract, run_contracts_accept, start_contract
from mainframe.context import assemble_context, run_context_accept
from mainframe.depmap import get_or_build as depmap_get, plan_verification, run_depmap_accept
from mainframe.memory import mark_rejected, remember, retrieve, revalidate, run_memory_accept
from mainframe.patching import apply_batch, inspect_and_snapshot, rollback_batch, run_patching_accept
from mainframe.tools import expose_for_task, invoke, list_tools, run_tools_accept
from mainframe.verify import reproduce_failure, run_verify_accept, verify_repair
from mainframe.local_model import (
    confirm_pull,
    download_plan,
    local_model_status,
    run_benchmarks,
    run_local_model_accept,
    select_candidate,
    verify_protocol,
)
from mainframe.providers import (
    get_broker,
    investigation_report,
    list_adapters,
    live_or_pause,
    run_protocol_fixture,
    run_providers_accept,
)
from mainframe.quota import AdmissionController, ActualUsage, UsageEstimate, run_quota_accept
from mainframe.modeleval import (
    build_and_route,
    discover_eligible_models,
    run_eval,
    run_modeleval_accept,
)
from mainframe.controller import Budgets, run_controller, run_controller_accept
from mainframe.codingloop import load_checkpoint, run_coding_loop, run_codingloop_accept
from mainframe.review import review_changes, run_review_accept
from mainframe.cache import (
    cached_model_response,
    cached_repo_scan,
    cached_retrieve,
    run_cache_accept,
)
from mainframe.durable import plan_task, recover, run_durable_accept, DurableStore
from mainframe.boundaries import boundary_report, run_boundaries_accept, spawn_bounded
from mainframe.secretdata import get_facility, redact_for_surface, run_secretdata_accept
from mainframe.capabilities import run_capabilities_accept
from mainframe.browser import run_browser_accept, run_website_maintenance_demo, playwright_status
from mainframe.codingbench import run_codingbench, run_codingbench_accept
from mainframe.workflows import (
    dry_run_plan,
    run_workflow,
    run_workflow_ai_accept,
    run_workflow_resilience_accept,
    run_workflows_accept,
    validate_workflow,
)
from mainframe.workflows.load import load_fixture, load_workflow
from mainframe.schedule import (
    probe_openclaw_automations_cli,
    run_schedule_accept,
    schedule_local_report,
)
from mainframe.schedule.dispatcher import fire_job
from mainframe.schedule.report import write_local_report
from mainframe.schedule.store import ScheduleStore
from mainframe.triggers import run_triggers_accept
from mainframe.inventory import file_range, overview, run_inventory_accept, scan_repository
from mainframe.retrieval import retrieve, run_retrieval_accept
from mainframe.workspace import inspect_workspace


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2))


def cmd_status(_: argparse.Namespace) -> int:
    ensure_state()
    cfg = load_config()
    probe = probe_free_inference()
    _print_json(
        {
            "name": "MAINFRAME",
            "version": __version__,
            "root": str(ROOT),
            "cost_posture": COST_POSTURE,
            "ai_probe": probe.to_dict(),
            "automation_tasks": list_tasks(),
            "config_ai_mode": cfg.get("ai", {}).get("mode"),
            "config_ai_provider": cfg.get("ai", {}).get("provider"),
            "credentials_required": False,
            "hosted_service_required": False,
        }
    )
    return 0


def cmd_audit(_: argparse.Namespace) -> int:
    """Dependency / migration audit — disabled routes are visible, not hidden."""
    ensure_state()
    _print_json(
        {
            "contract": "strict_free_only",
            "provider_audit": provider_audit(),
            "dependency_migration_table": dependency_migration_rows(),
            "cost_posture": COST_POSTURE,
        }
    )
    return 0


def cmd_inspect(_: argparse.Namespace) -> int:
    report = inspect_workspace()
    _print_json(report.to_dict())
    return 0


def cmd_tasks(_: argparse.Namespace) -> int:
    _print_json({"tasks": list_tasks()})
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    params: dict[str, Any] = {}
    if args.param:
        for item in args.param:
            if "=" not in item:
                print(f"Invalid --param {item!r}; expected key=value", file=sys.stderr)
                return 2
            key, value = item.split("=", 1)
            params[key] = value
    result = run_task(args.task, params)
    _print_json(result.to_dict())
    return 0 if result.ok else 1


def cmd_ai(args: argparse.Namespace) -> int:
    if args.ai_command == "probe":
        result = probe_free_inference()
        _print_json(result.to_dict())
        # paused/disabled is not a failure of the system — honest report is success
        return 0
    if args.ai_command == "ask":
        out = run_ai_step(args.prompt)
        _print_json(out)
        if out.get("paused"):
            return 0  # pause is expected/allowed
        return 0 if out.get("ok") else 1
    if args.ai_command == "refuse":
        # Prove disabled routes exist and hard-refuse (not merely hidden).
        out = invoke_disabled(args.provider_id)
        _print_json(out)
        return 0 if out.get("refused") and out.get("fallback_used") is False else 1
    print("Unknown ai subcommand", file=sys.stderr)
    return 2


def cmd_scorecard(args: argparse.Namespace) -> int:
    """Run Layer-C workload baselines; competitors remain unmeasured."""
    payload = run_scorecard(trials=args.trials)
    _print_json(payload)
    return 0 if payload.get("ok") else 1


def cmd_doctor(_: argparse.Namespace) -> int:
    """Measure Windows host environment; no secrets, downloads, or startup mutations."""
    report = run_doctor()
    _print_json(report)
    return 0 if report.get("ok") else 1


def cmd_gate(_: argparse.Namespace) -> int:
    """Central capability/cost gate self-test (blocks paid/alias/expired before dispatch)."""
    report = gate_self_test()
    _print_json(report)
    return 0 if report.get("ok") else 1


def cmd_demo(_: argparse.Namespace) -> int:
    """Offline deterministic demos + mock repair + failure/cancel/AI-pause paths."""
    report = run_all_demos()
    _print_json(report)
    return 0 if report.get("ok") else 1


def cmd_inventory(args: argparse.Namespace) -> int:
    """Repository inventory via Git/rg/FS — hashes + provenance; no embeddings."""
    from pathlib import Path

    if args.inventory_command == "accept":
        out = run_inventory_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1

    root = Path(args.root).resolve() if getattr(args, "root", None) else ROOT
    if args.inventory_command == "scan":
        out = scan_repository(root, incremental=not getattr(args, "full", False))
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.inventory_command == "overview":
        out = overview(root)
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.inventory_command == "file-range":
        out = file_range(root, args.path, args.start, args.end)
        _print_json(out)
        return 0 if out.get("ok") else 1
    print("Unknown inventory subcommand", file=sys.stderr)
    return 2


def cmd_retrieve(args: argparse.Namespace) -> int:
    """Local issue→code retrieval (exact/lexical; optional measured FTS5)."""
    from pathlib import Path

    if args.retrieve_command == "accept":
        out = run_retrieval_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.retrieve_command == "search":
        root = Path(args.root).resolve() if args.root else ROOT
        issue = args.issue
        if args.issue_file:
            issue = Path(args.issue_file).read_text(encoding="utf-8")
        if not issue:
            print("Provide --issue or --issue-file", file=sys.stderr)
            return 2
        use_fts: bool | None = None
        if args.fts5 == "on":
            use_fts = True
        elif args.fts5 == "off":
            use_fts = False
        out = retrieve(
            root,
            issue_text=issue,
            goal=args.goal,
            follow_up=args.follow_up,
            use_fts5=use_fts,
            top_k=args.top_k,
        )
        _print_json(out)
        return 0 if out.get("ok") else 1
    print("Unknown retrieve subcommand", file=sys.stderr)
    return 2


def cmd_codeintel(args: argparse.Namespace) -> int:
    """Language tools / parsers for symbols, callers, signatures, deps — no model."""
    from pathlib import Path

    if args.codeintel_command == "accept":
        out = run_codeintel_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.codeintel_command == "status":
        _print_json(codeintel_status())
        return 0

    root = Path(args.root).resolve() if getattr(args, "root", None) else ROOT
    cmd = args.codeintel_command
    if cmd == "lookup":
        out = lookup_symbol(root, args.name, module=args.module)
    elif cmd == "callers":
        out = codeintel_callers(root, args.name, module=args.module)
    elif cmd == "signature":
        out = codeintel_signature(
            root,
            rel_path=args.path,
            line=args.line,
            column=args.column,
            module=args.module,
            name=args.name,
        )
    elif cmd == "definition":
        out = definition_at(root, args.path, args.line, args.column)
    elif cmd == "imports":
        out = file_imports(root, args.path)
    elif cmd == "diagnostics":
        out = codeintel_diagnostics(root)
    elif cmd == "deps":
        out = dependency_api(args.module_name, attr=args.attr, extra_path=args.extra_path)
    elif cmd == "reject-call":
        out = reject_absent_call(args.module_name, args.attr, extra_path=args.extra_path)
    else:
        print("Unknown codeintel subcommand", file=sys.stderr)
        return 2
    _print_json(out)
    return 0 if out.get("ok") else 1


def cmd_depmap(args: argparse.Namespace) -> int:
    """Dependency/test map and verification plan — local cache only."""
    from pathlib import Path

    if args.depmap_command == "accept":
        out = run_depmap_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    root = Path(args.root).resolve() if getattr(args, "root", None) else ROOT
    if args.depmap_command == "build":
        out = depmap_get(root, force=bool(args.force))
        _print_json(
            {
                "ok": out.get("ok"),
                "cache_hit": out.get("cache_hit"),
                "cache_key": out.get("cache_key"),
                "incomplete": out.get("incomplete"),
                "module_count": len(out.get("modules") or {}),
                "edge_count": len(out.get("edges") or {}),
                "test_count": len(out.get("tests") or {}),
                "uncertainty_count": len(out.get("uncertainties") or {}),
                "graph_service_used": out.get("graph_service_used"),
                "absence_not_proven": out.get("absence_not_proven"),
            }
        )
        return 0 if out.get("ok") else 1
    if args.depmap_command == "plan":
        changed = list(args.changed or [])
        if not changed:
            print("Provide --changed path (repeatable)", file=sys.stderr)
            return 2
        out = plan_verification(root, changed, force_rebuild=bool(args.force))
        _print_json(out)
        return 0 if out.get("ok") else 1
    print("Unknown depmap subcommand", file=sys.stderr)
    return 2


def cmd_contract(args: argparse.Namespace) -> int:
    """Build/start task contracts — deterministic classify; ask only when needed."""
    import json
    from pathlib import Path

    if args.contract_command == "accept":
        out = run_contracts_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.contract_command == "build":
        text = args.text or ""
        if args.file:
            text = Path(args.file).read_text(encoding="utf-8")
        iface = json.loads(args.interface) if args.interface else None
        out = build_contract(text, interface=iface)
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.contract_command == "start":
        text = args.text or ""
        if args.file:
            text = Path(args.file).read_text(encoding="utf-8")
        built = build_contract(text)
        if not built.get("ok"):
            _print_json(built)
            return 1
        inputs = {}
        if args.param:
            for item in args.param:
                if "=" in item:
                    k, v = item.split("=", 1)
                    inputs[k] = v
        out = start_contract(built["contract"], inputs=inputs)
        _print_json(out)
        return 0 if out.get("ok") else 1
    print("Unknown contract subcommand", file=sys.stderr)
    return 2


def cmd_context(args: argparse.Namespace) -> int:
    """Progressive context assembly with budget reserves and token report."""
    from pathlib import Path

    if args.context_command == "accept":
        out = run_context_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.context_command == "assemble":
        root = Path(args.root).resolve() if args.root else ROOT
        text = args.text or ""
        if args.file:
            text = Path(args.file).read_text(encoding="utf-8")
        out = assemble_context(
            root,
            request_text=text,
            goal=args.goal or text,
            constrained=bool(args.constrained),
            include_docs_module=args.docs_module,
            include_docs_attr=args.docs_attr,
            probe_inference=not args.no_probe,
        )
        # Avoid dumping huge assembled_text twice unless asked
        if not args.include_text:
            out = {k: v for k, v in out.items() if k != "assembled_text"}
            out["assembled_text_omitted"] = True
        _print_json(out)
        return 0 if out.get("ok") else 1
    print("Unknown context subcommand", file=sys.stderr)
    return 2


def cmd_memory(args: argparse.Namespace) -> int:
    """Local project memory — isolated, hash-revalidated; no hosted storage."""
    import json
    from pathlib import Path

    if args.memory_command == "accept":
        out = run_memory_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    root = Path(args.root).resolve() if getattr(args, "root", None) else ROOT
    if args.memory_command == "remember":
        out = remember(
            root,
            kind=args.kind,
            source_class=args.source_class,
            title=args.title,
            body=args.body,
            scope=json.loads(args.scope) if args.scope else None,
            source_refs=args.ref or [],
            support_paths=args.support or [],
            verification_status=args.status,
            rejected=bool(args.rejected),
            metadata=json.loads(args.metadata) if args.metadata else None,
        )
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.memory_command == "retrieve":
        out = retrieve(
            root,
            query=args.query or "",
            kind=args.kind,
            trusted_only=bool(args.trusted_only),
            limit=args.limit,
        )
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.memory_command == "revalidate":
        out = revalidate(root, entry_id=args.id)
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.memory_command == "reject":
        out = mark_rejected(root, args.id)
        _print_json(out)
        return 0 if out.get("ok") else 1
    print("Unknown memory subcommand", file=sys.stderr)
    return 2


def cmd_tools(args: argparse.Namespace) -> int:
    """Typed tool registry — validate, invoke, audit; optional MCP fingerprint."""
    import json
    from pathlib import Path

    if args.tools_command == "accept":
        out = run_tools_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.tools_command == "list":
        out = (
            expose_for_task(args.task)
            if args.task
            else {"ok": True, "tools": list_tools()}
        )
        _print_json(out)
        return 0
    if args.tools_command == "invoke":
        root = Path(args.root).resolve() if args.root else ROOT
        try:
            raw_args = json.loads(args.args)
        except json.JSONDecodeError:
            raw_args = args.args  # let invoke report malformed_json
        out = invoke(
            args.name,
            raw_args,
            call_id=args.call_id,
            root=root,
            allow_correction=not args.no_correct,
        )
        _print_json(out)
        return 0 if out.get("ok") else 1
    print("Unknown tools subcommand", file=sys.stderr)
    return 2


def cmd_patch(args: argparse.Namespace) -> int:
    """Precise hash-bound patch batches with journal recovery / selective rollback."""
    import json
    from pathlib import Path

    if args.patch_command == "accept":
        out = run_patching_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    root = Path(args.root).resolve() if getattr(args, "root", None) else ROOT
    if args.patch_command == "snapshot":
        paths = list(args.path or [])
        if not paths:
            print("Provide --path (repeatable)", file=sys.stderr)
            return 2
        out = inspect_and_snapshot(root, paths)
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.patch_command == "apply":
        edits = json.loads(Path(args.edits_file).read_text(encoding="utf-8"))
        if not isinstance(edits, list):
            print("edits file must be a JSON array", file=sys.stderr)
            return 2
        out = apply_batch(root, edits, snapshot_id=args.snapshot_id)
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.patch_command == "rollback":
        out = rollback_batch(root, args.batch_id)
        _print_json(out)
        return 0 if out.get("ok") else 1
    print("Unknown patch subcommand", file=sys.stderr)
    return 2


def cmd_verify(args: argparse.Namespace) -> int:
    """Reproduce failures, run targeted/edge checks, bind results to code+env."""
    import json
    from pathlib import Path

    if args.verify_command == "accept":
        out = run_verify_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.verify_command == "reproduce":
        root = Path(args.root).resolve()
        out = reproduce_failure(
            root,
            test_target=args.test,
            pythonpath=args.pythonpath or str(root),
        )
        _print_json(out)
        return 0 if out.get("reproduced") or out.get("run", {}).get("ok") else 1
    if args.verify_command == "run":
        root = Path(args.root).resolve()
        contract = json.loads(Path(args.contract).read_text(encoding="utf-8"))
        out = verify_repair(
            root,
            contract=contract,
            code_paths=list(args.code or []),
            example_tests=list(args.example or []),
            evaluator_tests=list(args.evaluator or []),
            risk=args.risk,
        )
        _print_json(out)
        return 0 if out.get("ok") else 1
    print("Unknown verify subcommand", file=sys.stderr)
    return 2


def cmd_local_model(args: argparse.Namespace) -> int:
    """Optional local Ollama (native /api/chat) or llama.cpp — never required."""
    ensure_state()
    if args.local_model_command == "status":
        out = local_model_status()
        _print_json(out)
        return 0
    if args.local_model_command == "select":
        out = select_candidate()
        _print_json(out)
        return 0
    if args.local_model_command == "protocol":
        out = verify_protocol(model=getattr(args, "model", None))
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.local_model_command == "download-plan":
        out = download_plan(getattr(args, "candidate", None))
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.local_model_command == "pull":
        out = confirm_pull(getattr(args, "candidate", None), confirm=bool(args.confirm_pull))
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.local_model_command == "bench":
        cfg = load_config()
        base = str(cfg.get("ai", {}).get("ollama_base_url", "http://127.0.0.1:11434"))
        out = run_benchmarks(base_url=base, model=getattr(args, "model", None))
        _print_json(out)
        return 0
    if args.local_model_command == "accept":
        out = run_local_model_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    print("Unknown local-model subcommand", file=sys.stderr)
    return 2


def cmd_providers(args: argparse.Namespace) -> int:
    """Investigated hosted provider adapters — fixtures always; live only if eligible."""
    ensure_state()
    if args.providers_command == "investigate":
        _print_json(investigation_report())
        return 0
    if args.providers_command == "list":
        _print_json({"adapters": list_adapters(), "broker": get_broker().status()})
        return 0
    if args.providers_command == "fixture":
        out = run_protocol_fixture(
            args.provider,
            with_tools=bool(args.tools),
            stream=bool(args.stream),
        )
        if hasattr(out, "to_dict"):
            _print_json(out.to_dict())
            return 0 if out.ok else 1
        _print_json([e.to_dict() for e in out])
        return 0
    if args.providers_command == "live":
        from mainframe.providers.types import Message

        out = live_or_pause(args.provider, [Message(role="user", content=args.prompt)])
        _print_json(out.to_dict())
        # Live unverified → pause is success for free-only contract
        return 0 if (out.ok or out.paused or out.refused) and not out.paid_fallback_used else 1
    if args.providers_command == "accept":
        out = run_providers_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    print("Unknown providers subcommand", file=sys.stderr)
    return 2


def cmd_quota(args: argparse.Namespace) -> int:
    """Quota-aware admission — reserve/reconcile on local ledger."""
    ensure_state()
    if args.quota_command == "accept":
        out = run_quota_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    ctl = AdmissionController()
    if args.quota_command == "status":
        key = ctl.bind_bucket(
            provider_id=args.provider,
            entitlement_id=args.entitlement,
            window_id=args.window,
        )
        _print_json(ctl.ledger.snapshot(key))
        return 0
    if args.quota_command == "admit":
        d = ctl.admit(
            provider_id=args.provider,
            estimate=UsageEstimate(
                requests=args.requests,
                tokens=args.tokens,
                context_tokens=args.context,
                tool_overhead_tokens=args.tool_overhead,
                reasoning_overhead_tokens=args.reasoning_overhead,
            ),
            priority=args.priority,
            entitlement_id=args.entitlement,
            window_id=args.window,
        )
        _print_json(d.to_dict())
        return 0 if d.allowed else 1
    if args.quota_command == "reconcile":
        out = ctl.reconcile(
            args.reservation_id,
            ActualUsage(
                requests=args.requests,
                tokens=args.tokens if args.tokens is not None else None,
                context_tokens=args.context if args.context is not None else None,
                tool_overhead_tokens=args.tool_overhead if args.tool_overhead is not None else None,
                reasoning_overhead_tokens=args.reasoning_overhead if args.reasoning_overhead is not None else None,
                unknown=bool(args.unknown),
            ),
        )
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.quota_command == "release":
        out = ctl.release(args.reservation_id, reason=args.reason)
        _print_json(out)
        return 0 if out.get("ok") else 1
    print("Unknown quota subcommand", file=sys.stderr)
    return 2


def cmd_modeleval(args: argparse.Namespace) -> int:
    """Held-out model eval, capability matrix, measured routing."""
    ensure_state()
    if args.modeleval_command == "accept":
        out = run_modeleval_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.modeleval_command == "models":
        _print_json({"models": [m.to_dict() for m in discover_eligible_models()]})
        return 0
    if args.modeleval_command == "run":
        models = [
            m
            for m in discover_eligible_models()
            if m.eligible and m.available and (args.include_live or m.provider_id == "fixture_local")
        ]
        report = run_eval(split=args.split, models=models, use_quota=not args.no_quota)
        if args.route:
            packed = build_and_route(report)
            _print_json({"eval": report, **packed})
        else:
            _print_json(report)
        return 0
    if args.modeleval_command == "route":
        models = [m for m in discover_eligible_models() if m.eligible and m.available]
        # Prefer fixture for offline; include any available local
        fixtures = [m for m in models if m.provider_id == "fixture_local"]
        report = run_eval(split="holdout", models=fixtures or models, use_quota=True)
        packed = build_and_route(report)
        _print_json(packed)
        return 0
    print("Unknown modeleval subcommand", file=sys.stderr)
    return 2


def cmd_controller(args: argparse.Namespace) -> int:
    """Adaptive task controller — deterministic / direct / plan-review."""
    ensure_state()
    if args.controller_command == "accept":
        out = run_controller_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.controller_command == "run":
        task: dict[str, Any] = {
            "goal": args.goal,
            "kind": args.kind,
            "deterministic_op": args.deterministic_op,
            "impact": args.impact,
            "ambiguous": bool(args.ambiguous),
            "bounded": bool(args.bounded),
            "difficult": bool(args.difficult),
            "acceptance": args.acceptance,
        }
        if args.param:
            params = {}
            for item in args.param:
                if "=" in item:
                    k, v = item.split("=", 1)
                    params[k] = v
            task["params"] = params
        budgets = Budgets(
            max_turns=args.max_turns,
            max_tokens=args.max_tokens,
            max_tool_calls=args.max_tools,
            max_elapsed_ms=args.max_elapsed_ms,
        )
        out = run_controller(task, budgets=budgets)
        _print_json(out.to_dict())
        return 0 if out.ok else 1
    print("Unknown controller subcommand", file=sys.stderr)
    return 2


def cmd_codingloop(args: argparse.Namespace) -> int:
    """Coding loop — reproduce → investigate → propose → apply → check → report."""
    ensure_state()
    if args.codingloop_command == "accept":
        out = run_codingloop_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.codingloop_command == "run":
        from pathlib import Path

        workspace = Path(args.workspace).resolve()
        resume = load_checkpoint(args.resume) if args.resume else None
        out = run_coding_loop(
            workspace,
            goal=args.goal,
            max_attempts=args.max_attempts,
            resume_from=resume,
            interrupt_after_phase=args.interrupt_after,
            user_protected_paths=args.protect or None,
        )
        _print_json(out)
        # Proposal-only / interrupted runs are honest failures for --ok semantics
        if out.get("interrupted"):
            return 0
        return 0 if out.get("ok") else 1
    print("Unknown codingloop subcommand", file=sys.stderr)
    return 2


def cmd_review(args: argparse.Namespace) -> int:
    """Gated change review — deterministic first; model only when benefit justifies it."""
    ensure_state()
    if args.review_command == "accept":
        out = run_review_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.review_command == "run":
        from pathlib import Path

        workspace = Path(args.workspace).resolve()
        diffs: list[str] = []
        if args.diff_file:
            diffs.append(Path(args.diff_file).read_text(encoding="utf-8"))
        out = review_changes(
            workspace,
            goal=args.goal,
            unified_diffs=diffs,
            changed_paths=args.path or None,
            impact=args.impact,
            unresolved_high_value=bool(args.unresolved_high_value),
            prior_review_helped=True if args.prior_helped else (False if args.prior_no_help else None),
            patch_author_model_id=args.author_model,
            reviewer_model_id=args.reviewer_model,
            route=args.route,
            human_requirements=args.require or None,
        )
        _print_json(out)
        return 0 if out.get("ok") else 1
    print("Unknown review subcommand", file=sys.stderr)
    return 2


def cmd_cache(args: argparse.Namespace) -> int:
    """Exact-reuse caches — scans, retrieve, tools, workflows, model responses."""
    ensure_state()
    if args.cache_command == "accept":
        out = run_cache_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.cache_command == "scan":
        from pathlib import Path

        out = cached_repo_scan(Path(args.workspace).resolve())
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.cache_command == "retrieve":
        from pathlib import Path

        out = cached_retrieve(
            Path(args.workspace).resolve(),
            issue_text=args.issue,
            goal=args.goal,
        )
        _print_json(out)
        return 0 if out.get("ok", True) else 1
    if args.cache_command == "model":
        from pathlib import Path

        model = {
            "provider_id": args.provider,
            "model_id": args.model_id,
            "model_version": args.model_version,
        }
        out = cached_model_response(
            Path(args.workspace).resolve(),
            prompt=args.prompt,
            model=model,
            freshness_required=bool(args.fresh),
        )
        _print_json(out)
        return 0
    print("Unknown cache subcommand", file=sys.stderr)
    return 2


def cmd_durable(args: argparse.Namespace) -> int:
    """Durable tasks — transitions, leases, receipts, engine status reconcile."""
    ensure_state()
    if args.durable_command == "accept":
        out = run_durable_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.durable_command == "plan":
        store = DurableStore()
        out = plan_task(store, goal=args.goal, destination=args.destination)
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.durable_command == "recover":
        store = DurableStore()
        out = recover(store, args.operation_id)
        _print_json(out)
        return 0 if out.get("ok") else 1
    print("Unknown durable subcommand", file=sys.stderr)
    return 2


def cmd_boundaries(args: argparse.Namespace) -> int:
    """Executable-tool boundaries — paths, process, env, network, resources."""
    ensure_state()
    if args.boundaries_command == "accept":
        out = run_boundaries_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.boundaries_command == "report":
        out = boundary_report(verify=not args.no_verify)
        _print_json(out)
        return 0
    print("Unknown boundaries subcommand", file=sys.stderr)
    return 2


def cmd_secretdata(args: argparse.Namespace) -> int:
    """Secrets facility, redaction, untrusted-data gates, SSRF guards."""
    ensure_state()
    if args.secretdata_command == "accept":
        out = run_secretdata_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.secretdata_command == "status":
        _print_json(get_facility().status())
        return 0
    if args.secretdata_command == "redact":
        out = redact_for_surface(args.text, surface=args.surface)
        _print_json(out)
        return 0 if out.get("ok") else 1
    print("Unknown secretdata subcommand", file=sys.stderr)
    return 2


def cmd_automation_report(args: argparse.Namespace) -> int:
    """Deterministic scheduled report writer (no model, no outbound)."""
    from pathlib import Path

    out = write_local_report(title=args.title, out_path=Path(args.out))
    _print_json(out)
    return 0 if out.get("ok") else 1


def cmd_triggers(args: argparse.Namespace) -> int:
    """File/repo/webhook/poll triggers — typed events bound to fixed jobs."""
    ensure_state()
    if args.triggers_command == "accept":
        out = run_triggers_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    print("Unknown triggers subcommand", file=sys.stderr)
    return 2


def cmd_schedule(args: argparse.Namespace) -> int:
    """OpenClaw-compatible command payloads + FreeForge local deterministic fire."""
    ensure_state()
    if args.schedule_command == "accept":
        out = run_schedule_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.schedule_command == "probe":
        _print_json(probe_openclaw_automations_cli())
        return 0
    if args.schedule_command == "add-report":
        store = ScheduleStore()
        out = schedule_local_report(
            store,
            name=args.name,
            title=args.title,
            at=args.at,
            tz=args.tz,
        )
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.schedule_command == "fire":
        store = ScheduleStore()
        out = fire_job(store, args.job_id, force=bool(args.force))
        _print_json(out)
        return 0 if out.get("ok") else 1
    print("Unknown schedule subcommand", file=sys.stderr)
    return 2


def cmd_workflow(args: argparse.Namespace) -> int:
    """Versioned workflows — validate, dry-run, run fixture, accept."""
    ensure_state()
    if args.workflow_command == "accept":
        out = run_workflows_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.workflow_command == "accept-resilience":
        out = run_workflow_resilience_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.workflow_command == "accept-ai":
        out = run_workflow_ai_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.workflow_command == "validate":
        raw = load_workflow(args.path) if args.path else load_fixture(args.fixture)
        caps = set(args.capability) if args.capability else None
        out = validate_workflow(raw, available_capabilities=caps, strict_capabilities=not args.defer_caps)
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.workflow_command == "plan":
        raw = load_workflow(args.path) if args.path else load_fixture(args.fixture)
        caps = set(args.capability) if args.capability else None
        out = dry_run_plan(raw, available_capabilities=caps, strict_capabilities=not args.defer_caps)
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.workflow_command == "run":
        import tempfile
        from pathlib import Path

        from mainframe.workflows.load import materialize_fixture

        raw = load_workflow(args.path) if args.path else load_fixture(args.fixture)
        work = Path(args.work) if args.work else Path(tempfile.mkdtemp(prefix="mf-wf-run-"))
        if args.fixture and not args.path:
            materialize_fixture(args.fixture, work)
        caps = set(args.capability) if args.capability else None
        out = run_workflow(
            raw,
            inputs={"title": args.title} if args.title else {},
            work_dir=work,
            available_capabilities=caps,
            strict_capabilities=not args.defer_caps,
        )
        _print_json(out)
        return 0 if out.get("ok") else 1
    print("Unknown workflow subcommand", file=sys.stderr)
    return 2


def cmd_codingbench(args: argparse.Namespace) -> int:
    """Held-out coding benchmark — mock integration vs live quality (opt-in)."""
    ensure_state()
    if args.codingbench_command == "accept":
        out = run_codingbench_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.codingbench_command == "run":
        kind = "live_model_quality" if args.live else "mock_integration"
        out = run_codingbench(
            split=args.split,
            measurement_kind=kind,
            include_compare=not args.no_compare,
            publish=not args.no_publish,
        )
        _print_json(out)
        return 0
    print("Unknown codingbench subcommand", file=sys.stderr)
    return 2


def cmd_browser(args: argparse.Namespace) -> int:
    """Playwright browser tools, maintenance demo, acceptance."""
    ensure_state()
    if args.browser_command == "accept":
        out = run_browser_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.browser_command == "status":
        _print_json({"playwright": playwright_status()})
        return 0
    if args.browser_command == "demo":
        out = run_website_maintenance_demo()
        _print_json(out)
        return 0 if out.get("ok") else 1
    print("Unknown browser subcommand", file=sys.stderr)
    return 2


def cmd_capabilities(args: argparse.Namespace) -> int:
    """Scoped capability grants, authorization, revoke, emergency stop."""
    ensure_state()
    if args.capabilities_command == "accept":
        out = run_capabilities_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    print("Unknown capabilities subcommand", file=sys.stderr)
    return 2


def cmd_freeforge(args: argparse.Namespace) -> int:
    if args.freeforge_command == "status":
        _print_json(freeforge_status())
        return 0
    if args.freeforge_command == "spike":
        result = run_spike()
        _print_json(result.to_dict())
        # Spike succeeds when a single engine is selected and nesting is refused.
        ok = (
            result.selected_engine == "openclaw_embedded_agent_runtime"
            and result.rejected_engine == "opencode_acp_worker"
            and result.nested_loops_allowed is False
        )
        return 0 if ok else 1
    if args.freeforge_command == "discover":
        out = discover_apis(args.query, limit=args.limit)
        _print_json(out)
        return 0 if out.get("ok") or out.get("paused") else 1
    print("Unknown freeforge subcommand", file=sys.stderr)
    return 2


def cmd_discovery(args: argparse.Namespace) -> int:
    """Pinned public-apis snapshot discovery + shortlist activation."""
    ensure_state()
    if args.discovery_command == "accept":
        out = run_discovery_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.discovery_command == "status":
        _print_json(snapshot_status())
        return 0
    if args.discovery_command == "search":
        out = search_catalog(args.query or "", limit=args.limit, include_ads=args.include_ads)
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.discovery_command == "shortlist":
        if args.id:
            from mainframe.discovery import classify_shortlist, load_shortlist

            rec = load_shortlist(args.id)
            _print_json(
                {
                    "record": rec,
                    "classify": classify_shortlist(rec, workflow_purpose=args.purpose),
                }
            )
            return 0
        _print_json({"shortlist_ids": list_shortlist_ids()})
        return 0
    if args.discovery_command == "activate":
        out = activate_connector(args.id, workflow_purpose=args.purpose)
        _print_json(out)
        return 0 if out.get("activated") else 1
    print("Unknown discovery subcommand", file=sys.stderr)
    return 2


def cmd_connectors(args: argparse.Namespace) -> int:
    """Verified read-only API connectors — fixtures or live."""
    ensure_state()
    if args.connectors_command == "accept":
        out = run_connectors_accept(try_live=not args.fixtures_only)
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.connectors_command == "list":
        _print_json({"connectors": list_connectors()})
        return 0
    if args.connectors_command == "call":
        out = call_operation(
            args.connector,
            args.op,
            json.loads(args.args) if args.args else {},
            mode=args.mode,
            fixture_scenario=args.fixture,
        )
        _print_json(out)
        return 0 if out.get("ok") else 1
    print("Unknown connectors subcommand", file=sys.stderr)
    return 2


def cmd_docreport(args: argparse.Namespace) -> int:
    """Local document→report: parsers/OCR first; CSV + report; no external auto-post."""
    from pathlib import Path

    ensure_state()
    if args.docreport_command == "accept":
        out = run_docreport_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.docreport_command == "run":
        sources = [Path(p) for p in args.sources]
        out = run_docreport_pipeline(
            sources,
            out_dir=Path(args.out),
            allow_ocr=not args.no_ocr,
            use_ai_semantic=bool(args.ai_semantic),
        )
        _print_json(out)
        return 0 if out.get("ok") else 1
    print("Unknown docreport subcommand", file=sys.stderr)
    return 2


def cmd_promote(args: argparse.Namespace) -> int:
    """Promote accepted task traces into deterministic programs (untrusted until tested)."""
    from pathlib import Path

    ensure_state()
    if args.promote_command == "accept":
        out = run_promote_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.promote_command == "from-reporting":
        out_dir = Path(args.out)
        trace = build_reporting_trace()
        prog = promote_trace(trace, out_dir=out_dir)
        _print_json(prog.to_dict())
        return 0
    if args.promote_command == "run":
        from mainframe.promote.generate import load_program_meta

        prog = load_program_meta(Path(args.program))
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
        out = run_promoted(
            prog,
            payload,
            work_dir=Path(args.work),
            require_trust=not args.allow_untrusted,
        )
        _print_json(out)
        return 0 if out.get("ok") else 1
    print("Unknown promote subcommand", file=sys.stderr)
    return 2


def cmd_visual(args: argparse.Namespace) -> int:
    """Optional removable visual bridge (simple local form; Node-RED optional export)."""
    from pathlib import Path

    from mainframe.config import STATE_DIR
    from mainframe.visual.server import start_bridge
    from mainframe.visual.store import workflows_root

    ensure_state()
    if args.visual_command == "accept":
        out = run_visual_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.visual_command == "status":
        _print_json(bridge_status())
        return 0
    if args.visual_command == "eval-nodered":
        _print_json(evaluate_nodered_optional())
        return 0
    if args.visual_command == "serve":
        host = args.host
        if host not in {"127.0.0.1", "localhost", "::1"}:
            _print_json({"ok": False, "error": "loopback_only"})
            return 2
        wf_root = Path(args.workflows) if args.workflows else workflows_root()
        work = Path(args.work) if args.work else (STATE_DIR / "visual_work")
        work.mkdir(parents=True, exist_ok=True)
        server, _t = start_bridge(host=host, port=args.port, workflows_root=wf_root, work_root=work)
        port = server.server_address[1]
        _print_json(
            {
                "ok": True,
                "url": f"http://127.0.0.1:{port}/",
                "scheduler_owner": "openclaw_gateway",
                "note": "Ctrl+C to stop. Removing this server leaves saved workflows intact.",
            }
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            server.shutdown()
        return 0
    print("Unknown visual subcommand", file=sys.stderr)
    return 2


def cmd_faults(args: argparse.Namespace) -> int:
    """Fault-injection matrix — local deterministic; fixtures ≠ live."""
    ensure_state()
    if args.faults_command == "accept":
        out = run_faults_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.faults_command == "matrix":
        out = publish_failure_matrix()
        _print_json(
            {
                "ok": out.get("ok"),
                "json_path": out.get("json_path"),
                "md_path": out.get("md_path"),
                "passed": (out.get("matrix") or {}).get("passed"),
                "failed": (out.get("matrix") or {}).get("failed"),
                "gate": (out.get("matrix") or {}).get("gate_before_more_connectors"),
            }
        )
        return 0 if out.get("ok") else 1
    print("Unknown faults subcommand", file=sys.stderr)
    return 2


def cmd_dashboard(args: argparse.Namespace) -> int:
    """Local dashboard — status, history, quota, decisions, artifacts, controls."""
    ensure_state()
    if args.dashboard_command == "accept":
        out = run_dashboard_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.dashboard_command == "show":
        _print_json(build_dashboard(project_id=args.project))
        return 0
    if args.dashboard_command == "task":
        _print_json(task_detail(args.id, project_id=args.project))
        return 0
    if args.dashboard_command == "stop":
        _print_json(dashboard_stop(args.id, kind=args.kind))
        return 0
    if args.dashboard_command == "resume":
        _print_json(dashboard_resume(args.id, kind=args.kind))
        return 0
    if args.dashboard_command == "serve":
        started = start_dashboard(host=args.host, port=args.port)
        if not started.get("ok"):
            _print_json(started)
            return 1
        print(f"Dashboard: {started['url']}", flush=True)
        print("Ctrl+C to stop. Notifications: local inbox only.", flush=True)
        try:
            started["thread"].join()
        except KeyboardInterrupt:
            started["server"].shutdown()
            print("Stopped.", flush=True)
        return 0
    print("Unknown dashboard subcommand", file=sys.stderr)
    return 2


def cmd_project(args: argparse.Namespace) -> int:
    """Project workspaces, isolation, egress, retention, export/delete."""
    from pathlib import Path

    ensure_state()
    if args.project_command == "accept":
        out = run_projects_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.project_command == "create":
        out = create_project(
            args.id,
            workspace=args.workspace,
            confidentiality=args.confidentiality,
            retention_days=None if args.retention_days < 0 else args.retention_days,
            display_name=args.name,
        )
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.project_command == "list":
        _print_json({"ok": True, "projects": list_projects()})
        return 0
    if args.project_command == "show":
        rec = get_project(args.id)
        _print_json({"ok": bool(rec), "project": rec})
        return 0 if rec else 1
    if args.project_command == "egress":
        classes = args.allow_class.split(",") if args.allow_class else None
        providers = args.allow_provider.split(",") if args.allow_provider else None
        _print_json(
            update_egress(
                args.id,
                allowed_data_classes_off_device=classes,
                eligible_providers_may_receive=providers,
            )
        )
        return 0
    if args.project_command == "retention":
        days = None if args.days < 0 else args.days
        _print_json(set_retention(args.id, retention_days=days))
        return 0
    if args.project_command == "retention-apply":
        _print_json(apply_retention(args.id, dry_run=not args.confirm))
        return 0
    if args.project_command == "preview":
        _print_json(preview_affected_records(args.id))
        return 0
    if args.project_command == "export":
        dest = Path(args.dest) if args.dest else None
        out = export_project(args.id, dest=dest)
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.project_command == "delete":
        out = delete_project(args.id, confirm=bool(args.confirm), preview_only=not args.confirm)
        _print_json(out)
        return 0 if out.get("ok") else 1
    print("Unknown project subcommand", file=sys.stderr)
    return 2


def cmd_workload_eval(args: argparse.Namespace) -> int:
    """Held-out W1–W3 evaluation, ablations, evidence-gated claims."""
    ensure_state()
    if args.workload_eval_command == "accept":
        out = run_workload_eval_accept(trials=args.trials)
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.workload_eval_command == "run":
        out = run_heldout_eval(trials=args.trials)
        _print_json(
            {
                "ok": out.get("ok"),
                "report_md": out.get("report_md"),
                "report_json": out.get("report_json"),
                "policy_path": out.get("policy_path"),
                "trials_per_cell": out.get("trials_per_cell"),
                "small_sample_acknowledged": out.get("small_sample_acknowledged"),
                "competitors": out.get("competitors"),
                "claims_n": len(out.get("claims") or []),
            }
        )
        return 0 if out.get("ok") else 1
    print("Unknown workload-eval subcommand", file=sys.stderr)
    return 2


def cmd_cost_audit(args: argparse.Namespace) -> int:
    """Reproducible cost audit — hidden paid deps, outbound proofs, hosted-gone."""
    ensure_state()
    if args.cost_audit_command == "accept":
        out = run_costaudit_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.cost_audit_command == "run":
        out = run_cost_audit()
        _print_json(
            {
                "ok": out.get("ok"),
                "report_md": out.get("report_md"),
                "report_json": out.get("report_json"),
                "acceptance": out.get("acceptance"),
                "network_boundary": {
                    "os_network_isolation": (out.get("network_boundary") or {}).get(
                        "os_network_isolation"
                    ),
                    "note": (out.get("network_boundary") or {}).get("note"),
                },
            }
        )
        return 0 if out.get("ok") else 1
    print("Unknown cost-audit subcommand", file=sys.stderr)
    return 2


def cmd_release(args: argparse.Namespace) -> int:
    """Minimal local release: package, smoke, backup, migrate, startup, uninstall."""
    from pathlib import Path

    from mainframe.release.backup import create_backup, restore_backup
    from mainframe.release.credentials import credentials_status
    from mainframe.release.migrate import migrate_saved_workflow, recover_workflow_db
    from mainframe.release.package import build_release_tree
    from mainframe.release.smoke import clean_install_smoke
    from mainframe.release.startup import startup_register, startup_remove, startup_status
    from mainframe.release.uninstall import run_uninstall, uninstall_plan
    from mainframe.release.upgrade import upgrade_check

    ensure_state()
    cmd = args.release_command
    if cmd == "accept":
        out = run_release_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if cmd == "run":
        out = run_release_package(register_startup=not args.skip_startup)
        _print_json(
            {
                "ok": out.get("ok"),
                "release_version": out.get("release_version"),
                "report_md": out.get("report_md"),
                "report_json": out.get("report_json"),
                "acceptance": out.get("acceptance"),
                "package_dest": (out.get("package") or {}).get("dest"),
                "documented_not_tested": out.get("documented_not_tested"),
            }
        )
        return 0 if out.get("ok") else 1
    if cmd == "package":
        out = build_release_tree()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if cmd == "smoke":
        tree = Path(args.tree) if args.tree else None
        if tree is None:
            built = build_release_tree()
            tree = Path(built["dest"])
        out = clean_install_smoke(tree)
        _print_json(out)
        return 0 if out.get("ok") else 1
    if cmd == "backup":
        out = create_backup(include_secrets=bool(args.include_secrets))
        _print_json(out)
        return 0 if out.get("ok") else 1
    if cmd == "restore":
        out = restore_backup(args.archive)
        _print_json(out)
        return 0 if out.get("ok") else 1
    if cmd == "migrate-workflow":
        out = migrate_saved_workflow(
            fixture=args.fixture,
            path=args.path,
        )
        _print_json(out)
        return 0 if out.get("ok") else 1
    if cmd == "migrate-db":
        out = recover_workflow_db()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if cmd == "upgrade-check":
        out = upgrade_check()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if cmd == "credentials-status":
        _print_json(credentials_status())
        return 0
    if cmd == "startup-status":
        _print_json(startup_status())
        return 0
    if cmd == "startup-register":
        out = startup_register(confirm=bool(args.confirm))
        _print_json(out)
        return 0 if out.get("ok") else 1
    if cmd == "startup-remove":
        out = startup_remove()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if cmd == "uninstall-plan":
        _print_json(uninstall_plan())
        return 0
    if cmd == "uninstall":
        out = run_uninstall(
            confirm=bool(args.confirm),
            delete_state=bool(args.delete_state),
            delete_dist=bool(args.delete_dist),
        )
        _print_json(out)
        return 0 if out.get("ok") else 1
    print("Unknown release subcommand", file=sys.stderr)
    return 2


def cmd_recommend(args: argparse.Namespace) -> int:
    """Recommended FreeForge config from measured evidence — three modes."""
    ensure_state()
    if args.recommend_command == "accept":
        out = run_recommend_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.recommend_command == "run":
        out = run_recommend()
        _print_json(
            {
                "ok": out.get("ok"),
                "recommended_mode_id": (out.get("modes") or {}).get("recommended_mode_id"),
                "report_md": out.get("report_md"),
                "report_json": out.get("report_json"),
                "acceptance": out.get("acceptance"),
                "demos": {
                    "coding_ok": ((out.get("demos") or {}).get("coding") or {}).get("ok"),
                    "automation_ok": ((out.get("demos") or {}).get("automation") or {}).get(
                        "ok"
                    ),
                },
            }
        )
        return 0 if out.get("ok") else 1
    print("Unknown recommend subcommand", file=sys.stderr)
    return 2


def cmd_surfaces(args: argparse.Namespace) -> int:
    """Web vs application product surfaces (optional GH Actions/Pages)."""
    from mainframe.surfaces.application import build_application_surface
    from mainframe.surfaces.catalog import surface_catalog
    from mainframe.surfaces.web import build_web_surface

    ensure_state()
    cmd = args.surfaces_command
    if cmd == "accept":
        out = run_surfaces_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if cmd == "run":
        out = run_surfaces()
        _print_json(
            {
                "ok": out.get("ok"),
                "web": out.get("web", {}).get("dest"),
                "application": out.get("application", {}).get("dest"),
                "actions_url": (out.get("github_actions") or {}).get("actions_url_template"),
                "pages_url_optional": (out.get("github_actions") or {}).get(
                    "pages_url_optional"
                ),
                "report_md": out.get("report_md"),
            }
        )
        return 0 if out.get("ok") else 1
    if cmd == "catalog":
        _print_json(surface_catalog())
        return 0
    if cmd == "build-web":
        out = build_web_surface()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if cmd == "build-app":
        out = build_application_surface()
        _print_json(out)
        return 0 if out.get("ok") else 1
    print("Unknown surfaces subcommand", file=sys.stderr)
    return 2


def cmd_editor(args: argparse.Namespace) -> int:
    """Editor↔CLI shared tasks (extension uses supported VS Code APIs)."""
    from pathlib import Path

    from mainframe.editor.bridge import configure_completion, set_diagnostics
    from mainframe.editor.state import EditorTaskStore

    ensure_state()
    if args.editor_command == "accept":
        out = run_editor_accept()
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.editor_command == "eval-void":
        _print_json(void_evaluation_summary())
        return 0
    if args.editor_command == "chat":
        out = chat_to_task(args.text, workspace=Path(args.workspace), source=args.source)
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.editor_command == "select":
        payload = json.loads(args.json)
        out = attach_selection(
            args.task,
            path=payload["path"],
            text=payload["text"],
            start_line=payload.get("start_line"),
            end_line=payload.get("end_line"),
        )
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.editor_command == "buffer":
        payload = json.loads(args.json)
        out = attach_unsaved_buffer(
            args.task,
            path=payload["path"],
            text=payload["text"],
            dirty=bool(payload.get("dirty", True)),
            version=payload.get("version"),
        )
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.editor_command == "propose":
        edits = json.loads(Path(args.edits).read_text(encoding="utf-8"))
        out = propose_reviewable_diffs(args.task, edits)
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.editor_command == "apply":
        out = apply_verified_patch(args.task)
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.editor_command == "cancel":
        out = cancel_task(args.task)
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.editor_command == "resume":
        out = resume_task(args.task)
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.editor_command == "diagnostics":
        diags = json.loads(Path(args.file).read_text(encoding="utf-8"))
        out = set_diagnostics(args.task, diags)
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.editor_command == "completion":
        out = configure_completion(args.task, requested=bool(args.request))
        _print_json(out)
        return 0 if out.get("ok") else 1
    if args.editor_command == "show":
        task = EditorTaskStore().load(args.task)
        _print_json({"ok": task is not None, "task": task})
        return 0 if task else 1
    print("Unknown editor subcommand", file=sys.stderr)
    return 2


def cmd_accept(_: argparse.Namespace) -> int:
    """Built-in acceptance checks — reports real outcomes only."""
    ensure_state()
    checks: list[dict[str, Any]] = []

    # 1) status loads
    try:
        cfg = load_config()
        checks.append(
            {
                "id": "config_loads",
                "ok": bool(cfg.get("cost_posture")),
                "detail": "config.json readable; cost posture present",
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "config_loads", "ok": False, "detail": str(exc)})

    # 2) inspect finds rules
    report = inspect_workspace()
    checks.append(
        {
            "id": "rules_present",
            "ok": any("mainframe-core" in r for r in report.rules),
            "detail": f"rules={report.rules}",
        }
    )

    # 3) deterministic echo
    echo = run_task("echo", {"message": "accept"})
    checks.append(
        {
            "id": "task_echo",
            "ok": echo.ok and echo.output.get("message") == "accept",
            "detail": echo.error or echo.output,
        }
    )

    # 4) checksum runs
    checksum = run_task("workspace-checksum", {})
    checks.append(
        {
            "id": "task_checksum",
            "ok": checksum.ok and bool(checksum.output.get("sha256")),
            "detail": {
                "sha256": checksum.output.get("sha256"),
                "file_count": checksum.output.get("file_count"),
                "error": checksum.error,
            },
        }
    )

    # 5) AI probe honest (any of available/paused/disabled is valid; crash is not)
    probe = probe_free_inference()
    checks.append(
        {
            "id": "ai_probe_honest",
            "ok": probe.status in {"available", "paused", "disabled"},
            "detail": probe.to_dict(),
        }
    )

    # 6) cost posture forbids paid / hosted / promo paths
    posture = COST_POSTURE
    checks.append(
        {
            "id": "cost_posture_zero_required",
            "ok": (
                posture["required_fees"] is False
                and posture["paid_accounts_allowed"] is False
                and posture["trials_allowed"] is False
                and posture["promotional_credits_allowed"] is False
                and posture["paid_fallbacks_allowed"] is False
                and posture["hosted_engines_allowed"] is False
                and posture["cloud_databases_allowed"] is False
                and posture["remote_execution_allowed"] is False
                and posture["analytics_allowed"] is False
                and posture["hosted_search_allowed"] is False
                and posture["cloud_storage_allowed"] is False
                and posture["local_llm_required"] is False
                and posture["deterministic_without_ai"] is True
            ),
            "detail": posture,
        }
    )

    # 7) launch does not require credentials or hosted service
    cfg = load_config()
    ai = cfg.get("ai", {})
    checks.append(
        {
            "id": "launch_without_credentials_or_hosted",
            "ok": (
                "api_key" not in ai
                and ai.get("provider") == "ollama_local"
                and is_loopback_url(str(ai.get("ollama_base_url", "")))
                and cfg.get("automation", {}).get("require_ai") is False
            ),
            "detail": {
                "provider": ai.get("provider"),
                "ollama_base_url": ai.get("ollama_base_url"),
                "require_ai": cfg.get("automation", {}).get("require_ai"),
            },
        }
    )

    # 8) disabled provider route hard-refuses with no fallback
    refused = invoke_disabled("openai_api")
    checks.append(
        {
            "id": "disabled_route_refuses_no_fallback",
            "ok": bool(refused.get("refused")) and refused.get("fallback_used") is False,
            "detail": refused,
        }
    )

    # 9) non-loopback endpoint is not eligible
    from mainframe.eligibility import decide_provider

    remote = decide_provider("ollama_local", "https://api.openai.com/v1")
    checks.append(
        {
            "id": "non_loopback_rejected",
            "ok": remote.eligible is False,
            "detail": remote.to_dict(),
        }
    )

    # 10) audit table present
    rows = dependency_migration_rows()
    checks.append(
        {
            "id": "dependency_table_present",
            "ok": len(rows) >= 5 and any(r["status"] == "disabled" for r in rows),
            "detail": {"row_count": len(rows)},
        }
    )

    # 11) dated scorecard doc exists
    scorecard_docs = list((ROOT / "docs").glob("SCORECARD-*.md"))
    checks.append(
        {
            "id": "dated_scorecard_doc",
            "ok": len(scorecard_docs) >= 1,
            "detail": [str(p.relative_to(ROOT)).replace("\\", "/") for p in scorecard_docs],
        }
    )

    # 12) scorecard runner meets MAINFRAME targets (1 trial for accept speed)
    sc = run_scorecard(trials=1)
    checks.append(
        {
            "id": "scorecard_workloads_baseline",
            "ok": bool(sc.get("ok")),
            "detail": {
                "ok": sc.get("ok"),
                "hypotheses": sc.get("hypotheses"),
                "workloads": [
                    {
                        "workload": w["workload"],
                        "meets": w["meets_mainframe_target"],
                        "competitor_claude_code": w["competitor_claude_code"],
                        "competitor_cursor": w["competitor_cursor"],
                    }
                    for w in sc.get("layers", {}).get("C_end_to_end", [])
                ],
            },
        }
    )

    # 13) FreeForge pins + single coding engine selection
    try:
        pins = load_pins()
        spike = run_spike()
        oc_pin = pins["components"]["openclaw/openclaw"]["pin_commit"]
        void_pin = pins["components"]["voideditor/void"]["pin_commit"]
        api_pin = pins["components"]["public-apis/public-apis"]["pin_commit"]
        checks.append(
            {
                "id": "freeforge_pins_and_engine",
                "ok": (
                    bool(oc_pin)
                    and bool(void_pin)
                    and bool(api_pin)
                    and pins["components"]["voideditor/void"].get("archived") is True
                    and spike.selected_engine == "openclaw_embedded_agent_runtime"
                    and spike.rejected_engine == "opencode_acp_worker"
                    and spike.nested_loops_allowed is False
                    and (ROOT / "docs" / "FREEFORGE.md").is_file()
                    and (ROOT / "docs" / "NOTICES.md").is_file()
                ),
                "detail": {
                    "openclaw_pin": oc_pin,
                    "void_pin": void_pin,
                    "public_apis_pin": api_pin,
                    "selected_engine": spike.selected_engine,
                    "runtime_status": spike.runtime_status,
                    "playwright": spike.playwright_probe.get("status"),
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "freeforge_pins_and_engine", "ok": False, "detail": str(exc)})

    # 14) doctor returns actionable report without forbidden side effects
    try:
        doc = run_doctor()
        findings = doc.get("findings") or []
        checks.append(
            {
                "id": "doctor_windows_env",
                "ok": (
                    doc.get("ok") is True
                    and doc.get("secrets_exposed") is False
                    and doc.get("models_downloaded") is False
                    and doc.get("startup_tasks_enabled") is False
                    and doc.get("performance_benchmarks_claimed") is False
                    and isinstance(doc.get("memory"), dict)
                    and isinstance(doc.get("resource_limits"), dict)
                    and len(findings) >= 1
                    and doc.get("host_context", {}).get("kind") is not None
                ),
                "detail": {
                    "host_kind": doc.get("host_context", {}).get("kind"),
                    "trust_hardware_as_user_pc": doc.get("host_context", {}).get(
                        "trust_hardware_as_user_pc"
                    ),
                    "memory_measured": (doc.get("memory") or {}).get("measured"),
                    "finding_count": len(findings),
                    "recommended_models": (doc.get("model_fit") or {}).get("recommended_ids"),
                    "docker_required": (
                        doc.get("resource_limits") or {}
                    ).get("docker_desktop", {}).get("required_for_core"),
                    "report_path": doc.get("report_path"),
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "doctor_windows_env", "ok": False, "detail": str(exc)})

    # 15) central cost gate blocks paid/alias/expired; no silent spend switch
    try:
        gate = gate_self_test()
        checks.append(
            {
                "id": "cost_gate_blocks_before_dispatch",
                "ok": bool(gate.get("ok")),
                "detail": {
                    "passed": gate.get("passed"),
                    "failed": gate.get("failed"),
                    "case_ids": [c.get("id") for c in gate.get("cases", [])],
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "cost_gate_blocks_before_dispatch", "ok": False, "detail": str(exc)})

    # 16) offline demos + mock repair + pause
    try:
        demos = run_all_demos()
        checks.append(
            {
                "id": "offline_demos_and_mock_repair",
                "ok": bool(demos.get("ok")),
                "detail": {
                    "passed": demos.get("passed"),
                    "failed": demos.get("failed"),
                    "check_ids": [c.get("id") for c in demos.get("checks", [])],
                    "report_path": demos.get("report_path"),
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "offline_demos_and_mock_repair", "ok": False, "detail": str(exc)})

    # 17) repository inventory (git/rg/fs, incremental, no embeddings)
    try:
        inv = run_inventory_accept()
        checks.append(
            {
                "id": "repository_inventory",
                "ok": bool(inv.get("ok")),
                "detail": {
                    "passed": inv.get("passed"),
                    "failed": inv.get("failed"),
                    "check_ids": [c.get("id") for c in inv.get("checks", [])],
                    "failed_ids": [c.get("id") for c in inv.get("checks", []) if not c.get("ok")],
                    "embedding_service_used": inv.get("embedding_service_used"),
                    "model_request_used": inv.get("model_request_used"),
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "repository_inventory", "ok": False, "detail": str(exc)})

    # 18) local issue→code retrieval (exact/lexical; FTS5 only if measured)
    try:
        ret = run_retrieval_accept()
        checks.append(
            {
                "id": "issue_to_code_retrieval",
                "ok": bool(ret.get("ok")),
                "detail": {
                    "passed": ret.get("passed"),
                    "failed": ret.get("failed"),
                    "mean_relevant_file_recall": ret.get("mean_relevant_file_recall"),
                    "mean_context_chars": ret.get("mean_context_chars"),
                    "fts5_policy": ret.get("fts5_policy"),
                    "failed_ids": [c.get("id") for c in ret.get("checks", []) if not c.get("ok")],
                    "remote_vector_db_used": ret.get("remote_vector_db_used"),
                    "paid_embedding_used": ret.get("paid_embedding_used"),
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "issue_to_code_retrieval", "ok": False, "detail": str(exc)})

    # 19) codeintel: duplicate symbols, callers, reject absent dependency API
    try:
        ci = run_codeintel_accept()
        checks.append(
            {
                "id": "codeintel_symbols_callers_deps",
                "ok": bool(ci.get("ok")),
                "detail": {
                    "passed": ci.get("passed"),
                    "failed": ci.get("failed"),
                    "failed_ids": [c.get("id") for c in ci.get("checks", []) if not c.get("ok")],
                    "adapters": ci.get("adapters"),
                    "model_service_used": ci.get("model_service_used"),
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "codeintel_symbols_callers_deps", "ok": False, "detail": str(exc)})

    # 20) dependency/test map: cross-package dependent tests + unresolved dynamic
    try:
        dm = run_depmap_accept()
        checks.append(
            {
                "id": "dependency_test_map",
                "ok": bool(dm.get("ok")),
                "detail": {
                    "passed": dm.get("passed"),
                    "failed": dm.get("failed"),
                    "failed_ids": [c.get("id") for c in dm.get("checks", []) if not c.get("ok")],
                    "graph_service_used": dm.get("graph_service_used"),
                    "model_service_used": dm.get("model_service_used"),
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "dependency_test_map", "ok": False, "detail": str(exc)})

    # 21) task contracts: refactor interface, one question, routine start
    try:
        tc = run_contracts_accept()
        checks.append(
            {
                "id": "task_contracts",
                "ok": bool(tc.get("ok")),
                "detail": {
                    "passed": tc.get("passed"),
                    "failed": tc.get("failed"),
                    "failed_ids": [c.get("id") for c in tc.get("checks", []) if not c.get("ok")],
                    "model_service_used": tc.get("model_service_used"),
                    "separate_label_call": tc.get("separate_label_call"),
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "task_contracts", "ok": False, "detail": str(exc)})

    # 22) progressive context assembly
    try:
        cx = run_context_accept()
        checks.append(
            {
                "id": "progressive_context",
                "ok": bool(cx.get("ok")),
                "detail": {
                    "passed": cx.get("passed"),
                    "failed": cx.get("failed"),
                    "failed_ids": [c.get("id") for c in cx.get("checks", []) if not c.get("ok")],
                    "token_use": cx.get("token_use"),
                    "model_service_used": cx.get("model_service_used"),
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "progressive_context", "ok": False, "detail": str(exc)})

    # 23) local project memory
    try:
        mem = run_memory_accept()
        checks.append(
            {
                "id": "project_memory",
                "ok": bool(mem.get("ok")),
                "detail": {
                    "passed": mem.get("passed"),
                    "failed": mem.get("failed"),
                    "failed_ids": [c.get("id") for c in mem.get("checks", []) if not c.get("ok")],
                    "hosted_storage_used": mem.get("hosted_storage_used"),
                    "model_training_used": mem.get("model_training_used"),
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "project_memory", "ok": False, "detail": str(exc)})

    # 24) typed tool registry
    try:
        tr = run_tools_accept()
        checks.append(
            {
                "id": "typed_tool_registry",
                "ok": bool(tr.get("ok")),
                "detail": {
                    "passed": tr.get("passed"),
                    "failed": tr.get("failed"),
                    "failed_ids": [c.get("id") for c in tr.get("checks", []) if not c.get("ok")],
                    "tool_count": tr.get("tool_count"),
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "typed_tool_registry", "ok": False, "detail": str(exc)})

    # 25) precise patching
    try:
        pt = run_patching_accept()
        checks.append(
            {
                "id": "precise_patching",
                "ok": bool(pt.get("ok")),
                "detail": {
                    "passed": pt.get("passed"),
                    "failed": pt.get("failed"),
                    "failed_ids": [c.get("id") for c in pt.get("checks", []) if not c.get("ok")],
                    "filesystem_atomicity_claimed": pt.get("filesystem_atomicity_claimed"),
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "precise_patching", "ok": False, "detail": str(exc)})

    # 26) verify / repair evaluation
    try:
        vr = run_verify_accept()
        checks.append(
            {
                "id": "verify_repair_pipeline",
                "ok": bool(vr.get("ok")),
                "detail": {
                    "passed": vr.get("passed"),
                    "failed": vr.get("failed"),
                    "failed_ids": [c.get("id") for c in vr.get("checks", []) if not c.get("ok")],
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "verify_repair_pipeline", "ok": False, "detail": str(exc)})

    # 27) optional local-model adapter
    try:
        lm = run_local_model_accept()
        checks.append(
            {
                "id": "local_model_adapter",
                "ok": bool(lm.get("ok")),
                "detail": {
                    "passed": lm.get("passed"),
                    "failed": lm.get("failed"),
                    "live_status": lm.get("live_status"),
                    "failed_ids": [c.get("id") for c in lm.get("checks", []) if not c.get("ok")],
                    "frontier_parity_claimed": lm.get("frontier_parity_claimed"),
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "local_model_adapter", "ok": False, "detail": str(exc)})

    # 28) hosted provider adapters (investigated; live disabled unless eligible)
    try:
        pr = run_providers_accept()
        checks.append(
            {
                "id": "hosted_provider_adapters",
                "ok": bool(pr.get("ok")),
                "detail": {
                    "passed": pr.get("passed"),
                    "failed": pr.get("failed"),
                    "live_verified_any": pr.get("live_verified_any"),
                    "disabled_unverified": (pr.get("investigation") or {}).get("disabled_unverified"),
                    "failed_ids": [c.get("id") for c in pr.get("checks", []) if not c.get("ok")],
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "hosted_provider_adapters", "ok": False, "detail": str(exc)})

    # 29) quota-aware admission control
    try:
        qa = run_quota_accept()
        checks.append(
            {
                "id": "quota_admission",
                "ok": bool(qa.get("ok")),
                "detail": {
                    "passed": qa.get("passed"),
                    "failed": qa.get("failed"),
                    "failed_ids": [c.get("id") for c in qa.get("checks", []) if not c.get("ok")],
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "quota_admission", "ok": False, "detail": str(exc)})

    # 30) model evaluation set + measured routing
    try:
        me = run_modeleval_accept()
        checks.append(
            {
                "id": "model_eval_routing",
                "ok": bool(me.get("ok")),
                "detail": {
                    "passed": me.get("passed"),
                    "failed": me.get("failed"),
                    "failed_ids": [c.get("id") for c in me.get("checks", []) if not c.get("ok")],
                    "route_selected": (me.get("matrix_summary") or {}).get("route_selected"),
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "model_eval_routing", "ok": False, "detail": str(exc)})

    # 31) adaptive task controller
    try:
        ct = run_controller_accept()
        checks.append(
            {
                "id": "adaptive_controller",
                "ok": bool(ct.get("ok")),
                "detail": {
                    "passed": ct.get("passed"),
                    "failed": ct.get("failed"),
                    "failed_ids": [c.get("id") for c in ct.get("checks", []) if not c.get("ok")],
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "adaptive_controller", "ok": False, "detail": str(exc)})

    # 32) coding loop (contracts→retrieve→patch→verify lifecycle)
    try:
        cl = run_codingloop_accept()
        checks.append(
            {
                "id": "coding_loop",
                "ok": bool(cl.get("ok")),
                "detail": {
                    "passed": cl.get("passed"),
                    "failed": cl.get("failed"),
                    "failed_ids": [c.get("id") for c in cl.get("checks", []) if not c.get("ok")],
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "coding_loop", "ok": False, "detail": str(exc)})

    # 33) gated change review (seeded defect + no-gain routes disabled)
    try:
        rv = run_review_accept()
        checks.append(
            {
                "id": "change_review",
                "ok": bool(rv.get("ok")),
                "detail": {
                    "passed": rv.get("passed"),
                    "failed": rv.get("failed"),
                    "failed_ids": [c.get("id") for c in rv.get("checks", []) if not c.get("ok")],
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "change_review", "ok": False, "detail": str(exc)})

    # 34) exact-reuse caches (scan/retrieve/tools/workflow/model)
    try:
        ca = run_cache_accept()
        checks.append(
            {
                "id": "exact_reuse_cache",
                "ok": bool(ca.get("ok")),
                "detail": {
                    "passed": ca.get("passed"),
                    "failed": ca.get("failed"),
                    "failed_ids": [c.get("id") for c in ca.get("checks", []) if not c.get("ok")],
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "exact_reuse_cache", "ok": False, "detail": str(exc)})

    # 35) durable tasks (crash recovery + status reconcile; no duplicate mutation)
    try:
        du = run_durable_accept()
        checks.append(
            {
                "id": "durable_tasks",
                "ok": bool(du.get("ok")),
                "detail": {
                    "passed": du.get("passed"),
                    "failed": du.get("failed"),
                    "failed_ids": [c.get("id") for c in du.get("checks", []) if not c.get("ok")],
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "durable_tasks", "ok": False, "detail": str(exc)})

    # 36) executable-tool boundaries (traversal/symlink/network/runaway)
    try:
        bd = run_boundaries_accept()
        checks.append(
            {
                "id": "exec_boundaries",
                "ok": bool(bd.get("ok")),
                "detail": {
                    "passed": bd.get("passed"),
                    "failed": bd.get("failed"),
                    "failed_ids": [c.get("id") for c in bd.get("checks", []) if not c.get("ok")],
                    "enforced": [
                        e.get("boundary")
                        for e in (bd.get("boundary_report") or {}).get("enforced", [])
                        if e.get("enforced")
                    ],
                    "assumptions": [
                        a.get("boundary")
                        for a in (bd.get("boundary_report") or {}).get("assumptions", [])
                    ],
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "exec_boundaries", "ok": False, "detail": str(exc)})

    # 37) secrets + untrusted data (injection/SSRF/redaction)
    try:
        sd = run_secretdata_accept()
        checks.append(
            {
                "id": "secret_untrusted_data",
                "ok": bool(sd.get("ok")),
                "detail": {
                    "passed": sd.get("passed"),
                    "failed": sd.get("failed"),
                    "failed_ids": [c.get("id") for c in sd.get("checks", []) if not c.get("ok")],
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "secret_untrusted_data", "ok": False, "detail": str(exc)})

    # 38) scoped capabilities (grants, holds, revoke, emergency stop)
    try:
        sc = run_capabilities_accept()
        checks.append(
            {
                "id": "scoped_capabilities",
                "ok": bool(sc.get("ok")),
                "detail": {
                    "passed": sc.get("passed"),
                    "failed": sc.get("failed"),
                    "failed_ids": [c.get("id") for c in sc.get("checks", []) if not c.get("ok")],
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "scoped_capabilities", "ok": False, "detail": str(exc)})

    # 39) Playwright browser tools + site maintenance demo
    try:
        br = run_browser_accept()
        checks.append(
            {
                "id": "playwright_browser_tools",
                "ok": bool(br.get("ok")),
                "detail": {
                    "passed": br.get("passed"),
                    "failed": br.get("failed"),
                    "paused": br.get("paused"),
                    "failed_ids": [c.get("id") for c in br.get("checks", []) if not c.get("ok")],
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "playwright_browser_tools", "ok": False, "detail": str(exc)})

    # 40) held-out coding benchmark (mock harness vs FreeForge; raw publish)
    try:
        cb = run_codingbench_accept()
        checks.append(
            {
                "id": "coding_benchmark_holdout",
                "ok": bool(cb.get("ok")),
                "detail": {
                    "passed": cb.get("passed"),
                    "failed": cb.get("failed"),
                    "report_path": cb.get("report_path"),
                    "priority_fix": cb.get("priority_fix"),
                    "failed_ids": [c.get("id") for c in cb.get("checks", []) if not c.get("ok")],
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "coding_benchmark_holdout", "ok": False, "detail": str(exc)})

    # 41) versioned workflows (validate/dry-run/offline run; AI block preserves outputs)
    try:
        wf = run_workflows_accept()
        checks.append(
            {
                "id": "versioned_workflows",
                "ok": bool(wf.get("ok")),
                "detail": {
                    "passed": wf.get("passed"),
                    "failed": wf.get("failed"),
                    "failed_ids": [c.get("id") for c in wf.get("checks", []) if not c.get("ok")],
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "versioned_workflows", "ok": False, "detail": str(exc)})

    # 42) OpenClaw automation payloads + FreeForge schedule entry
    try:
        sch = run_schedule_accept()
        checks.append(
            {
                "id": "openclaw_schedule_integration",
                "ok": bool(sch.get("ok")),
                "detail": {
                    "passed": sch.get("passed"),
                    "failed": sch.get("failed"),
                    "failed_ids": [c.get("id") for c in sch.get("checks", []) if not c.get("ok")],
                    "computer_must_be_running": bool(sch.get("computer_must_be_running")),
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "openclaw_schedule_integration", "ok": False, "detail": str(exc)})

    # 43) triggers — file/repo/webhook/poll; dedupe; no arbitrary command
    try:
        tr = run_triggers_accept()
        checks.append(
            {
                "id": "event_triggers",
                "ok": bool(tr.get("ok")),
                "detail": {
                    "passed": tr.get("passed"),
                    "failed": tr.get("failed"),
                    "failed_ids": [c.get("id") for c in tr.get("checks", []) if not c.get("ok")],
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "event_triggers", "ok": False, "detail": str(exc)})

    # 44) workflow resilience — checkpoints, resume, delivery vs execution, unknown outcome
    try:
        wfr = run_workflow_resilience_accept()
        checks.append(
            {
                "id": "workflow_resilience",
                "ok": bool(wfr.get("ok")),
                "detail": {
                    "passed": wfr.get("passed"),
                    "failed": wfr.get("failed"),
                    "failed_ids": [c.get("id") for c in wfr.get("checks", []) if not c.get("ok")],
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "workflow_resilience", "ok": False, "detail": str(exc)})

    # 45) typed AI workflow steps — extract/classify/summarize/propose; evidence; offline checkpoint
    try:
        wfa = run_workflow_ai_accept()
        checks.append(
            {
                "id": "workflow_typed_ai_steps",
                "ok": bool(wfa.get("ok")),
                "detail": {
                    "passed": wfa.get("passed"),
                    "failed": wfa.get("failed"),
                    "failed_ids": [c.get("id") for c in wfa.get("checks", []) if not c.get("ok")],
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "workflow_typed_ai_steps", "ok": False, "detail": str(exc)})

    # 46) public-apis pinned snapshot discovery + shortlist activation gates
    try:
        disc = run_discovery_accept()
        checks.append(
            {
                "id": "public_apis_discovery",
                "ok": bool(disc.get("ok")),
                "detail": {
                    "passed": disc.get("passed"),
                    "failed": disc.get("failed"),
                    "failed_ids": [c.get("id") for c in disc.get("checks", []) if not c.get("ok")],
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "public_apis_discovery", "ok": False, "detail": str(exc)})

    # 47) verified read-only API connectors (fixtures + honest live provenance)
    try:
        cn = run_connectors_accept(try_live=True)
        checks.append(
            {
                "id": "api_connectors_readonly",
                "ok": bool(cn.get("ok")),
                "detail": {
                    "passed": cn.get("passed"),
                    "failed": cn.get("failed"),
                    "live_ok_count": cn.get("live_ok_count"),
                    "failed_ids": [c.get("id") for c in cn.get("checks", []) if not c.get("ok")],
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "api_connectors_readonly", "ok": False, "detail": str(exc)})

    # 48) local document→report (clean/scanned/malformed/duplicate; accuracy + unresolved)
    try:
        dr = run_docreport_accept()
        checks.append(
            {
                "id": "document_to_report",
                "ok": bool(dr.get("ok")),
                "detail": {
                    "passed": dr.get("passed"),
                    "failed": dr.get("failed"),
                    "failed_ids": [c.get("id") for c in dr.get("checks", []) if not c.get("ok")],
                    "auto_posted_external": dr.get("auto_posted_external"),
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "document_to_report", "ok": False, "detail": str(exc)})

    # 49) promote accepted traces → deterministic programs (varied inputs; OOC reject)
    try:
        pr = run_promote_accept()
        checks.append(
            {
                "id": "workflow_promotion",
                "ok": bool(pr.get("ok")),
                "detail": {
                    "passed": pr.get("passed"),
                    "failed": pr.get("failed"),
                    "failed_ids": [c.get("id") for c in pr.get("checks", []) if not c.get("ok")],
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "workflow_promotion", "ok": False, "detail": str(exc)})

    # 50) optional visual bridge (simple form; Node-RED eval; ≡ CLI; removable)
    try:
        vis = run_visual_accept()
        checks.append(
            {
                "id": "visual_bridge",
                "ok": bool(vis.get("ok")),
                "detail": {
                    "passed": vis.get("passed"),
                    "failed": vis.get("failed"),
                    "failed_ids": [c.get("id") for c in vis.get("checks", []) if not c.get("ok")],
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "visual_bridge", "ok": False, "detail": str(exc)})

    # 51) fault-injection matrix (local deterministic; connector gate)
    try:
        ft = run_faults_accept()
        checks.append(
            {
                "id": "fault_injection_matrix",
                "ok": bool(ft.get("ok")),
                "detail": {
                    "passed": ft.get("passed"),
                    "failed": ft.get("failed"),
                    "matrix_paths": ft.get("matrix_paths"),
                    "failed_ids": [c.get("id") for c in ft.get("checks", []) if not c.get("ok")],
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "fault_injection_matrix", "ok": False, "detail": str(exc)})

    # 52) editor bridge — shared task state with CLI; Void eval; no duplicate apply
    try:
        ed = run_editor_accept()
        checks.append(
            {
                "id": "editor_bridge",
                "ok": bool(ed.get("ok")),
                "detail": {
                    "passed": ed.get("passed"),
                    "failed": ed.get("failed"),
                    "failed_ids": [c.get("id") for c in ed.get("checks", []) if not c.get("ok")],
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "editor_bridge", "ok": False, "detail": str(exc)})

    # 53) local dashboard — recover blocked without logs; notify failure side-effect safe
    try:
        dash = run_dashboard_accept()
        checks.append(
            {
                "id": "local_dashboard",
                "ok": bool(dash.get("ok")),
                "detail": {
                    "passed": dash.get("passed"),
                    "failed": dash.get("failed"),
                    "failed_ids": [c.get("id") for c in dash.get("checks", []) if not c.get("ok")],
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "local_dashboard", "ok": False, "detail": str(exc)})

    # 54) project isolation — cross-retrieval/session/path/token; export no credentials
    try:
        proj = run_projects_accept()
        checks.append(
            {
                "id": "project_isolation",
                "ok": bool(proj.get("ok")),
                "detail": {
                    "passed": proj.get("passed"),
                    "failed": proj.get("failed"),
                    "failed_ids": [c.get("id") for c in proj.get("checks", []) if not c.get("ok")],
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "project_isolation", "ok": False, "detail": str(exc)})

    # 55) held-out workload eval (repair / site / docreport) + ablations
    try:
        we = run_workload_eval_accept(trials=2)
        checks.append(
            {
                "id": "heldout_workload_eval",
                "ok": bool(we.get("ok")),
                "detail": {
                    "passed": we.get("passed"),
                    "failed": we.get("failed"),
                    "report_md": we.get("report_md"),
                    "failed_ids": [c.get("id") for c in we.get("checks", []) if not c.get("ok")],
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "heldout_workload_eval", "ok": False, "detail": str(exc)})

    # 56) reproducible cost audit (hidden paid deps; outbound proofs; hosted-gone)
    try:
        ca = run_costaudit_accept()
        checks.append(
            {
                "id": "reproducible_cost_audit",
                "ok": bool(ca.get("ok")),
                "detail": {
                    "passed": ca.get("passed"),
                    "failed": ca.get("failed"),
                    "report_md": ca.get("report_md"),
                    "failed_ids": [c.get("id") for c in ca.get("checks", []) if not c.get("ok")],
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"id": "reproducible_cost_audit", "ok": False, "detail": str(exc)})

    passed = sum(1 for c in checks if c["ok"])
    failed = len(checks) - passed
    payload = {
        "suite": "mainframe-accept",
        "passed": passed,
        "failed": failed,
        "ok": failed == 0,
        "checks": checks,
        "offline_report": {
            "works_offline": [
                "status",
                "inspect",
                "tasks",
                "run (deterministic)",
                "accept (non-AI checks)",
                "audit",
                "ai refuse (disabled routes)",
                "scorecard (deterministic W1–W3)",
                "freeforge status/spike + local discovery snapshot",
                "doctor (local measurements)",
                "gate (cost/capability)",
                "demo (deterministic + mock repair offline)",
                "inventory (git/rg/fs hashes; no embeddings)",
                "retrieve (local issue→code; no remote vectors)",
                "codeintel (ast/optional jedi/pyright; no model)",
                "depmap (import/test map; no graph service)",
                "contract (task contracts; deterministic classify)",
                "context (progressive pack; critical preserved)",
                "memory (local project memory; no hosted storage)",
                "tools (typed registry; auditable invoke)",
                "patch (hash-bound batch; selective rollback)",
                "verify (reproduce/edges/integrity; bound results)",
                "local-model status/select/protocol/download-plan (unavailable OK)",
                "providers investigate/fixture (hosted; live disabled unless eligible)",
                "quota admit/status (local ledger; no overspend)",
                "modeleval run/route (holdout; measured routing)",
                "controller run (adaptive modes + budgets)",
                "codingloop run (reproduce→report; checkpoint/resume)",
                "review run (deterministic-first gated review)",
                "cache scan/retrieve/model (exact reuse; project-isolated)",
                "durable plan/recover (leases/receipts; status reconcile)",
                "boundaries report/accept (Job Object + path/network policy)",
                "secretdata status/redact/accept (DPAPI + injection/SSRF gates)",
                "capabilities accept (scoped grants; holds; revoke/emergency stop)",
                "browser status/demo/accept (Playwright tools; site maintenance demo)",
                "codingbench run/accept (held-out coding benchmark; mock vs live separate)",
                "workflow validate/plan/run/accept (versioned graph; FreeForge receipts)",
                "workflow accept-resilience (checkpoints/resume/delivery/unknown)",
                "workflow accept-ai (typed AI steps; evidence; offline checkpoint)",
                "discovery search/shortlist/activate/accept (pinned public-apis snapshot)",
                "connectors list/call/accept (read-only verified APIs + fixtures)",
                "docreport run/accept (local ingest→CSV/report; OCR optional; no auto-post)",
                "promote accept/from-reporting/run (trace→deterministic program; untrusted until tested)",
                "visual status/serve/accept (optional form bridge; Node-RED optional; removable)",
                "faults matrix/accept (local fault injection; failure matrix; connector gate)",
                "editor chat/select/buffer/propose/apply/accept (shared task state; Void eval)",
                "dashboard show/serve/stop/resume/accept (local status; evidence; local notify)",
                "project create/list/export/delete/accept (isolation; egress; retention; no cred export)",
                "workload-eval run/accept (held-out W1–W3; ablations; evidence-gated claims)",
                "cost-audit run/accept (hidden paid deps; outbound proofs; hosted-gone sim)",
                "release run/accept (minimal package; smoke; backup; migrate; startup)",
                "recommend run/accept (FreeForge modes; matrix; coding+automation demos)",
                "surfaces run/accept (web + application packages; optional Actions/Pages)",
                "schedule probe/add-report/fire/accept (OpenClaw command-argv; zero model)",
                "triggers accept (file/repo/webhook/poll; dedupe; bound jobs only)",
            ],
            "requires_eligible_free_inference": [
                "ai ask with local Ollama + installed model",
                "local-model bench against real weights",
                "providers live (only with verified entitlement + broker credential)",
                "modeleval live ollama/llamacpp rows (when runtime available)",
            ],
            "requires_openclaw_gateway": [
                "scheduled coding via selected embedded engine",
            ],
            "ai_probe_observed": probe.to_dict(),
            "layer_b_model_reasoning": "unmeasured",
            "competitor_e2e": "unmeasured",
            "coding_engine_selected": "openclaw_embedded_agent_runtime",
            "coding_engine_rejected": "opencode_acp_worker",
        },
    }
    _print_json(payload)
    return 0 if payload["ok"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mainframe",
        description="MAINFRAME — open-source coding & automation (zero required fees)",
    )
    parser.add_argument("--version", action="version", version=f"MAINFRAME {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="Show version, cost posture, AI probe, tasks")
    p_status.set_defaults(func=cmd_status)

    p_audit = sub.add_parser(
        "audit",
        help="Free-only dependency/migration table; lists disabled routes (not hidden)",
    )
    p_audit.set_defaults(func=cmd_audit)

    p_inspect = sub.add_parser("inspect", help="Read-only inspect of rules, docs, modules")
    p_inspect.set_defaults(func=cmd_inspect)

    p_tasks = sub.add_parser("tasks", help="List deterministic automation tasks")
    p_tasks.set_defaults(func=cmd_tasks)

    p_run = sub.add_parser("run", help="Run a deterministic task")
    p_run.add_argument("task", help="Task name")
    p_run.add_argument(
        "--param",
        action="append",
        default=[],
        help="Task parameter key=value (repeatable)",
    )
    p_run.set_defaults(func=cmd_run)

    p_ai = sub.add_parser("ai", help="Optional free-only AI (pauses if unavailable)")
    ai_sub = p_ai.add_subparsers(dest="ai_command", required=True)
    p_probe = ai_sub.add_parser("probe", help="Probe local free inference; never invents success")
    p_probe.set_defaults(func=cmd_ai)
    p_ask = ai_sub.add_parser("ask", help="Ask local free model or pause")
    p_ask.add_argument("prompt", help="Prompt text")
    p_ask.set_defaults(func=cmd_ai)
    p_refuse = ai_sub.add_parser(
        "refuse",
        help="Invoke a disabled provider id to prove hard refuse (no fallback)",
    )
    p_refuse.add_argument("provider_id", help="Disabled provider id, e.g. openai_api")
    p_refuse.set_defaults(func=cmd_ai)

    p_accept = sub.add_parser("accept", help="Run built-in acceptance checks")
    p_accept.set_defaults(func=cmd_accept)

    p_doc = sub.add_parser(
        "doctor",
        help="Measure Windows host RAM/CPU/disk/tools; set limits; no downloads/startup changes",
    )
    p_doc.set_defaults(func=cmd_doctor)

    p_gate = sub.add_parser(
        "gate",
        help="Capability/cost gate self-test (paid/alias/expired blocked; no silent spend)",
    )
    p_gate.set_defaults(func=cmd_gate)

    p_demo = sub.add_parser(
        "demo",
        help="Offline non-AI demos + mock issue→patch + failure/cancel/AI-pause",
    )
    p_demo.set_defaults(func=cmd_demo)

    p_inv = sub.add_parser(
        "inventory",
        help="Repo inventory (Git/rg/FS hashes); overview + bounded file-range; no embeddings",
    )
    inv_sub = p_inv.add_subparsers(dest="inventory_command", required=True)
    inv_scan = inv_sub.add_parser("scan", help="Scan repository; store hashes + provenance")
    inv_scan.add_argument("--root", default=None, help="Scan root (default: MAINFRAME root)")
    inv_scan.add_argument(
        "--full",
        action="store_true",
        help="Ignore mtime/size reuse (still updates store)",
    )
    inv_scan.set_defaults(func=cmd_inventory)
    inv_ov = inv_sub.add_parser("overview", help="Bounded agent overview (no file bodies)")
    inv_ov.add_argument("--root", default=None)
    inv_ov.set_defaults(func=cmd_inventory)
    inv_fr = inv_sub.add_parser("file-range", help="Bounded line range for one file")
    inv_fr.add_argument("path", help="Repo-relative path")
    inv_fr.add_argument("--start", type=int, default=1)
    inv_fr.add_argument("--end", type=int, default=None)
    inv_fr.add_argument("--root", default=None)
    inv_fr.set_defaults(func=cmd_inventory)
    inv_acc = inv_sub.add_parser("accept", help="Fixture compare + incremental edit work")
    inv_acc.set_defaults(func=cmd_inventory)

    p_ret = sub.add_parser(
        "retrieve",
        help="Local issue→code retrieval (exact/lexical; FTS5 only if measured useful)",
    )
    ret_sub = p_ret.add_subparsers(dest="retrieve_command", required=True)
    ret_search = ret_sub.add_parser("search", help="Retrieve ranked file ranges for an issue")
    ret_search.add_argument("--root", default=None, help="Repo root (default: MAINFRAME)")
    ret_search.add_argument("--goal", required=True, help="User goal (preserved alongside terms)")
    ret_search.add_argument("--issue", default="", help="Issue / stack / error text")
    ret_search.add_argument("--issue-file", default=None, help="Read issue text from file")
    ret_search.add_argument("--follow-up", default=None, help="Targeted follow-up search terms")
    ret_search.add_argument(
        "--fts5",
        choices=("auto", "on", "off"),
        default="auto",
        help="FTS5: auto uses measured policy",
    )
    ret_search.add_argument("--top-k", type=int, default=8)
    ret_search.set_defaults(func=cmd_retrieve)
    ret_acc = ret_sub.add_parser("accept", help="Recall/context fixtures + FTS5 ablation")
    ret_acc.set_defaults(func=cmd_retrieve)

    p_ci = sub.add_parser(
        "codeintel",
        help="Symbols/callers/signatures/deps via AST + optional Jedi/Pyright (no model)",
    )
    ci_sub = p_ci.add_subparsers(dest="codeintel_command", required=True)
    ci_status = ci_sub.add_parser("status", help="Show available language tooling adapters")
    ci_status.set_defaults(func=cmd_codeintel)
    ci_lookup = ci_sub.add_parser("lookup", help="Lookup symbol definitions (disambiguate via --module)")
    ci_lookup.add_argument("name")
    ci_lookup.add_argument("--module", default=None)
    ci_lookup.add_argument("--root", default=None)
    ci_lookup.set_defaults(func=cmd_codeintel)
    ci_callers = ci_sub.add_parser("callers", help="List actual callers of a symbol")
    ci_callers.add_argument("name")
    ci_callers.add_argument("--module", default=None)
    ci_callers.add_argument("--root", default=None)
    ci_callers.set_defaults(func=cmd_codeintel)
    ci_sig = ci_sub.add_parser("signature", help="Inspect signature by name or cursor")
    ci_sig.add_argument("--name", default=None)
    ci_sig.add_argument("--module", default=None)
    ci_sig.add_argument("--path", default=None)
    ci_sig.add_argument("--line", type=int, default=None)
    ci_sig.add_argument("--column", type=int, default=None)
    ci_sig.add_argument("--root", default=None)
    ci_sig.set_defaults(func=cmd_codeintel)
    ci_def = ci_sub.add_parser("definition", help="Goto-definition at path:line:column")
    ci_def.add_argument("path")
    ci_def.add_argument("line", type=int)
    ci_def.add_argument("column", type=int)
    ci_def.add_argument("--root", default=None)
    ci_def.set_defaults(func=cmd_codeintel)
    ci_imp = ci_sub.add_parser("imports", help="List imports for a file")
    ci_imp.add_argument("path")
    ci_imp.add_argument("--root", default=None)
    ci_imp.set_defaults(func=cmd_codeintel)
    ci_diag = ci_sub.add_parser("diagnostics", help="Pyright diagnostics when available")
    ci_diag.add_argument("--root", default=None)
    ci_diag.set_defaults(func=cmd_codeintel)
    ci_deps = ci_sub.add_parser("deps", help="Resolve installed module API / optional attr")
    ci_deps.add_argument("module_name")
    ci_deps.add_argument("--attr", default=None)
    ci_deps.add_argument("--extra-path", default=None)
    ci_deps.set_defaults(func=cmd_codeintel)
    ci_rej = ci_sub.add_parser(
        "reject-call",
        help="Reject a proposed call if attr absent from installed dependency",
    )
    ci_rej.add_argument("module_name")
    ci_rej.add_argument("attr")
    ci_rej.add_argument("--extra-path", default=None)
    ci_rej.set_defaults(func=cmd_codeintel)
    ci_acc = ci_sub.add_parser("accept", help="Duplicate symbols, callers, absent-API reject")
    ci_acc.set_defaults(func=cmd_codeintel)

    p_dm = sub.add_parser(
        "depmap",
        help="Dependency/test map + verification plan (cached locally; no graph service)",
    )
    dm_sub = p_dm.add_subparsers(dest="depmap_command", required=True)
    dm_build = dm_sub.add_parser("build", help="Build or reuse cached map")
    dm_build.add_argument("--root", default=None)
    dm_build.add_argument("--force", action="store_true")
    dm_build.set_defaults(func=cmd_depmap)
    dm_plan = dm_sub.add_parser("plan", help="Affected modules + verify commands for changes")
    dm_plan.add_argument("--root", default=None)
    dm_plan.add_argument(
        "--changed",
        action="append",
        default=[],
        help="Changed path relative to root (repeatable)",
    )
    dm_plan.add_argument("--force", action="store_true", help="Force map rebuild")
    dm_plan.set_defaults(func=cmd_depmap)
    dm_acc = dm_sub.add_parser("accept", help="Cross-package dependent test + dynamic widen")
    dm_acc.set_defaults(func=cmd_depmap)

    p_ct = sub.add_parser(
        "contract",
        help="Task contracts (behavior/scope/checks); deterministic classify; ask sparingly",
    )
    ct_sub = p_ct.add_subparsers(dest="contract_command", required=True)
    ct_build = ct_sub.add_parser("build", help="Build contract from request text")
    ct_build.add_argument("--text", default="", help="Natural-language request")
    ct_build.add_argument("--file", default=None, help="Read request from file")
    ct_build.add_argument(
        "--interface",
        default=None,
        help='JSON interface for refactor, e.g. {"module_path":"m.py","symbols":[...]}',
    )
    ct_build.set_defaults(func=cmd_contract)
    ct_start = ct_sub.add_parser("start", help="Start ready contract / known workflow")
    ct_start.add_argument("--text", default="")
    ct_start.add_argument("--file", default=None)
    ct_start.add_argument("--param", action="append", default=[], help="input key=value")
    ct_start.set_defaults(func=cmd_contract)
    ct_acc = ct_sub.add_parser("accept", help="Refactor/ambiguous/routine contract checks")
    ct_acc.set_defaults(func=cmd_contract)

    p_cx = sub.add_parser(
        "context",
        help="Progressive context pack (contract/overview/symbols/ranges/diagnostics)",
    )
    cx_sub = p_cx.add_subparsers(dest="context_command", required=True)
    cx_as = cx_sub.add_parser("assemble", help="Assemble ranked evidence under a token budget")
    cx_as.add_argument("--root", default=None)
    cx_as.add_argument("--text", default="", help="Issue / request text")
    cx_as.add_argument("--file", default=None)
    cx_as.add_argument("--goal", default=None)
    cx_as.add_argument("--constrained", action="store_true", help="Use tight fixture-like budget")
    cx_as.add_argument("--docs-module", default=None, help="Prefer installed types for module")
    cx_as.add_argument("--docs-attr", default=None)
    cx_as.add_argument("--include-text", action="store_true", help="Include assembled_text in JSON")
    cx_as.add_argument("--no-probe", action="store_true", help="Skip inference probe for actual tokens")
    cx_as.set_defaults(func=cmd_context)
    cx_acc = cx_sub.add_parser("accept", help="Constrained fixture retains fix-critical evidence")
    cx_acc.set_defaults(func=cmd_context)

    p_mem = sub.add_parser(
        "memory",
        help="Local project memory (commands/solutions/failures); hash revalidation; no hosted storage",
    )
    mem_sub = p_mem.add_subparsers(dest="memory_command", required=True)
    mem_rem = mem_sub.add_parser("remember", help="Store an entry with explicit source class")
    mem_rem.add_argument("--root", default=None)
    mem_rem.add_argument(
        "--kind",
        required=True,
        choices=["build_command", "module_responsibility", "accepted_solution", "failure_pattern"],
    )
    mem_rem.add_argument(
        "--source-class",
        required=True,
        choices=["user_instruction", "observation", "hypothesis", "external_text", "generated_summary"],
    )
    mem_rem.add_argument("--title", required=True)
    mem_rem.add_argument("--body", required=True)
    mem_rem.add_argument("--scope", default=None, help="JSON scope object")
    mem_rem.add_argument("--ref", action="append", default=[], help="Source reference path")
    mem_rem.add_argument("--support", action="append", default=[], help="Supporting file for hash")
    mem_rem.add_argument(
        "--status",
        default="unverified",
        choices=["unverified", "verified", "rejected", "expired", "needs_revalidation"],
    )
    mem_rem.add_argument("--rejected", action="store_true")
    mem_rem.add_argument("--metadata", default=None, help="JSON metadata")
    mem_rem.set_defaults(func=cmd_memory)
    mem_get = mem_sub.add_parser("retrieve", help="Retrieve relevant memory for this project")
    mem_get.add_argument("--root", default=None)
    mem_get.add_argument("--query", default="")
    mem_get.add_argument("--kind", default=None)
    mem_get.add_argument("--trusted-only", action="store_true")
    mem_get.add_argument("--limit", type=int, default=20)
    mem_get.set_defaults(func=cmd_memory)
    mem_re = mem_sub.add_parser("revalidate", help="Invalidate entries whose support hashes drifted")
    mem_re.add_argument("--root", default=None)
    mem_re.add_argument("--id", default=None)
    mem_re.set_defaults(func=cmd_memory)
    mem_rj = mem_sub.add_parser("reject", help="Mark entry rejected (never trusted guidance)")
    mem_rj.add_argument("id")
    mem_rj.add_argument("--root", default=None)
    mem_rj.set_defaults(func=cmd_memory)
    mem_acc = mem_sub.add_parser("accept", help="Reuse/invalidate/reject-injection checks")
    mem_acc.set_defaults(func=cmd_memory)

    p_tools = sub.add_parser(
        "tools",
        help="Typed tool registry (search/range/symbols/diagnostics/patch/tests/diff)",
    )
    tools_sub = p_tools.add_subparsers(dest="tools_command", required=True)
    tools_list = tools_sub.add_parser("list", help="List tools (optionally task-filtered)")
    tools_list.add_argument("--task", default=None, help="Task kind for relevance filter")
    tools_list.set_defaults(func=cmd_tools)
    tools_inv = tools_sub.add_parser("invoke", help="Invoke a tool with call_id + JSON args")
    tools_inv.add_argument("name", help="Tool name")
    tools_inv.add_argument("--call-id", required=True, help="Unique operation / tool-call ID")
    tools_inv.add_argument("--args", default="{}", help="JSON object of arguments")
    tools_inv.add_argument("--root", default=None)
    tools_inv.add_argument("--no-correct", action="store_true", help="Disable one bounded correction")
    tools_inv.set_defaults(func=cmd_tools)
    tools_acc = tools_sub.add_parser("accept", help="No side effects on bad calls; auditable valid calls")
    tools_acc.set_defaults(func=cmd_tools)

    p_patch = sub.add_parser(
        "patch",
        help="Precise hash-bound patches (validate batch, journal recover, selective rollback)",
    )
    patch_sub = p_patch.add_subparsers(dest="patch_command", required=True)
    p_snap = patch_sub.add_parser("snapshot", help="Inspect scoped paths into a base snapshot")
    p_snap.add_argument("--root", default=None)
    p_snap.add_argument("--path", action="append", default=[], help="Scoped relative path")
    p_snap.set_defaults(func=cmd_patch)
    p_apply = patch_sub.add_parser("apply", help="Validate then apply edit batch bound to snapshot")
    p_apply.add_argument("--root", default=None)
    p_apply.add_argument("--snapshot-id", required=True)
    p_apply.add_argument(
        "--edits-file",
        required=True,
        help='JSON array of {"path","old","new"} edits',
    )
    p_apply.set_defaults(func=cmd_patch)
    p_rb = patch_sub.add_parser("rollback", help="Selective rollback of agent-owned batch only")
    p_rb.add_argument("batch_id")
    p_rb.add_argument("--root", default=None)
    p_rb.set_defaults(func=cmd_patch)
    p_pacc = patch_sub.add_parser("accept", help="Dup/Unicode/concurrent/interrupt recovery checks")
    p_pacc.set_defaults(func=cmd_patch)

    p_ver = sub.add_parser(
        "verify",
        help="Reproduce failures; targeted/edge/type/regression; bind to code+env",
    )
    ver_sub = p_ver.add_subparsers(dest="verify_command", required=True)
    v_rep = ver_sub.add_parser("reproduce", help="Reproduce failure before repair")
    v_rep.add_argument("--root", required=True)
    v_rep.add_argument("--test", required=True, help="pytest target")
    v_rep.add_argument("--pythonpath", default=None)
    v_rep.set_defaults(func=cmd_verify)
    v_run = ver_sub.add_parser("run", help="Full post-repair verification pipeline")
    v_run.add_argument("--root", required=True)
    v_run.add_argument("--contract", required=True, help="Path to contract JSON")
    v_run.add_argument("--code", action="append", default=[], help="Code path to bind")
    v_run.add_argument("--example", action="append", default=[], help="Example/workspace test path")
    v_run.add_argument(
        "--evaluator",
        action="append",
        default=[],
        help="Evaluator-owned test path (outside editable target)",
    )
    v_run.add_argument("--risk", default="medium", choices=["low", "medium", "high"])
    v_run.set_defaults(func=cmd_verify)
    v_acc = ver_sub.add_parser("accept", help="Edge miss / preexisting / invalidate checks")
    v_acc.set_defaults(func=cmd_verify)

    p_lm = sub.add_parser(
        "local-model",
        help="Optional local Ollama (/api/chat) or llama.cpp — doctor fit, explicit download, bench",
    )
    lm_sub = p_lm.add_subparsers(dest="local_model_command", required=True)
    lm_status = lm_sub.add_parser("status", help="Available or visibly unavailable")
    lm_status.set_defaults(func=cmd_local_model)
    lm_sel = lm_sub.add_parser("select", help="Doctor RAM fit → small candidate (no download)")
    lm_sel.set_defaults(func=cmd_local_model)
    lm_proto = lm_sub.add_parser(
        "protocol",
        help="Verify native protocol, chat template, tools flag, license",
    )
    lm_proto.add_argument("--model", default=None)
    lm_proto.set_defaults(func=cmd_local_model)
    lm_plan = lm_sub.add_parser("download-plan", help="Explicit pull/GGUF steps (never auto)")
    lm_plan.add_argument("--candidate", default=None)
    lm_plan.set_defaults(func=cmd_local_model)
    lm_pull = lm_sub.add_parser("pull", help="Run ollama pull only with --confirm-pull")
    lm_pull.add_argument("--candidate", default=None)
    lm_pull.add_argument(
        "--confirm-pull",
        action="store_true",
        help="Required to actually execute ollama pull",
    )
    lm_pull.set_defaults(func=cmd_local_model)
    lm_bench = lm_sub.add_parser(
        "bench",
        help="Extraction / tool-use / coding latency + client RSS (measured; no frontier claims)",
    )
    lm_bench.add_argument("--model", default=None)
    lm_bench.set_defaults(func=cmd_local_model)
    lm_acc = lm_sub.add_parser("accept", help="Cloud reject / offline mock / no-local-model checks")
    lm_acc.set_defaults(func=cmd_local_model)

    p_prov = sub.add_parser(
        "providers",
        help="Investigated hosted adapters (Groq/Gemini/Mistral) — fixtures; live only if eligible",
    )
    prov_sub = p_prov.add_subparsers(dest="providers_command", required=True)
    pr_inv = prov_sub.add_parser("investigate", help="Account/use/data/models/quotas/billing findings")
    pr_inv.set_defaults(func=cmd_providers)
    pr_list = prov_sub.add_parser("list", help="Adapter feature matrix + broker status")
    pr_list.set_defaults(func=cmd_providers)
    pr_fix = prov_sub.add_parser("fixture", help="Run protocol fixture (no network; unverified_live)")
    pr_fix.add_argument("provider", choices=["groq_cloud", "google_gemini_api", "mistral_api"])
    pr_fix.add_argument("--tools", action="store_true")
    pr_fix.add_argument("--stream", action="store_true")
    pr_fix.set_defaults(func=cmd_providers)
    pr_live = prov_sub.add_parser("live", help="Live only when entitlement+credential; else pause")
    pr_live.add_argument("provider", choices=["groq_cloud", "google_gemini_api", "mistral_api"])
    pr_live.add_argument("prompt", nargs="?", default="ping")
    pr_live.set_defaults(func=cmd_providers)
    pr_acc = prov_sub.add_parser("accept", help="Fixtures + exhaustion pause + unverified live labels")
    pr_acc.set_defaults(func=cmd_providers)

    p_quota = sub.add_parser(
        "quota",
        help="Quota-aware admission (reserve/reconcile; persist; no identity rotation)",
    )
    q_sub = p_quota.add_subparsers(dest="quota_command", required=True)
    q_status = q_sub.add_parser("status", help="Ledger snapshot for a provider window")
    q_status.add_argument("--provider", default="ollama_local")
    q_status.add_argument("--entitlement", default=None)
    q_status.add_argument("--window", default="default")
    q_status.set_defaults(func=cmd_quota)
    q_admit = q_sub.add_parser("admit", help="Reserve estimated usage before dispatch")
    q_admit.add_argument("--provider", default="ollama_local")
    q_admit.add_argument("--entitlement", default=None)
    q_admit.add_argument("--window", default="default")
    q_admit.add_argument("--priority", choices=["interactive", "background"], default="interactive")
    q_admit.add_argument("--requests", type=int, default=1)
    q_admit.add_argument("--tokens", type=int, default=0)
    q_admit.add_argument("--context", type=int, default=0)
    q_admit.add_argument("--tool-overhead", type=int, default=0)
    q_admit.add_argument("--reasoning-overhead", type=int, default=0)
    q_admit.set_defaults(func=cmd_quota)
    q_rec = q_sub.add_parser("reconcile", help="Reconcile actual usage (unknown kept conservatively)")
    q_rec.add_argument("reservation_id")
    q_rec.add_argument("--requests", type=int, default=1)
    q_rec.add_argument("--tokens", type=int, default=None)
    q_rec.add_argument("--context", type=int, default=None)
    q_rec.add_argument("--tool-overhead", type=int, default=None)
    q_rec.add_argument("--reasoning-overhead", type=int, default=None)
    q_rec.add_argument("--unknown", action="store_true")
    q_rec.set_defaults(func=cmd_quota)
    q_rel = q_sub.add_parser("release", help="Release reservation (cancel/timeout path)")
    q_rel.add_argument("reservation_id")
    q_rel.add_argument("--reason", default="cancelled")
    q_rel.set_defaults(func=cmd_quota)
    q_acc = q_sub.add_parser("accept", help="No overspend / retry-or-unknown / priority checks")
    q_acc.set_defaults(func=cmd_quota)

    p_me = sub.add_parser(
        "modeleval",
        help="Held-out model eval + capability matrix + measured routing",
    )
    me_sub = p_me.add_subparsers(dest="modeleval_command", required=True)
    me_models = me_sub.add_parser("models", help="Eligible/available models (local vs account-dependent)")
    me_models.set_defaults(func=cmd_modeleval)
    me_run = me_sub.add_parser("run", help="Run eval split (default holdout)")
    me_run.add_argument("--split", default="holdout", choices=["holdout", "tune"])
    me_run.add_argument("--route", action="store_true", help="Build matrix + routes after eval")
    me_run.add_argument("--include-live", action="store_true", help="Include available ollama/llamacpp")
    me_run.add_argument("--no-quota", action="store_true")
    me_run.set_defaults(func=cmd_modeleval)
    me_route = me_sub.add_parser("route", help="Eval holdout fixtures and write interpretable routes")
    me_route.set_defaults(func=cmd_modeleval)
    me_acc = me_sub.add_parser("accept", help="Measured routing ≠ marketing; FP invalidates")
    me_acc.set_defaults(func=cmd_modeleval)

    p_ctl = sub.add_parser(
        "controller",
        help="Adaptive task controller (deterministic / direct / plan-review + budgets)",
    )
    ctl_sub = p_ctl.add_subparsers(dest="controller_command", required=True)
    ctl_run = ctl_sub.add_parser("run", help="Run one adaptive task")
    ctl_run.add_argument("--goal", default="")
    ctl_run.add_argument("--kind", default="")
    ctl_run.add_argument("--deterministic-op", default=None)
    ctl_run.add_argument("--impact", default="normal", choices=["normal", "high", "critical"])
    ctl_run.add_argument("--ambiguous", action="store_true")
    ctl_run.add_argument("--bounded", action="store_true")
    ctl_run.add_argument("--difficult", action="store_true")
    ctl_run.add_argument("--acceptance", default="pass")
    ctl_run.add_argument("--param", action="append", default=[], help="key=value for deterministic ops")
    ctl_run.add_argument("--max-turns", type=int, default=8)
    ctl_run.add_argument("--max-tokens", type=int, default=4000)
    ctl_run.add_argument("--max-tools", type=int, default=12)
    ctl_run.add_argument("--max-elapsed-ms", type=int, default=30000)
    ctl_run.set_defaults(func=cmd_controller)
    ctl_acc = ctl_sub.add_parser("accept", help="Simple/difficult/no-progress acceptance checks")
    ctl_acc.set_defaults(func=cmd_controller)

    p_cl = sub.add_parser(
        "codingloop",
        help="Coding loop (reproduce→investigate→propose→apply→check→report)",
    )
    cl_sub = p_cl.add_subparsers(dest="codingloop_command", required=True)
    cl_run = cl_sub.add_parser("run", help="Run coding loop on a workspace")
    cl_run.add_argument("--workspace", required=True, help="Workspace root to repair")
    cl_run.add_argument("--goal", required=True, help="Issue / repair goal")
    cl_run.add_argument("--max-attempts", type=int, default=3)
    cl_run.add_argument("--resume", default=None, help="Checkpoint id to resume")
    cl_run.add_argument(
        "--interrupt-after",
        default=None,
        help="Test hook: interrupt after phase (investigate|apply|…)",
    )
    cl_run.add_argument(
        "--protect",
        action="append",
        default=[],
        help="Relative path to preserve (user edit); repeatable",
    )
    cl_run.set_defaults(func=cmd_codingloop)
    cl_acc = cl_sub.add_parser(
        "accept",
        help="Multi-file e2e / impossible stop / resume / honesty checks",
    )
    cl_acc.set_defaults(func=cmd_codingloop)

    p_rev = sub.add_parser(
        "review",
        help="Gated change review (deterministic first; model only if benefit justifies)",
    )
    rev_sub = p_rev.add_subparsers(dest="review_command", required=True)
    rev_run = rev_sub.add_parser("run", help="Review diffs against a workspace")
    rev_run.add_argument("--workspace", required=True)
    rev_run.add_argument("--goal", required=True)
    rev_run.add_argument("--diff-file", default=None, help="Unified diff file to review")
    rev_run.add_argument("--path", action="append", default=[], help="Changed relative path")
    rev_run.add_argument("--impact", default="normal", choices=["normal", "high", "critical"])
    rev_run.add_argument("--unresolved-high-value", action="store_true")
    rev_run.add_argument("--prior-helped", action="store_true")
    rev_run.add_argument("--prior-no-help", action="store_true")
    rev_run.add_argument("--author-model", default=None)
    rev_run.add_argument("--reviewer-model", default=None)
    rev_run.add_argument("--route", default=None)
    rev_run.add_argument("--require", action="append", default=[], help="Human requirement")
    rev_run.set_defaults(func=cmd_review)
    rev_acc = rev_sub.add_parser(
        "accept",
        help="Seeded defect detection / no-gain route disable / ranking checks",
    )
    rev_acc.set_defaults(func=cmd_review)

    p_cache = sub.add_parser(
        "cache",
        help="Exact-reuse caches (scan/retrieve/tools/workflow/model)",
    )
    cache_sub = p_cache.add_subparsers(dest="cache_command", required=True)
    cache_scan = cache_sub.add_parser("scan", help="Cached repository scan")
    cache_scan.add_argument("--workspace", required=True)
    cache_scan.set_defaults(func=cmd_cache)
    cache_ret = cache_sub.add_parser("retrieve", help="Cached issue→code retrieve")
    cache_ret.add_argument("--workspace", required=True)
    cache_ret.add_argument("--issue", required=True)
    cache_ret.add_argument("--goal", required=True)
    cache_ret.set_defaults(func=cmd_cache)
    cache_model = cache_sub.add_parser("model", help="Exact model-response reuse (avoid request)")
    cache_model.add_argument("--workspace", required=True)
    cache_model.add_argument("--prompt", required=True)
    cache_model.add_argument("--provider", default="ollama_local")
    cache_model.add_argument("--model-id", default="local")
    cache_model.add_argument("--model-version", default="1")
    cache_model.add_argument("--fresh", action="store_true", help="Freshness required — no reuse")
    cache_model.set_defaults(func=cmd_cache)
    cache_acc = cache_sub.add_parser(
        "accept",
        help="Repeated read-only less work; source/permission/freshness invalidate",
    )
    cache_acc.set_defaults(func=cmd_cache)

    p_dur = sub.add_parser(
        "durable",
        help="Durable tasks (transitions/leases/receipts; status reconcile)",
    )
    dur_sub = p_dur.add_subparsers(dest="durable_command", required=True)
    dur_plan = dur_sub.add_parser("plan", help="Create a planned durable operation")
    dur_plan.add_argument("--goal", required=True)
    dur_plan.add_argument("--destination", default="local_effect_sink")
    dur_plan.set_defaults(func=cmd_durable)
    dur_rec = dur_sub.add_parser("recover", help="Recover/reconcile after crash or gap")
    dur_rec.add_argument("--operation-id", required=True)
    dur_rec.set_defaults(func=cmd_durable)
    dur_acc = dur_sub.add_parser(
        "accept",
        help="Crash before/during/after-effect recovery; no duplicate mutation",
    )
    dur_acc.set_defaults(func=cmd_durable)

    p_bd = sub.add_parser(
        "boundaries",
        help="Executable-tool boundaries (paths/process/env/network/resources)",
    )
    bd_sub = p_bd.add_subparsers(dest="boundaries_command", required=True)
    bd_rep = bd_sub.add_parser("report", help="Enforced vs assumed boundaries on this host")
    bd_rep.add_argument("--no-verify", action="store_true", help="Skip live Job Object child test")
    bd_rep.set_defaults(func=cmd_boundaries)
    bd_acc = bd_sub.add_parser(
        "accept",
        help="Traversal/symlink/network/runaway attempts; report enforcement",
    )
    bd_acc.set_defaults(func=cmd_boundaries)

    p_sd = sub.add_parser(
        "secretdata",
        help="Local secrets, redaction, untrusted-data gates, SSRF guards",
    )
    sd_sub = p_sd.add_subparsers(dest="secretdata_command", required=True)
    sd_st = sd_sub.add_parser("status", help="Secret facility status (no values)")
    sd_st.set_defaults(func=cmd_secretdata)
    sd_red = sd_sub.add_parser("redact", help="Redact a string for a surface")
    sd_red.add_argument("--surface", required=True, choices=["logs", "traces", "prompts", "screenshots", "exports"])
    sd_red.add_argument("--text", required=True)
    sd_red.set_defaults(func=cmd_secretdata)
    sd_acc = sd_sub.add_parser(
        "accept",
        help="Injection/secrets/SSRF/quoted-data acceptance checks",
    )
    sd_acc.set_defaults(func=cmd_secretdata)

    p_cap = sub.add_parser(
        "capabilities",
        help="Scoped capability grants, recurring auth, holds, revoke, emergency stop",
    )
    cap_sub = p_cap.add_subparsers(dest="capabilities_command", required=True)
    cap_acc = cap_sub.add_parser(
        "accept",
        help="Recurring report without re-prompt; new recipient/destructive held",
    )
    cap_acc.set_defaults(func=cmd_capabilities)

    p_br = sub.add_parser(
        "browser",
        help="Playwright navigation/locators/DOM/screenshots; site maintenance demo",
    )
    br_sub = p_br.add_subparsers(dest="browser_command", required=True)
    br_st = br_sub.add_parser("status", help="Local Playwright probe")
    br_st.set_defaults(func=cmd_browser)
    br_demo = br_sub.add_parser("demo", help="Broken page → patch → verify; external submit held")
    br_demo.set_defaults(func=cmd_browser)
    br_acc = br_sub.add_parser("accept", help="Layout-tolerant locators, missing control, submit hold")
    br_acc.set_defaults(func=cmd_browser)

    p_cb = sub.add_parser(
        "codingbench",
        help="Held-out coding benchmark — harness compare, raw local results",
    )
    cb_sub = p_cb.add_subparsers(dest="codingbench_command", required=True)
    cb_run = cb_sub.add_parser("run", help="Run benchmark (mock integration by default)")
    cb_run.add_argument("--split", default="holdout", choices=["holdout", "tune"])
    cb_run.add_argument("--live", action="store_true", help="Live model quality path (opt-in)")
    cb_run.add_argument("--no-compare", action="store_true", help="Skip fixture-weak comparison")
    cb_run.add_argument("--no-publish", action="store_true", help="Skip writing JSON to .mainframe/runs/")
    cb_run.set_defaults(func=cmd_codingbench)
    cb_acc = cb_sub.add_parser("accept", help="Mock integration accept + publish raw results")
    cb_acc.set_defaults(func=cmd_codingbench)

    p_wf = sub.add_parser(
        "workflow",
        help="Versioned workflows — validate, dry-run plan, local fixture runner",
    )
    wf_sub = p_wf.add_subparsers(dest="workflow_command", required=True)
    wf_val = wf_sub.add_parser("validate", help="Validate workflow graph before execution")
    wf_val.add_argument("--fixture", default="input_to_report")
    wf_val.add_argument("--path", default=None)
    wf_val.add_argument("--capability", action="append", default=[])
    wf_val.add_argument("--defer-caps", action="store_true", help="Treat unavailable caps as warnings")
    wf_val.set_defaults(func=cmd_workflow)
    wf_plan = wf_sub.add_parser("plan", help="Dry-run ordered plan (no side effects)")
    wf_plan.add_argument("--fixture", default="input_to_report")
    wf_plan.add_argument("--path", default=None)
    wf_plan.add_argument("--capability", action="append", default=[])
    wf_plan.add_argument("--defer-caps", action="store_true")
    wf_plan.set_defaults(func=cmd_workflow)
    wf_run = wf_sub.add_parser("run", help="Run local fixture workflow")
    wf_run.add_argument("--fixture", default="input_to_report")
    wf_run.add_argument("--path", default=None)
    wf_run.add_argument("--work", default=None)
    wf_run.add_argument("--title", default="Report")
    wf_run.add_argument("--capability", action="append", default=[])
    wf_run.add_argument("--defer-caps", action="store_true")
    wf_run.set_defaults(func=cmd_workflow)
    wf_acc = wf_sub.add_parser(
        "accept",
        help="Offline input→report; unavailable AI blocks without corrupting outputs",
    )
    wf_acc.set_defaults(func=cmd_workflow)
    wf_res = wf_sub.add_parser(
        "accept-resilience",
        help="Interrupt/resume, failed delivery review, unknown outcome, cancel, concurrency",
    )
    wf_res.set_defaults(func=cmd_workflow)
    wf_ai = wf_sub.add_parser(
        "accept-ai",
        help="Typed AI steps: extract/classify/summarize/propose; evidence; offline checkpoint",
    )
    wf_ai.set_defaults(func=cmd_workflow)

    p_sched = sub.add_parser(
        "schedule",
        help="OpenClaw automation command-argv payloads; FreeForge deterministic fire",
    )
    sch_sub = p_sched.add_subparsers(dest="schedule_command", required=True)
    sch_probe = sch_sub.add_parser("probe", help="Verify installed OpenClaw automations CLI/schema")
    sch_probe.set_defaults(func=cmd_schedule)
    sch_add = sch_sub.add_parser("add-report", help="Schedule local report via exact argv (no shell)")
    sch_add.add_argument("--name", default="local-report")
    sch_add.add_argument("--title", default="Scheduled local report")
    sch_add.add_argument("--at", default="immediate", help="immediate | duration (20m) | ISO")
    sch_add.add_argument("--tz", default=None, help="IANA timezone for offset-less --at")
    sch_add.set_defaults(func=cmd_schedule)
    sch_fire = sch_sub.add_parser("fire", help="Fire a due/forced deterministic command job")
    sch_fire.add_argument("job_id")
    sch_fire.add_argument("--force", action="store_true")
    sch_fire.set_defaults(func=cmd_schedule)
    sch_acc = sch_sub.add_parser(
        "accept",
        help="Schedule report, restart, verify receipt; prove zero model/outbound",
    )
    sch_acc.set_defaults(func=cmd_schedule)

    p_tr = sub.add_parser(
        "triggers",
        help="File/repo/local-webhook/poll triggers with typed events and bound jobs",
    )
    tr_sub = p_tr.add_subparsers(dest="triggers_command", required=True)
    tr_acc = tr_sub.add_parser(
        "accept",
        help="Dedupe→one run; unrelated→none; auth cannot select command",
    )
    tr_acc.set_defaults(func=cmd_triggers)

    p_ar = sub.add_parser(
        "automation-report",
        help="Write deterministic local report (scheduler command target; no AI)",
    )
    p_ar.add_argument("--title", required=True)
    p_ar.add_argument("--out", required=True, help="Output JSON path")
    p_ar.set_defaults(func=cmd_automation_report)

    p_score = sub.add_parser(
        "scorecard",
        help="Run dated Layer-C workload baselines (competitors stay unmeasured)",
    )
    p_score.add_argument(
        "--trials",
        type=int,
        default=5,
        help="Trials per workload for reliability (default 5)",
    )
    p_score.set_defaults(func=cmd_scorecard)

    p_ff = sub.add_parser("freeforge", help="FreeForge thin integration (pins, spike, discovery)")
    ff_sub = p_ff.add_subparsers(dest="freeforge_command", required=True)
    ff_status = ff_sub.add_parser("status", help="Pins, engine selection, SQLite path")
    ff_status.set_defaults(func=cmd_freeforge)
    ff_spike = ff_sub.add_parser("spike", help="Coding-engine spike; refuse nested loops")
    ff_spike.set_defaults(func=cmd_freeforge)
    ff_disc = ff_sub.add_parser(
        "discover",
        help="Search local pinned public-apis snapshot (no endpoint calls)",
    )
    ff_disc.add_argument("--query", default="", help="Substring filter")
    ff_disc.add_argument("--limit", type=int, default=15)
    ff_disc.set_defaults(func=cmd_freeforge)

    p_disc = sub.add_parser(
        "discovery",
        help="Pinned public-apis snapshot; shortlist evidence; activation states",
    )
    disc_sub = p_disc.add_subparsers(dest="discovery_command", required=True)
    disc_status = disc_sub.add_parser("status", help="Snapshot pin, license, entry counts")
    disc_status.set_defaults(func=cmd_discovery)
    disc_search = disc_sub.add_parser("search", help="Local catalog search (never calls listed APIs)")
    disc_search.add_argument("--query", default="")
    disc_search.add_argument("--limit", type=int, default=25)
    disc_search.add_argument("--include-ads", action="store_true")
    disc_search.set_defaults(func=cmd_discovery)
    disc_sl = disc_sub.add_parser("shortlist", help="List shortlist ids or show one record + state")
    disc_sl.add_argument("--id", default=None)
    disc_sl.add_argument(
        "--purpose",
        default="general",
        choices=["general", "commercial", "noncommercial", "research"],
    )
    disc_sl.set_defaults(func=cmd_discovery)
    disc_act = disc_sub.add_parser("activate", help="Activate shortlisted connector if evidence allows")
    disc_act.add_argument("--id", required=True)
    disc_act.add_argument(
        "--purpose",
        default="general",
        choices=["general", "commercial", "noncommercial", "research"],
    )
    disc_act.set_defaults(func=cmd_discovery)
    disc_acc = disc_sub.add_parser("accept", help="Eligible / NC / trial / unavailable acceptance")
    disc_acc.set_defaults(func=cmd_discovery)

    p_conn = sub.add_parser(
        "connectors",
        help="Verified read-only API connectors (typed I/O, fixtures, provenance)",
    )
    conn_sub = p_conn.add_subparsers(dest="connectors_command", required=True)
    conn_list = conn_sub.add_parser("list", help="List connector specs and operations")
    conn_list.set_defaults(func=cmd_connectors)
    conn_call = conn_sub.add_parser("call", help="Call one operation (fixture or live)")
    conn_call.add_argument("--connector", required=True)
    conn_call.add_argument("--op", required=True)
    conn_call.add_argument("--args", default=None, help="JSON object of typed inputs")
    conn_call.add_argument("--mode", choices=["fixture", "live"], default="fixture")
    conn_call.add_argument("--fixture", default="ok", help="Fixture scenario name")
    conn_call.set_defaults(func=cmd_connectors)
    conn_acc = conn_sub.add_parser("accept", help="Fixture drift/quota/pagination + live provenance")
    conn_acc.add_argument(
        "--fixtures-only",
        action="store_true",
        help="Skip live probes (fixtures still cover acceptance cases)",
    )
    conn_acc.set_defaults(func=cmd_connectors)

    p_dr = sub.add_parser(
        "docreport",
        help="Local document→report (ingest/extract/validate/dedupe → CSV + report)",
    )
    dr_sub = p_dr.add_subparsers(dest="docreport_command", required=True)
    dr_run = dr_sub.add_parser("run", help="Run pipeline on local files")
    dr_run.add_argument("sources", nargs="+", help="Input files (csv/tsv/txt/json/jsonl/images)")
    dr_run.add_argument("--out", required=True, help="Output directory for CSV + report")
    dr_run.add_argument("--no-ocr", action="store_true", help="Disable Tesseract/sidecar OCR")
    dr_run.add_argument(
        "--ai-semantic",
        action="store_true",
        help="Request eligible semantic review gate (still queues uncertain fields; no auto-post)",
    )
    dr_run.set_defaults(func=cmd_docreport)
    dr_acc = dr_sub.add_parser(
        "accept",
        help="Clean/scanned/malformed/duplicate fixtures; accuracy + unresolved",
    )
    dr_acc.set_defaults(func=cmd_docreport)

    p_pr = sub.add_parser(
        "promote",
        help="Promote accepted task traces to deterministic programs (untrusted until tested)",
    )
    pr_sub = p_pr.add_subparsers(dest="promote_command", required=True)
    pr_from = pr_sub.add_parser("from-reporting", help="Promote reporting demo trace (emits untrusted program)")
    pr_from.add_argument("--out", required=True, help="Directory for program + metadata")
    pr_from.set_defaults(func=cmd_promote)
    pr_run = pr_sub.add_parser("run", help="Run a promoted program against a JSON payload")
    pr_run.add_argument("--program", required=True, help="Path to *.meta.json")
    pr_run.add_argument("--input", required=True, help="JSON payload path")
    pr_run.add_argument("--work", required=True, help="Work directory for artifacts")
    pr_run.add_argument(
        "--allow-untrusted",
        action="store_true",
        help="Harness only: run before tested/accepted trust",
    )
    pr_run.set_defaults(func=cmd_promote)
    pr_acc = pr_sub.add_parser(
        "accept",
        help="Promote reporting/website; varied inputs; model calls avoided; OOC reject",
    )
    pr_acc.set_defaults(func=cmd_promote)

    p_vis = sub.add_parser(
        "visual",
        help="Optional removable visual bridge (simple local form; Node-RED optional)",
    )
    vis_sub = p_vis.add_subparsers(dest="visual_command", required=True)
    vis_st = vis_sub.add_parser("status", help="Bridge status + Node-RED evaluation summary")
    vis_st.set_defaults(func=cmd_visual)
    vis_ev = vis_sub.add_parser("eval-nodered", help="Core license + node cost evaluation")
    vis_ev.set_defaults(func=cmd_visual)
    vis_sv = vis_sub.add_parser("serve", help="Loopback HTML form (edit/invoke FreeForge only)")
    vis_sv.add_argument("--host", default="127.0.0.1")
    vis_sv.add_argument("--port", type=int, default=8787)
    vis_sv.add_argument("--workflows", default=None, help="Workflow store root (default .mainframe/workflows)")
    vis_sv.add_argument("--work", default=None, help="Run work directory")
    vis_sv.set_defaults(func=cmd_visual)
    vis_acc = vis_sub.add_parser(
        "accept",
        help="Create+execute visually ≡ CLI; dual-trigger refuse; removable",
    )
    vis_acc.set_defaults(func=cmd_visual)

    p_ft = sub.add_parser(
        "faults",
        help="Fault-injection tests + failure matrix (local deterministic)",
    )
    ft_sub = p_ft.add_subparsers(dest="faults_command", required=True)
    ft_mx = ft_sub.add_parser("matrix", help="Run scenarios and publish FAILURE_MATRIX.md/json")
    ft_mx.set_defaults(func=cmd_faults)
    ft_acc = ft_sub.add_parser(
        "accept",
        help="Duplicate/clock/crash/timeout/malformed/expired/quota/lost-ack/cancel matrix",
    )
    ft_acc.set_defaults(func=cmd_faults)

    p_ed = sub.add_parser(
        "editor",
        help="Editor↔CLI shared tasks (VS Code extension; Void reference only)",
    )
    ed_sub = p_ed.add_subparsers(dest="editor_command", required=True)
    ed_ev = ed_sub.add_parser("eval-void", help="Pinned Void license/service evaluation")
    ed_ev.set_defaults(func=cmd_editor)
    ed_chat = ed_sub.add_parser("chat", help="Chat → shared task")
    ed_chat.add_argument("--text", required=True)
    ed_chat.add_argument("--workspace", required=True)
    ed_chat.add_argument("--source", default="cli", choices=["cli", "editor"])
    ed_chat.set_defaults(func=cmd_editor)
    ed_sel = ed_sub.add_parser("select", help="Attach selected-code context")
    ed_sel.add_argument("--task", required=True)
    ed_sel.add_argument("--json", required=True, help="JSON: path,text,start_line,end_line")
    ed_sel.set_defaults(func=cmd_editor)
    ed_buf = ed_sub.add_parser("buffer", help="Preserve unsaved buffer in task state")
    ed_buf.add_argument("--task", required=True)
    ed_buf.add_argument("--json", required=True)
    ed_buf.set_defaults(func=cmd_editor)
    ed_prop = ed_sub.add_parser("propose", help="Validate edits → reviewable diffs")
    ed_prop.add_argument("--task", required=True)
    ed_prop.add_argument("--edits", required=True, help="JSON file of edits")
    ed_prop.set_defaults(func=cmd_editor)
    ed_ap = ed_sub.add_parser("apply", help="Apply verified patch once (deduped by operation_id)")
    ed_ap.add_argument("--task", required=True)
    ed_ap.set_defaults(func=cmd_editor)
    ed_can = ed_sub.add_parser("cancel", help="Cancel task (no new effects)")
    ed_can.add_argument("--task", required=True)
    ed_can.set_defaults(func=cmd_editor)
    ed_res = ed_sub.add_parser("resume", help="Resume non-cancelled task")
    ed_res.add_argument("--task", required=True)
    ed_res.set_defaults(func=cmd_editor)
    ed_diag = ed_sub.add_parser("diagnostics", help="Record diagnostics on task")
    ed_diag.add_argument("--task", required=True)
    ed_diag.add_argument("--file", required=True)
    ed_diag.set_defaults(func=cmd_editor)
    ed_comp = ed_sub.add_parser("completion", help="Budgeted completion gate")
    ed_comp.add_argument("--task", required=True)
    ed_comp.add_argument("--request", action="store_true")
    ed_comp.set_defaults(func=cmd_editor)
    ed_show = ed_sub.add_parser("show", help="Show shared task JSON")
    ed_show.add_argument("--task", required=True)
    ed_show.set_defaults(func=cmd_editor)
    ed_acc = ed_sub.add_parser("accept", help="Shared state / buffers / one patch apply")
    ed_acc.set_defaults(func=cmd_editor)

    p_dash = sub.add_parser(
        "dashboard",
        help="Local dashboard: status, history, quota, decisions, artifacts, controls",
    )
    dash_sub = p_dash.add_subparsers(dest="dashboard_command", required=True)
    dash_show = dash_sub.add_parser("show", help="JSON aggregate of tasks / quota / decisions")
    dash_show.add_argument("--project", default="default")
    dash_show.set_defaults(func=cmd_dashboard)
    dash_task = dash_sub.add_parser("task", help="Task detail + recovery without logs")
    dash_task.add_argument("--id", required=True)
    dash_task.add_argument("--project", default="default")
    dash_task.set_defaults(func=cmd_dashboard)
    dash_stop = dash_sub.add_parser("stop", help="Stop task (no new effects; no retarget)")
    dash_stop.add_argument("--id", required=True)
    dash_stop.add_argument("--kind", default=None)
    dash_stop.set_defaults(func=cmd_dashboard)
    dash_res = dash_sub.add_parser("resume", help="Resume after blocker cleared")
    dash_res.add_argument("--id", required=True)
    dash_res.add_argument("--kind", default=None)
    dash_res.set_defaults(func=cmd_dashboard)
    dash_sv = dash_sub.add_parser("serve", help="Loopback HTML dashboard")
    dash_sv.add_argument("--host", default="127.0.0.1")
    dash_sv.add_argument("--port", type=int, default=8788)
    dash_sv.set_defaults(func=cmd_dashboard)
    dash_acc = dash_sub.add_parser(
        "accept",
        help="Blocked recovery without logs; notify failure does not rerun/mistarget",
    )
    dash_acc.set_defaults(func=cmd_dashboard)

    p_proj = sub.add_parser(
        "project",
        help="Project workspaces, isolation, egress, retention, export/delete",
    )
    proj_sub = p_proj.add_subparsers(dest="project_command", required=True)
    pr_c = proj_sub.add_parser("create", help="Create project with workspace + scoped stores")
    pr_c.add_argument("--id", required=True)
    pr_c.add_argument("--workspace", default=None)
    pr_c.add_argument(
        "--confidentiality",
        default="internal",
        choices=["public", "internal", "confidential", "local_only"],
    )
    pr_c.add_argument("--retention-days", type=int, default=90, help="Use -1 for retain-until-delete")
    pr_c.add_argument("--name", default=None)
    pr_c.set_defaults(func=cmd_project)
    pr_l = proj_sub.add_parser("list", help="List projects")
    pr_l.set_defaults(func=cmd_project)
    pr_s = proj_sub.add_parser("show", help="Show project record + egress policy")
    pr_s.add_argument("--id", required=True)
    pr_s.set_defaults(func=cmd_project)
    pr_e = proj_sub.add_parser("egress", help="Update egress allowlists (secrets never leave)")
    pr_e.add_argument("--id", required=True)
    pr_e.add_argument("--allow-class", default=None, help="Comma-separated data classes")
    pr_e.add_argument("--allow-provider", default=None, help="Comma-separated provider ids")
    pr_e.set_defaults(func=cmd_project)
    pr_r = proj_sub.add_parser("retention", help="Set retention days (-1 = until delete)")
    pr_r.add_argument("--id", required=True)
    pr_r.add_argument("--days", type=int, required=True)
    pr_r.set_defaults(func=cmd_project)
    pr_ra = proj_sub.add_parser("retention-apply", help="Preview or apply retention candidates")
    pr_ra.add_argument("--id", required=True)
    pr_ra.add_argument("--confirm", action="store_true")
    pr_ra.set_defaults(func=cmd_project)
    pr_p = proj_sub.add_parser("preview", help="Preview records affected by export/delete")
    pr_p.add_argument("--id", required=True)
    pr_p.set_defaults(func=cmd_project)
    pr_x = proj_sub.add_parser("export", help="Export project (no credentials/secrets)")
    pr_x.add_argument("--id", required=True)
    pr_x.add_argument("--dest", default=None)
    pr_x.set_defaults(func=cmd_project)
    pr_d = proj_sub.add_parser("delete", help="Preview or confirm delete (no secure-erase claim)")
    pr_d.add_argument("--id", required=True)
    pr_d.add_argument("--confirm", action="store_true")
    pr_d.set_defaults(func=cmd_project)
    pr_a = proj_sub.add_parser(
        "accept",
        help="Cross-project/session/path/token isolation; export scrub; local-only pause",
    )
    pr_a.set_defaults(func=cmd_project)

    p_we = sub.add_parser(
        "workload-eval",
        help="Held-out repair/site/docreport eval vs minimal+manual; ablations",
    )
    we_sub = p_we.add_subparsers(dest="workload_eval_command", required=True)
    we_run = we_sub.add_parser("run", help="Full held-out comparison + ablations + report")
    we_run.add_argument("--trials", type=int, default=5)
    we_run.set_defaults(func=cmd_workload_eval)
    we_acc = we_sub.add_parser("accept", help="Publish report; evidence-gated claims; disable policy")
    we_acc.add_argument("--trials", type=int, default=3)
    we_acc.set_defaults(func=cmd_workload_eval)

    p_ca = sub.add_parser(
        "cost-audit",
        help="Reproducible cost audit: paid deps, outbound proofs, hosted-gone",
    )
    ca_sub = p_ca.add_subparsers(dest="cost_audit_command", required=True)
    ca_run = ca_sub.add_parser("run", help="Write docs/COST_AUDIT.md + .json")
    ca_run.set_defaults(func=cmd_cost_audit)
    ca_acc = ca_sub.add_parser("accept", help="Prove free-only audit + boundary disables")
    ca_acc.set_defaults(func=cmd_cost_audit)

    p_rel = sub.add_parser(
        "release",
        help="Minimal local release: pins, setup, smoke, backup, migrate, uninstall",
    )
    rel_sub = p_rel.add_subparsers(dest="release_command", required=True)
    rel_run = rel_sub.add_parser("run", help="Build package + smoke + backup/migrate + report")
    rel_run.add_argument(
        "--skip-startup",
        action="store_true",
        help="Skip Task Scheduler register/remove cycle",
    )
    rel_run.set_defaults(func=cmd_release)
    rel_acc = rel_sub.add_parser("accept", help="Acceptance: smoke, restore, migrate, no hosted reqs")
    rel_acc.set_defaults(func=cmd_release)
    rel_pkg = rel_sub.add_parser("package", help="Write dist/release tree only")
    rel_pkg.set_defaults(func=cmd_release)
    rel_smoke = rel_sub.add_parser("smoke", help="Clean-install smoke against a release tree")
    rel_smoke.add_argument("--tree", default=None, help="Release tree path (default: build one)")
    rel_smoke.set_defaults(func=cmd_release)
    rel_bak = rel_sub.add_parser("backup", help="Zip local .mainframe state (no cloud)")
    rel_bak.add_argument("--include-secrets", action="store_true")
    rel_bak.set_defaults(func=cmd_release)
    rel_res = rel_sub.add_parser("restore", help="Restore from a local backup zip")
    rel_res.add_argument("--archive", required=True)
    rel_res.set_defaults(func=cmd_release)
    rel_mw = rel_sub.add_parser("migrate-workflow", help="Migrate a saved workflow to current format")
    rel_mw.add_argument("--fixture", default=None)
    rel_mw.add_argument("--path", default=None)
    rel_mw.set_defaults(func=cmd_release)
    rel_mdb = rel_sub.add_parser("migrate-db", help="Prove additive SQLite migration recovery")
    rel_mdb.set_defaults(func=cmd_release)
    rel_up = rel_sub.add_parser("upgrade-check", help="Upgrade compatibility vs pins")
    rel_up.set_defaults(func=cmd_release)
    rel_cred = rel_sub.add_parser("credentials-status", help="Optional eligible API credential posture")
    rel_cred.set_defaults(func=cmd_release)
    rel_ss = rel_sub.add_parser("startup-status", help="Query removable logon task")
    rel_ss.set_defaults(func=cmd_release)
    rel_sr = rel_sub.add_parser("startup-register", help="Explicit logon task (requires --confirm)")
    rel_sr.add_argument("--confirm", action="store_true")
    rel_sr.set_defaults(func=cmd_release)
    rel_srm = rel_sub.add_parser("startup-remove", help="Remove logon task if present")
    rel_srm.set_defaults(func=cmd_release)
    rel_upl = rel_sub.add_parser("uninstall-plan", help="Show clean uninstall steps")
    rel_upl.set_defaults(func=cmd_release)
    rel_un = rel_sub.add_parser("uninstall", help="Remove startup (+ optional state/dist)")
    rel_un.add_argument("--confirm", action="store_true")
    rel_un.add_argument("--delete-state", action="store_true")
    rel_un.add_argument("--delete-dist", action="store_true")
    rel_un.set_defaults(func=cmd_release)

    p_rec = sub.add_parser(
        "recommend",
        help="Recommended FreeForge config: three modes, matrix, measured demos",
    )
    rec_sub = p_rec.add_subparsers(dest="recommend_command", required=True)
    rec_run = rec_sub.add_parser("run", help="Write docs/FREEFORGE_RECOMMENDED.md + .json")
    rec_run.set_defaults(func=cmd_recommend)
    rec_acc = rec_sub.add_parser(
        "accept",
        help="Prove modes + coding task + reusable automation under free contract",
    )
    rec_acc.set_defaults(func=cmd_recommend)

    p_surf = sub.add_parser(
        "surfaces",
        help="Web (sites/webapps) + application (desktop/store markets) packages",
    )
    surf_sub = p_surf.add_subparsers(dest="surfaces_command", required=True)
    surf_run = surf_sub.add_parser("run", help="Build both surfaces + docs/SURFACES.md")
    surf_run.set_defaults(func=cmd_surfaces)
    surf_acc = surf_sub.add_parser("accept", help="Prove web+app artifacts; CI optional")
    surf_acc.set_defaults(func=cmd_surfaces)
    surf_cat = surf_sub.add_parser("catalog", help="Show surface definitions")
    surf_cat.set_defaults(func=cmd_surfaces)
    surf_web = surf_sub.add_parser("build-web", help="Build dist/web static surface")
    surf_web.set_defaults(func=cmd_surfaces)
    surf_app = surf_sub.add_parser("build-app", help="Build dist/application desktop surface")
    surf_app.set_defaults(func=cmd_surfaces)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
