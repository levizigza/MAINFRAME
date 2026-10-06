"""End-to-end local document → CSV + report pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mainframe.docreport.dedupe import deduplicate
from mainframe.docreport.emit import write_csv, write_report
from mainframe.docreport.extract import extract_file, semantic_review_uncertain
from mainframe.docreport.validate import sum_ok_amounts, validate_records


def run_pipeline(
    sources: list[Path],
    *,
    out_dir: Path,
    allow_ocr: bool = True,
    use_ai_semantic: bool = False,
    expected: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Ingest → extract (local parsers / optional Tesseract) → validate →
    dedupe → CSV + readable report. Never auto-posts externally.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_records: list[dict[str, Any]] = []
    source_results: list[dict[str, Any]] = []
    for src in sources:
        result = extract_file(Path(src), allow_ocr=allow_ocr)
        source_results.append(
            {
                "path": str(src),
                "ok": result.get("ok"),
                "error": result.get("error"),
                "record_count": result.get("record_count"),
                "ocr": result.get("ocr"),
                "kind": (result.get("ingest") or {}).get("kind"),
            }
        )
        if result.get("ok"):
            all_records.extend(result.get("records") or [])

    validated = validate_records(all_records)
    deduped = deduplicate(validated)
    review = semantic_review_uncertain(deduped["records"], use_ai=use_ai_semantic)
    amount_sum = sum_ok_amounts(deduped["records"])

    metrics = _compute_metrics(
        extracted=len(all_records),
        kept=deduped["records"],
        duplicates=deduped["duplicates"],
        sources=len(sources),
        expected=expected,
    )

    csv_info = write_csv(deduped["records"], out_dir / "records.csv")
    pipeline = {
        "records": deduped["records"],
        "duplicates": deduped["duplicates"],
        "metrics": metrics,
        "semantic_review": review,
        "amount_sum": amount_sum,
        "sources": source_results,
    }
    report_info = write_report(out_dir=out_dir, pipeline=pipeline)

    return {
        "ok": True,
        "out_dir": str(out_dir),
        "csv": csv_info,
        "report": report_info,
        "metrics": metrics,
        "amount_sum": amount_sum,
        "semantic_review": review,
        "sources": source_results,
        "auto_posted_external": False,
        "claims_all_correct": False,
        "note": "Accuracy and unresolved fields are reported; reports are not asserted correct wholesale.",
    }


def _compute_metrics(
    *,
    extracted: int,
    kept: list[dict[str, Any]],
    duplicates: list[dict[str, Any]],
    sources: int,
    expected: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    unresolved_instances = sum(len(r.get("unresolved") or []) for r in kept)
    validation_ok = sum(1 for r in kept if (r.get("validation") or {}).get("ok"))

    accuracy: dict[str, Any] | None = None
    if expected is not None:
        accuracy = score_against_expected(kept, expected)

    return {
        "sources": sources,
        "extracted": extracted,
        "kept": len(kept),
        "duplicates": len(duplicates),
        "validation_ok": validation_ok,
        "unresolved_field_instances": unresolved_instances,
        "accuracy": accuracy,
        "claims_all_correct": False,
    }


def score_against_expected(
    records: list[dict[str, Any]],
    expected: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Compare extracted field values to labeled expected rows by record_id when present.
    Reports field-level accuracy — does not declare the whole report correct.
    """
    by_id: dict[str, dict[str, Any]] = {}
    for r in records:
        rid = ((r.get("fields") or {}).get("record_id") or {}).get("value")
        if rid:
            by_id[str(rid)] = r

    total_fields = 0
    matched = 0
    missing_expected = 0
    unresolved_labeled = 0
    details: list[dict[str, Any]] = []

    for exp in expected:
        eid = str(exp.get("record_id") or "")
        got = by_id.get(eid)
        if not got:
            missing_expected += 1
            details.append({"record_id": eid, "status": "not_extracted"})
            continue
        fields = got.get("fields") or {}
        for fname, exp_val in exp.items():
            if fname == "record_id":
                continue
            if fname.startswith("_"):
                continue
            # null expected = labeled unresolved; count unresolved, do not require match
            if exp_val is None:
                total_fields += 1
                gf = fields.get(fname) or {}
                if gf.get("status") in ("missing", "ambiguous"):
                    unresolved_labeled += 1
                    matched += 1  # correctly left unresolved
                else:
                    details.append(
                        {
                            "record_id": eid,
                            "field": fname,
                            "status": "expected_unresolved_but_got_value",
                            "got": gf.get("value"),
                        }
                    )
                continue
            total_fields += 1
            gf = fields.get(fname) or {}
            if gf.get("status") in ("missing", "ambiguous"):
                unresolved_labeled += 1
                details.append(
                    {
                        "record_id": eid,
                        "field": fname,
                        "status": gf.get("status"),
                        "expected": exp_val,
                    }
                )
                continue
            got_val = gf.get("as_str") if fname == "amount" else gf.get("value")
            if fname == "amount":
                try:
                    ok = got_val is not None and abs(float(got_val) - float(exp_val)) < 1e-9
                except (TypeError, ValueError):
                    ok = str(got_val) == str(exp_val)
            else:
                ok = str(got_val).strip() == str(exp_val).strip()
            if ok:
                matched += 1
            else:
                details.append(
                    {
                        "record_id": eid,
                        "field": fname,
                        "status": "mismatch",
                        "expected": exp_val,
                        "got": got_val,
                    }
                )

    rate = (matched / total_fields) if total_fields else None
    return {
        "labeled_records": len(expected),
        "matched_fields": matched,
        "total_compared_fields": total_fields,
        "field_accuracy": rate,
        "missing_expected_records": missing_expected,
        "unresolved_labeled_fields": unresolved_labeled,
        "details_sample": details[:30],
        "claims_all_correct": False,
    }
