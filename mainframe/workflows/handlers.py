"""Builtin deterministic / human / ai step handlers for the local fixture runner."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from mainframe.workflows.atomic import atomic_write_text
from mainframe.workflows.effects import build_effect_receipt

Handler = Callable[[dict[str, Any], dict[str, Any], Path], dict[str, Any]]


def handle_load_records(args: dict[str, Any], ctx: dict[str, Any], work: Path) -> dict[str, Any]:
    path = work / (args.get("path") or "records.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    return {"records": data, "count": len(data)}


def handle_transform_report(args: dict[str, Any], ctx: dict[str, Any], work: Path) -> dict[str, Any]:
    records = ctx.get("records") or []
    title = args.get("title") or ctx.get("title") or "Report"
    rows = [{"id": r.get("id"), "label": r.get("label"), "value": r.get("value")} for r in records]
    report = {
        "title": title,
        "row_count": len(rows),
        "rows": rows,
        "source_count": ctx.get("count"),
        "generated_by": "mainframe.workflows.handlers.transform_report",
    }
    return {"report": report}


def handle_write_artifact(args: dict[str, Any], ctx: dict[str, Any], work: Path) -> dict[str, Any]:
    report = ctx.get("report")
    if report is None:
        raise ValueError("missing_report")
    rel = args.get("path") or "report.json"
    out = work / rel
    text = json.dumps(report, indent=2) + "\n"
    atomic_write_text(out, text)
    digest = hashlib.sha256(text.encode()).hexdigest()
    op_id = args.get("operation_id") or ctx.get("_operation_id") or f"op_write_{digest[:12]}"
    effect = build_effect_receipt(
        operation_id=op_id,
        effect_kind="create_local_artifact",
        execution_status="succeeded",
        delivery_status="not_requested",
        outcome="succeeded",
        detail={"path": rel, "sha256": digest},
    )
    return {
        "artifact_path": rel,
        "sha256": digest,
        "bytes": len(text.encode()),
        "operation_id": op_id,
        "effect_receipt": effect,
        "_effect_kind": "create_local_artifact",
    }


def handle_human_approve(args: dict[str, Any], ctx: dict[str, Any], work: Path) -> dict[str, Any]:
    decision = args.get("decision") or ctx.get("human_decision") or "approve"
    if decision == "pending":
        return {"_human_pending": True, "decision": "pending"}
    return {"decision": decision, "approved": decision == "approve"}


def handle_ai_summarize(args: dict[str, Any], ctx: dict[str, Any], work: Path) -> dict[str, Any]:
    from mainframe.workflows.ai_runtime import run_typed_ai_step

    source = args.get("source") or ctx.get("source") or json.dumps(ctx.get("report") or {}, indent=2)
    return run_typed_ai_step(
        ai_type="summarize",
        source=str(source),
        args=args,
        work_dir=work,
        output_schema=args.get("output_schema")
        or {
            "type": "object",
            "required": ["summary"],
            "properties": {"summary": {"type": "string"}},
        },
        model_fixture=ctx.get("_model_fixture") or args.get("model_fixture"),
        force_unavailable=bool(ctx.get("_force_ai_unavailable")),
    )


def handle_ai_extract(args: dict[str, Any], ctx: dict[str, Any], work: Path) -> dict[str, Any]:
    from mainframe.workflows.ai_runtime import run_typed_ai_step

    source = str(args.get("source") or ctx.get("source") or "")
    return run_typed_ai_step(
        ai_type="extract",
        source=source,
        args=args,
        work_dir=work,
        output_schema=args.get("output_schema")
        or {
            "type": "object",
            "properties": {
                "fields": {"type": "object"},
                "uncertain": {"type": "boolean"},
                "name": {"type": "string"},
                "version": {"type": "string"},
            },
        },
        model_fixture=ctx.get("_model_fixture") or args.get("model_fixture"),
        force_unavailable=bool(ctx.get("_force_ai_unavailable")),
    )


def handle_ai_classify(args: dict[str, Any], ctx: dict[str, Any], work: Path) -> dict[str, Any]:
    from mainframe.workflows.ai_runtime import run_typed_ai_step

    source = str(args.get("source") or ctx.get("source") or "")
    return run_typed_ai_step(
        ai_type="classify",
        source=source,
        args=args,
        work_dir=work,
        output_schema=args.get("output_schema")
        or {
            "type": "object",
            "properties": {"label": {"type": "string"}, "uncertain": {"type": "boolean"}},
        },
        model_fixture=ctx.get("_model_fixture") or args.get("model_fixture"),
        force_unavailable=bool(ctx.get("_force_ai_unavailable")),
    )


def handle_ai_propose_code(args: dict[str, Any], ctx: dict[str, Any], work: Path) -> dict[str, Any]:
    from mainframe.workflows.ai_runtime import run_typed_ai_step

    source = str(args.get("source") or ctx.get("source") or ctx.get("code_context") or "")
    return run_typed_ai_step(
        ai_type="propose_code",
        source=source,
        args=args,
        work_dir=work,
        output_schema=args.get("output_schema")
        or {
            "type": "object",
            "properties": {"proposal": {"type": "string"}, "uncertain": {"type": "boolean"}},
        },
        model_fixture=ctx.get("_model_fixture") or args.get("model_fixture"),
        force_unavailable=bool(ctx.get("_force_ai_unavailable")),
    )


def handle_load_source(args: dict[str, Any], ctx: dict[str, Any], work: Path) -> dict[str, Any]:
    path = work / (args.get("path") or "source.txt")
    text = path.read_text(encoding="utf-8")
    return {"source": text, "source_bytes": len(text.encode())}


def handle_write_digest(args: dict[str, Any], ctx: dict[str, Any], work: Path) -> dict[str, Any]:
    source = ctx.get("source") or ""
    digest = hashlib.sha256(str(source).encode()).hexdigest()
    rel = args.get("path") or "digest.json"
    payload = {"sha256": digest, "bytes": len(str(source).encode())}
    atomic_write_text(work / rel, json.dumps(payload, indent=2) + "\n")
    return {"digest_path": rel, "digest_sha256": digest}


def handle_deliver_report(args: dict[str, Any], ctx: dict[str, Any], work: Path) -> dict[str, Any]:
    """
    Simulated connector delivery. Modes via args['mode'] or ctx['_delivery_mode']:
      succeed | fail | unknown
    Passes stable operation_id through the connector.
    """
    mode = args.get("mode") or ctx.get("_delivery_mode") or "succeed"
    op_id = args.get("operation_id") or ctx.get("_operation_id") or "op_deliver"
    artifact = ctx.get("artifact_path") or args.get("artifact_path")
    diag = {
        "artifact_path": artifact,
        "connector": "local_fixture_delivery",
        "api_token": "sk-SHOULD-REDACT",
    }
    if mode == "fail":
        effect = build_effect_receipt(
            operation_id=op_id,
            effect_kind="deliver_external",
            execution_status="succeeded",
            delivery_status="failed",
            outcome="failed",
            detail={"reason": "destination_rejected", "diag": diag},
        )
        return {
            "delivery_status": "failed",
            "execution_status": "succeeded",
            "operation_id": op_id,
            "effect_receipt": effect,
            "retained_for_review": True,
            "_delivery_failed": True,
        }
    if mode == "unknown":
        effect = build_effect_receipt(
            operation_id=op_id,
            effect_kind="deliver_external",
            execution_status="unknown",
            delivery_status="unknown",
            outcome="unknown",
            detail={"reason": "no_queryable_status_after_timeout", "diag": diag},
        )
        return {
            "delivery_status": "unknown",
            "execution_status": "unknown",
            "operation_id": op_id,
            "effect_receipt": effect,
            "outcome_unknown": True,
            "_outcome_unknown": True,
        }
    effect = build_effect_receipt(
        operation_id=op_id,
        effect_kind="deliver_external",
        execution_status="succeeded",
        delivery_status="delivered",
        outcome="succeeded",
        detail={"artifact_path": artifact},
    )
    return {
        "delivery_status": "delivered",
        "execution_status": "succeeded",
        "operation_id": op_id,
        "effect_receipt": effect,
    }


def handle_delete_local_draft(args: dict[str, Any], ctx: dict[str, Any], work: Path) -> dict[str, Any]:
    rel = args.get("path") or "draft.json"
    path = work / rel
    if path.is_file():
        path.unlink()
    return {
        "deleted": True,
        "path": rel,
        "compensation": {
            "supported": True,
            "inverse_of": "write_local_draft",
            "not_retract_message": True,
        },
    }


HANDLERS: dict[str, Handler] = {
    "load_records": handle_load_records,
    "transform_report": handle_transform_report,
    "write_artifact": handle_write_artifact,
    "human_approve": handle_human_approve,
    "ai_summarize": handle_ai_summarize,
    "ai_extract": handle_ai_extract,
    "ai_classify": handle_ai_classify,
    "ai_propose_code": handle_ai_propose_code,
    "load_source": handle_load_source,
    "write_digest": handle_write_digest,
    "deliver_report": handle_deliver_report,
    "delete_local_draft": handle_delete_local_draft,
}


def get_handler(name: str) -> Handler | None:
    return HANDLERS.get(name)
