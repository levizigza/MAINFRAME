"""Local field extraction with provenance; optional eligible semantic step for uncertain fields."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from mainframe.docreport.ingest import ingest_file, parse_json_records, parse_table_text
from mainframe.docreport.ocr import ocr_image
from mainframe.docreport.values import parse_date, parse_decimal, parse_unit_amount

# Expected report fields for invoice-like / ledger-like documents
CANONICAL_FIELDS = ("record_id", "date", "amount", "unit", "party", "notes")

_KV = re.compile(
    r"(?P<key>record[_\s]?id|date|amount|party|unit|notes)\s*[:=]\s*(?P<val>.+)",
    re.I,
)


def _field_status(name: str, raw: Any) -> dict[str, Any]:
    if raw is None or (isinstance(raw, str) and not str(raw).strip()):
        return {"field": name, "status": "missing", "value": None, "raw": raw}
    if name == "amount":
        parsed = parse_decimal(raw)
        return {"field": name, **parsed}
    if name == "date":
        parsed = parse_date(raw)
        return {"field": name, **parsed}
    if name == "unit":
        # unit alone or amount+unit already handled
        return {"field": name, "status": "ok", "value": str(raw).strip(), "raw": raw}
    return {"field": name, "status": "ok", "value": str(raw).strip(), "raw": raw}


def _normalize_row(row: dict[str, Any], *, source_file: str, page: int | None = None) -> dict[str, Any]:
    lower = {str(k).lower().replace(" ", "_"): v for k, v in row.items() if not str(k).startswith("_")}
    aliases = {
        "id": "record_id",
        "invoice": "record_id",
        "invoice_id": "record_id",
        "vendor": "party",
        "customer": "party",
        "name": "party",
        "total": "amount",
        "qty_unit": "unit",
        "currency": "unit",
    }
    mapped: dict[str, Any] = {}
    for k, v in lower.items():
        mapped[aliases.get(k, k)] = v

    fields = {}
    for name in CANONICAL_FIELDS:
        fields[name] = _field_status(name, mapped.get(name))

    # If amount carried a unit (e.g. "12.50 USD"), split
    amt_raw = mapped.get("amount")
    if isinstance(amt_raw, str) and fields["amount"]["status"] == "ambiguous":
        ua = parse_unit_amount(amt_raw)
        if ua["status"] == "ok":
            fields["amount"] = {
                "field": "amount",
                "status": "ok",
                "value": ua["value"],
                "raw": amt_raw,
                "as_str": ua["as_str"],
            }
            if ua.get("unit") and fields["unit"]["status"] == "missing":
                fields["unit"] = {
                    "field": "unit",
                    "status": "ok",
                    "value": ua["unit"],
                    "raw": ua["unit"],
                }

    provenance = {
        "source_file": source_file,
        "row": row.get("_row"),
        "page": page,
    }
    if row.get("_parse_error"):
        fields["_parse"] = {
            "field": "_parse",
            "status": "ambiguous",
            "value": None,
            "raw": row.get("_raw"),
            "reason": row["_parse_error"],
        }

    unresolved = [
        f["field"]
        for f in fields.values()
        if f.get("status") in ("missing", "ambiguous") and f.get("field") != "notes"
    ]
    # notes missing is OK
    unresolved = [u for u in unresolved if u != "notes"]

    return {
        "fields": fields,
        "provenance": provenance,
        "unresolved": unresolved,
        "record_key": _record_key(fields),
    }


def _record_key(fields: dict[str, Any]) -> str | None:
    rid = fields.get("record_id") or {}
    if rid.get("status") == "ok" and rid.get("value"):
        return f"id:{rid['value']}"
    date_v = (fields.get("date") or {}).get("value")
    amt = (fields.get("amount") or {}).get("as_str") or (fields.get("amount") or {}).get("value")
    party = (fields.get("party") or {}).get("value")
    if date_v and amt is not None and party:
        return f"fp:{date_v}|{amt}|{party}"
    return None


def extract_from_text(text: str, *, source_file: str, page: int | None = 1) -> list[dict[str, Any]]:
    """Extract KV lines or fall back to line-level ambiguous records."""
    found: dict[str, Any] = {}
    for line in text.splitlines():
        m = _KV.search(line)
        if m:
            found[m.group("key").lower().replace(" ", "_").replace("-", "_")] = m.group("val").strip()
    # Normalize keys
    norm = {}
    for k, v in found.items():
        if k in ("record_id", "recordid"):
            norm["record_id"] = v
        else:
            norm[k] = v
    if norm:
        return [_normalize_row({**norm, "_row": page}, source_file=source_file, page=page)]

    # Multi-record blocks separated by blank lines
    blocks = re.split(r"\n\s*\n", text.strip())
    records = []
    for i, block in enumerate(blocks, start=1):
        block_found: dict[str, Any] = {}
        for line in block.splitlines():
            m = _KV.search(line)
            if m:
                key = m.group("key").lower().replace(" ", "_")
                if key in ("record_id", "recordid"):
                    key = "record_id"
                block_found[key] = m.group("val").strip()
        if block_found:
            records.append(
                _normalize_row({**block_found, "_row": i}, source_file=source_file, page=page)
            )
    if records:
        return records

    # Unstructured — mark whole document as needing review
    return [
        {
            "fields": {
                name: {
                    "field": name,
                    "status": "ambiguous" if name != "notes" else "ok",
                    "value": text.strip()[:500] if name == "notes" else None,
                    "raw": text[:200] if name == "notes" else None,
                    "reason": "unstructured_text" if name != "notes" else None,
                }
                for name in CANONICAL_FIELDS
            },
            "provenance": {"source_file": source_file, "row": None, "page": page},
            "unresolved": [n for n in CANONICAL_FIELDS if n != "notes"],
            "record_key": None,
            "needs_semantic_review": True,
        }
    ]


def extract_file(path: Path, *, allow_ocr: bool = True) -> dict[str, Any]:
    """Ingest one file and extract records using local parsers (OCR before AI)."""
    ingested = ingest_file(path)
    if not ingested.get("ok"):
        return {"ok": False, "ingest": ingested, "records": []}

    kind = ingested["kind"]
    source = ingested["name"]
    records: list[dict[str, Any]] = []
    ocr_meta = None

    if kind == "table":
        delim = "\t" if ingested["suffix"] == ".tsv" else None
        rows = parse_table_text(ingested["text"] or "", delimiter=delim)
        records = [_normalize_row(r, source_file=source) for r in rows]
    elif kind == "json":
        rows = parse_json_records(ingested["text"] or "", suffix=ingested["suffix"])
        records = [_normalize_row(r, source_file=source) for r in rows]
    elif kind == "image":
        if not allow_ocr:
            return {
                "ok": False,
                "ingest": ingested,
                "records": [],
                "error": "ocr_disabled",
            }
        ocr_meta = ocr_image(Path(path))
        if ocr_meta.get("ok") and ocr_meta.get("text"):
            records = extract_from_text(
                ocr_meta["text"], source_file=source, page=ocr_meta.get("page") or 1
            )
            for r in records:
                r["extraction"] = "tesseract_ocr"
        else:
            # Scanned fixture may ship a sibling .ocr.txt for offline acceptance
            sibling = Path(path).with_suffix(Path(path).suffix + ".ocr.txt")
            if not sibling.is_file():
                sibling = Path(str(path) + ".ocr.txt")
            if sibling.is_file():
                text = sibling.read_text(encoding="utf-8")
                records = extract_from_text(text, source_file=source, page=1)
                for r in records:
                    r["extraction"] = "ocr_sidecar_fixture"
                ocr_meta = {
                    **ocr_meta,
                    "sidecar_used": True,
                    "sidecar_path": str(sibling),
                    "reason": "tesseract_unavailable_or_failed_using_sidecar",
                }
            else:
                return {
                    "ok": False,
                    "ingest": ingested,
                    "ocr": ocr_meta,
                    "records": [],
                    "error": "ocr_unavailable_no_sidecar",
                }
    else:
        records = extract_from_text(ingested["text"] or "", source_file=source, page=1)
        for r in records:
            r.setdefault("extraction", "local_text")

    return {
        "ok": True,
        "ingest": ingested,
        "ocr": ocr_meta,
        "records": records,
        "record_count": len(records),
    }


def semantic_review_uncertain(
    records: list[dict[str, Any]],
    *,
    use_ai: bool = False,
) -> dict[str, Any]:
    """
    Eligible semantic step for genuinely variable documents.
    Default: queue uncertain fields for human review; do not auto-invent values.
    AI path only when explicitly requested and eligibility allows (caller gates).
    """
    uncertain = []
    for i, rec in enumerate(records):
        if rec.get("unresolved") or rec.get("needs_semantic_review"):
            uncertain.append(
                {
                    "index": i,
                    "provenance": rec.get("provenance"),
                    "unresolved": rec.get("unresolved") or [],
                    "needs_semantic_review": bool(rec.get("needs_semantic_review")),
                    "review_status": "pending_human_review",
                }
            )

    if not use_ai:
        return {
            "applied": False,
            "reason": "ai_not_requested_local_first",
            "uncertain_count": len(uncertain),
            "review_queue": uncertain,
            "auto_posted_external": False,
        }

    # Placeholder gate — actual inference must go through eligibility; we do not call models here.
    return {
        "applied": False,
        "reason": "semantic_ai_requires_eligible_runtime_and_explicit_review",
        "uncertain_count": len(uncertain),
        "review_queue": uncertain,
        "auto_posted_external": False,
        "note": "Uncertain fields stay unresolved until reviewed; no external post of financial/PII.",
    }
