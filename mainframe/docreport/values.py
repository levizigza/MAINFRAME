"""Decimal, date, unit, and spreadsheet formula-injection handling."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import Any

# Cells that Excel/Sheets may treat as formulas — neutralize on CSV emit.
_FORMULA_PREFIX = re.compile(r"^[=+\-@]")

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%Y/%m/%d",
    "%d-%b-%Y",
    "%b %d, %Y",
)

_UNIT = re.compile(
    r"^\s*(?P<num>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)\s*(?P<unit>[A-Za-z%€$£]+)?\s*$"
)


def sanitize_csv_cell(value: Any) -> str:
    """Neutralize spreadsheet formula injection; preserve display text."""
    if value is None:
        return ""
    s = str(value)
    if _FORMULA_PREFIX.match(s):
        return "'" + s
    return s


def parse_decimal(raw: Any) -> dict[str, Any]:
    if raw is None or (isinstance(raw, str) and not str(raw).strip()):
        return {"status": "missing", "value": None, "raw": raw}
    s = str(raw).strip().replace(",", "")
    s2 = s.lstrip("$€£")
    pct = s2.endswith("%")
    if pct:
        s2 = s2[:-1].strip()
    try:
        d = Decimal(s2)
        if pct:
            d = d / Decimal(100)
        return {
            "status": "ok",
            "value": d,
            "raw": raw,
            "as_str": format(d, "f"),
            "percent_interpreted": pct,
        }
    except (InvalidOperation, ValueError):
        return {"status": "ambiguous", "value": None, "raw": raw, "reason": "not_a_decimal"}


def decimal_add(a: Decimal, b: Decimal) -> Decimal:
    return (a + b).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


def parse_date(raw: Any) -> dict[str, Any]:
    if raw is None or (isinstance(raw, str) and not str(raw).strip()):
        return {"status": "missing", "value": None, "raw": raw}
    s = str(raw).strip()
    hits: list[date] = []
    matched_fmt: list[str] = []
    for fmt in _DATE_FORMATS:
        try:
            hits.append(datetime.strptime(s, fmt).date())
            matched_fmt.append(fmt)
        except ValueError:
            continue
    uniq = {h.isoformat() for h in hits}
    if not hits:
        return {"status": "ambiguous", "value": None, "raw": raw, "reason": "unrecognized_date"}
    if len(uniq) > 1:
        return {
            "status": "ambiguous",
            "value": None,
            "raw": raw,
            "reason": "ambiguous_date_format",
            "candidates": sorted(uniq),
            "formats": matched_fmt,
        }
    return {
        "status": "ok",
        "value": hits[0].isoformat(),
        "raw": raw,
        "format": matched_fmt[0],
    }


def parse_unit_amount(raw: Any) -> dict[str, Any]:
    if raw is None or (isinstance(raw, str) and not str(raw).strip()):
        return {"status": "missing", "value": None, "unit": None, "raw": raw}
    s = str(raw).strip()
    m = _UNIT.match(s)
    if not m:
        return {
            "status": "ambiguous",
            "value": None,
            "unit": None,
            "raw": raw,
            "reason": "unit_parse_failed",
        }
    num = parse_decimal(m.group("num"))
    if num["status"] != "ok":
        return {**num, "unit": m.group("unit")}
    return {
        "status": "ok",
        "value": num["value"],
        "unit": m.group("unit"),
        "raw": raw,
        "as_str": num["as_str"],
    }
