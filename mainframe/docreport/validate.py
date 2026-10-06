"""Validate extracted records; keep missing/ambiguous explicit."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from mainframe.docreport.extract import CANONICAL_FIELDS
from mainframe.docreport.values import decimal_add


REQUIRED = ("record_id", "date", "amount", "party")


def validate_record(rec: dict[str, Any]) -> dict[str, Any]:
    fields = rec.get("fields") or {}
    issues: list[dict[str, Any]] = []
    for name in REQUIRED:
        f = fields.get(name) or {}
        st = f.get("status")
        if st == "missing":
            issues.append({"field": name, "severity": "missing_required"})
        elif st == "ambiguous":
            issues.append({"field": name, "severity": "ambiguous_required", "reason": f.get("reason")})

    amount = fields.get("amount") or {}
    if amount.get("status") == "ok" and amount.get("value") is not None:
        try:
            if not isinstance(amount["value"], Decimal):
                amount["value"] = Decimal(str(amount["value"]))
            if amount["value"] < 0:
                issues.append({"field": "amount", "severity": "negative_amount"})
        except Exception as exc:  # noqa: BLE001 — keep explicit
            issues.append({"field": "amount", "severity": "amount_cast_failed", "detail": str(exc)})

    valid = not any(i["severity"].startswith("missing") or "ambiguous" in i["severity"] for i in issues)
    return {
        **rec,
        "validation": {
            "ok": valid,
            "issues": issues,
        },
    }


def validate_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [validate_record(r) for r in records]


def sum_ok_amounts(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = Decimal("0.00")
    counted = 0
    skipped = 0
    for r in records:
        amt = (r.get("fields") or {}).get("amount") or {}
        if amt.get("status") == "ok" and amt.get("value") is not None:
            v = amt["value"] if isinstance(amt["value"], Decimal) else Decimal(str(amt["value"]))
            total = decimal_add(total, v)
            counted += 1
        else:
            skipped += 1
    return {
        "total": format(total, "f"),
        "counted": counted,
        "skipped_unresolved": skipped,
        "note": "Sum uses Decimal HALF_EVEN to cents; unresolved amounts excluded",
    }
