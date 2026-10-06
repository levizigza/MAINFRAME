"""Emit sanitized CSV and a readable local report — never auto-posts externally."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from mainframe.docreport.extract import CANONICAL_FIELDS
from mainframe.docreport.values import sanitize_csv_cell


def _cell_value(field: dict[str, Any] | None) -> str:
    if not field:
        return ""
    st = field.get("status")
    if st == "missing":
        return "<MISSING>"
    if st == "ambiguous":
        reason = field.get("reason") or "ambiguous"
        raw = field.get("raw")
        return f"<AMBIGUOUS:{reason}:{raw}>"
    if field.get("as_str") is not None:
        return str(field["as_str"])
    if field.get("value") is not None:
        return str(field["value"])
    return ""


def write_csv(records: list[dict[str, Any]], path: Path) -> dict[str, Any]:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = [
        "record_id",
        "date",
        "amount",
        "unit",
        "party",
        "notes",
        "source_file",
        "row",
        "page",
        "validation_ok",
        "unresolved",
        "dedupe_status",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(headers)
        for rec in records:
            fields = rec.get("fields") or {}
            prov = rec.get("provenance") or {}
            row = [
                _cell_value(fields.get("record_id")),
                _cell_value(fields.get("date")),
                _cell_value(fields.get("amount")),
                _cell_value(fields.get("unit")),
                _cell_value(fields.get("party")),
                _cell_value(fields.get("notes")),
                prov.get("source_file"),
                prov.get("row"),
                prov.get("page"),
                (rec.get("validation") or {}).get("ok"),
                ";".join(rec.get("unresolved") or []),
                (rec.get("dedupe") or {}).get("status"),
            ]
            writer.writerow([sanitize_csv_cell(c) for c in row])
    return {"path": str(path), "rows": len(records), "formula_injection_neutralized": True}


def write_report(
    *,
    out_dir: Path,
    pipeline: dict[str, Any],
) -> dict[str, Any]:
    """Write human-readable markdown + machine JSON. Local only; no external post."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    records = pipeline.get("records") or []
    metrics = pipeline.get("metrics") or {}
    review = pipeline.get("semantic_review") or {}
    amount_sum = pipeline.get("amount_sum") or {}

    md_path = out_dir / "report.md"
    json_path = out_dir / "report.json"

    lines = [
        "# Document → Report",
        "",
        "Local extraction only. Financial/personal records are **not** auto-posted to external systems.",
        "",
        "## Summary",
        "",
        f"- Sources ingested: {metrics.get('sources', 0)}",
        f"- Records extracted: {metrics.get('extracted', 0)}",
        f"- Kept after dedupe: {metrics.get('kept', 0)}",
        f"- Duplicates suppressed: {metrics.get('duplicates', 0)}",
        f"- Validation OK: {metrics.get('validation_ok', 0)}",
        f"- Unresolved field instances: {metrics.get('unresolved_field_instances', 0)}",
        f"- Field accuracy (exact match vs expected, when labeled): {metrics.get('accuracy')}",
        f"- Amount sum (resolved only): {amount_sum.get('total')} (skipped={amount_sum.get('skipped_unresolved')})",
        "",
        "## Semantic review",
        "",
        f"- Applied: {review.get('applied')}",
        f"- Reason: {review.get('reason')}",
        f"- Uncertain records queued: {review.get('uncertain_count')}",
        f"- Auto-posted external: {review.get('auto_posted_external', False)}",
        "",
        "## Provenance sample",
        "",
    ]
    for rec in records[:20]:
        prov = rec.get("provenance") or {}
        lines.append(
            f"- `{prov.get('source_file')}` row={prov.get('row')} page={prov.get('page')} "
            f"unresolved={rec.get('unresolved')} dedupe={(rec.get('dedupe') or {}).get('status')}"
        )
    if len(records) > 20:
        lines.append(f"- … {len(records) - 20} more")

    lines.extend(["", "## Unresolved fields", ""])
    any_u = False
    for rec in records:
        for name in rec.get("unresolved") or []:
            any_u = True
            f = (rec.get("fields") or {}).get(name) or {}
            prov = rec.get("provenance") or {}
            lines.append(
                f"- {prov.get('source_file')} row={prov.get('row')} field=`{name}` "
                f"status={f.get('status')} reason={f.get('reason')} raw={f.get('raw')!r}"
            )
    if not any_u:
        lines.append("- (none)")

    lines.extend(
        [
            "",
            "## Honesty note",
            "",
            "This report does **not** claim every generated row is correct.",
            "Accuracy and unresolved counts are measured against labeled fixtures when provided.",
            "",
        ]
    )
    md_path.write_text("\n".join(lines), encoding="utf-8")

    payload = {
        "kind": "document_to_report",
        "local_only": True,
        "auto_posted_external": False,
        "canonical_fields": list(CANONICAL_FIELDS),
        "metrics": metrics,
        "amount_sum": amount_sum,
        "semantic_review": review,
        "records": _serialize_records(records),
        "duplicates": _serialize_records(pipeline.get("duplicates") or []),
    }
    json_path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    return {"report_md": str(md_path), "report_json": str(json_path), "auto_posted_external": False}


def _serialize_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for rec in records:
        fields = {}
        for k, v in (rec.get("fields") or {}).items():
            fv = dict(v)
            if "value" in fv and fv["value"] is not None:
                fv["value"] = str(fv["value"])
            fields[k] = fv
        out.append({**rec, "fields": fields})
    return out
