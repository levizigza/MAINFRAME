"""Acceptance: clean / scanned / malformed / duplicate fixtures with accuracy metrics."""

from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path
from typing import Any

from mainframe.docreport.ocr import tesseract_probe
from mainframe.docreport.pipeline import run_pipeline
from mainframe.docreport.values import parse_date, parse_decimal, sanitize_csv_cell
from mainframe.config import ROOT

FIXTURES = ROOT / "docs" / "eval" / "docreport" / "fixtures"


def _load_expected(folder: Path) -> list[dict[str, Any]]:
    path = folder / "expected.json"
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _run_case(name: str, sources: list[Path], work: Path) -> dict[str, Any]:
    expected = _load_expected(FIXTURES / name)
    out = run_pipeline(sources, out_dir=work / name, allow_ocr=True, expected=expected)
    return out


def run_docreport_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="docreport_accept_") as tmp:
        work = Path(tmp)

        # 1) clean CSV
        clean = _run_case("clean", [FIXTURES / "clean" / "ledger.csv"], work)
        acc = (clean.get("metrics") or {}).get("accuracy") or {}
        checks.append(
            {
                "id": "clean_fixture_extract",
                "ok": bool(
                    clean.get("ok")
                    and (clean.get("metrics") or {}).get("kept") == 3
                    and acc.get("field_accuracy") == 1.0
                    and (clean.get("metrics") or {}).get("unresolved_field_instances") == 0
                ),
                "detail": {
                    "metrics": clean.get("metrics"),
                    "csv": clean.get("csv"),
                    "claims_all_correct": clean.get("claims_all_correct"),
                },
            }
        )

        # 2) scanned image + OCR sidecar (Tesseract optional)
        scanned = _run_case("scanned", [FIXTURES / "scanned" / "receipt.png"], work)
        sacc = (scanned.get("metrics") or {}).get("accuracy") or {}
        src0 = (scanned.get("sources") or [{}])[0]
        checks.append(
            {
                "id": "scanned_ocr_or_sidecar",
                "ok": bool(
                    scanned.get("ok")
                    and (scanned.get("metrics") or {}).get("kept") >= 1
                    and (sacc.get("field_accuracy") or 0) >= 0.99
                ),
                "detail": {
                    "tesseract": tesseract_probe(),
                    "source": src0,
                    "metrics": scanned.get("metrics"),
                },
            }
        )

        # 3) malformed — unresolved explicit; formula neutralized in CSV
        malformed = _run_case("malformed", [FIXTURES / "malformed" / "messy.csv"], work)
        csv_path = Path((malformed.get("csv") or {}).get("path") or "")
        csv_text = csv_path.read_text(encoding="utf-8") if csv_path.is_file() else ""
        formula_safe = "'=HYPERLINK" in csv_text or "'+cmd" in csv_text or "'@SUM" in csv_text
        unresolved = (malformed.get("metrics") or {}).get("unresolved_field_instances") or 0
        review = malformed.get("semantic_review") or {}
        checks.append(
            {
                "id": "malformed_unresolved_and_formula_safe",
                "ok": bool(
                    malformed.get("ok")
                    and unresolved >= 3
                    and formula_safe
                    and review.get("auto_posted_external") is False
                    and review.get("uncertain_count", 0) >= 1
                ),
                "detail": {
                    "unresolved_field_instances": unresolved,
                    "formula_safe": formula_safe,
                    "semantic_review": review,
                    "accuracy": (malformed.get("metrics") or {}).get("accuracy"),
                    "claims_all_correct": False,
                },
            }
        )

        # 4) duplicates suppressed
        dup = _run_case(
            "duplicate",
            [
                FIXTURES / "duplicate" / "batch_a.csv",
                FIXTURES / "duplicate" / "batch_b.csv",
            ],
            work,
        )
        dacc = (dup.get("metrics") or {}).get("accuracy") or {}
        checks.append(
            {
                "id": "duplicate_dedupe",
                "ok": bool(
                    dup.get("ok")
                    and (dup.get("metrics") or {}).get("extracted") == 4
                    and (dup.get("metrics") or {}).get("kept") == 3
                    and (dup.get("metrics") or {}).get("duplicates") == 1
                    and (dacc.get("field_accuracy") or 0) >= 0.99
                ),
                "detail": {"metrics": dup.get("metrics")},
            }
        )

        # 5) decimal / date / encoding unit checks
        d = parse_decimal("1.005")
        date_amb = parse_date("03/04/2024")
        enc_path = work / "latin1.txt"
        enc_path.write_bytes("record_id: ENC-1\ndate: 2024-01-01\namount: 1.00\nunit: USD\nparty: Café\n".encode("latin-1"))
        enc_run = run_pipeline([enc_path], out_dir=work / "encoding")
        enc_json = json.loads((work / "encoding" / "report.json").read_text(encoding="utf-8"))
        recs = enc_json.get("records") or []
        party = None
        if recs:
            party = ((recs[0].get("fields") or {}).get("party") or {}).get("value")
        checks.append(
            {
                "id": "decimal_date_encoding_formula_helpers",
                "ok": bool(
                    d.get("status") == "ok"
                    and date_amb.get("status") == "ambiguous"
                    and sanitize_csv_cell("=1+1").startswith("'")
                    and party is not None
                    and "Caf" in str(party)
                    and enc_run.get("auto_posted_external") is False
                ),
                "detail": {
                    "decimal": {k: (str(v) if k == "value" else v) for k, v in d.items()},
                    "date_ambiguous": date_amb,
                    "party": party,
                    "encoding_source": (enc_run.get("sources") or [{}])[0],
                },
            }
        )

        # 6) honesty: suite does not claim every report correct
        all_metrics = [
            (clean.get("metrics") or {}),
            (scanned.get("metrics") or {}),
            (malformed.get("metrics") or {}),
            (dup.get("metrics") or {}),
        ]
        honesty = all(
            m.get("claims_all_correct") is False and (m.get("accuracy") or {}).get("claims_all_correct") is False
            for m in all_metrics
            if m.get("accuracy") is not None
        ) and clean.get("claims_all_correct") is False
        checks.append(
            {
                "id": "reports_accuracy_not_wholesale_correct",
                "ok": honesty,
                "detail": {
                    "accuracies": [m.get("accuracy") for m in all_metrics],
                    "unresolved": [m.get("unresolved_field_instances") for m in all_metrics],
                },
            }
        )

        # 7) CSV provenance columns present
        with (Path((clean.get("csv") or {})["path"])).open(encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            headers = reader.fieldnames or []
            row = next(reader, {})
        checks.append(
            {
                "id": "csv_provenance_columns",
                "ok": bool(
                    "source_file" in headers
                    and "row" in headers
                    and "page" in headers
                    and row.get("source_file") == "ledger.csv"
                ),
                "detail": {"headers": headers, "sample_row": dict(row)},
            }
        )

    passed = sum(1 for c in checks if c["ok"])
    return {
        "suite": "docreport-accept",
        "passed": passed,
        "failed": len(checks) - passed,
        "ok": passed == len(checks),
        "checks": checks,
        "auto_posted_external": False,
        "note": "Extraction accuracy and unresolved fields reported; not every report claimed correct.",
    }
