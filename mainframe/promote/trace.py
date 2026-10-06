"""Build accepted task traces from reporting / website demos (with removable AI)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from mainframe.config import ROOT
from mainframe.promote.types import TaskTrace, TraceStep

FIXTURES = ROOT / "docs" / "demo" / "fixtures"


def build_reporting_trace(*, title_chosen_by_model: str = "Weekly records report") -> TaskTrace:
    """
    Accepted reporting demo trace that *included* unnecessary model decisions
    (title choice + summary) which promotion can remove.
    """
    records_path = FIXTURES / "records_report" / "records.json"
    records = json.loads(records_path.read_text(encoding="utf-8"))
    steps = [
        TraceStep(
            id="load",
            kind="deterministic",
            handler="load_records",
            args={"path": "records.json"},
            parameters_frozen={"path": "records.json"},
        ),
        TraceStep(
            id="ai_choose_title",
            kind="ai",
            handler="ai_choose_title",
            args={},
            parameters_frozen={"title": title_chosen_by_model},
            model_calls=1,
            removable=True,
            note="Title is a stable parameter after acceptance — not ongoing reasoning.",
        ),
        TraceStep(
            id="transform",
            kind="deterministic",
            handler="transform_report",
            args={"title": title_chosen_by_model},
            parameters_frozen={"title": title_chosen_by_model},
        ),
        TraceStep(
            id="ai_summarize",
            kind="ai",
            handler="ai_summarize",
            args={},
            model_calls=1,
            removable=True,
            note="Summary optional; report rows already specify the outcome.",
        ),
        TraceStep(
            id="write_report",
            kind="deterministic",
            handler="write_artifact",
            args={"path": "report.json"},
            parameters_frozen={"path": "report.json"},
        ),
    ]
    model_total = sum(s.model_calls for s in steps)
    out_sha = hashlib.sha256(
        json.dumps({"title": title_chosen_by_model, "rows": records}, sort_keys=True).encode()
    ).hexdigest()
    return TaskTrace(
        trace_id="trace_reporting_demo_v1",
        source="demo_records_to_report",
        accepted=True,
        version="1",
        steps=steps,
        permissions=["local.read", "local.write", "local.artifact"],
        example_input={"records_file": "records.json", "records": records},
        example_output={"artifact_path": "report.json", "row_count": len(records), "sha256_hint": out_sha[:16]},
        supported_conditions_hint={
            "input_schema": {
                "type": "object",
                "required": ["records"],
                "properties": {
                    "records": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["id", "value"],
                            "properties": {
                                "id": {"type": "string"},
                                "label": {"type": "string"},
                                "metric": {"type": "string"},
                                "value": {"type": ["number", "integer", "string"]},
                                "unit": {"type": "string"},
                            },
                            "additionalProperties": False,
                        },
                    },
                    "title": {"type": "string"},
                },
                "additionalProperties": False,
            },
            "min_records": 1,
            "max_records": 100,
            "artifact_path": "report.json",
        },
        model_calls_total=model_total,
    )


def build_website_trace() -> TaskTrace:
    """Accepted website-maintenance demo trace with a removable 'diagnose' AI step."""
    steps = [
        TraceStep(
            id="detect_missing_control",
            kind="deterministic",
            handler="detect_missing_button",
            args={"role": "button", "name": "Apply fix"},
            parameters_frozen={"role": "button", "name": "Apply fix"},
        ),
        TraceStep(
            id="ai_diagnose",
            kind="ai",
            handler="ai_diagnose_breakage",
            model_calls=1,
            removable=True,
            note="Breakage pattern is known; patch anchor is a frozen parameter.",
        ),
        TraceStep(
            id="apply_patch",
            kind="deterministic",
            handler="apply_html_patch",
            args={"patch_id": "restore_apply_fix"},
            parameters_frozen={"patch_id": "restore_apply_fix"},
        ),
        TraceStep(
            id="verify_healthy",
            kind="deterministic",
            handler="verify_status_healthy",
            args={"expected": "healthy"},
            parameters_frozen={"expected": "healthy"},
        ),
        TraceStep(
            id="guard_external_submit",
            kind="human",
            handler="hold_external_submit",
            genuinely_semantic=True,
            note="External submission remain a human/capability decision.",
        ),
    ]
    return TaskTrace(
        trace_id="trace_website_maint_v1",
        source="website_maintenance_demo",
        accepted=True,
        version="1",
        steps=steps,
        permissions=["local.read", "local.write", "local.browse", "human.decide"],
        example_input={"html_fixture": "index_broken.html"},
        example_output={"status_after": "healthy", "patch_ok": True},
        supported_conditions_hint={
            "requires_patch_anchor": True,
            "patch_id": "restore_apply_fix",
            "file_scheme_only": True,
            "input_schema": {
                "type": "object",
                "required": ["html_text"],
                "properties": {"html_text": {"type": "string"}},
                "additionalProperties": False,
            },
        },
        model_calls_total=1,
    )


def save_trace(trace: TaskTrace, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(trace.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def load_trace(path: Path) -> TaskTrace:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    steps = [TraceStep(**s) for s in data["steps"]]
    return TaskTrace(
        trace_id=data["trace_id"],
        source=data["source"],
        accepted=bool(data["accepted"]),
        version=str(data["version"]),
        steps=steps,
        permissions=list(data.get("permissions") or []),
        example_input=data.get("example_input") or {},
        example_output=data.get("example_output") or {},
        supported_conditions_hint=data.get("supported_conditions_hint") or {},
        model_calls_total=int(data.get("model_calls_total") or 0),
        note=data.get("note") or "",
    )
