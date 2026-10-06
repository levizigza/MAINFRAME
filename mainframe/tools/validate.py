"""Argument validation, streaming completeness, one bounded correction."""

from __future__ import annotations

import json
from typing import Any

from mainframe.contracts.schema import validate_against_schema


def parse_arguments(raw: Any) -> dict[str, Any]:
    """
    Parse tool arguments. Malformed JSON → error dict (not raise).
    Incomplete streaming (null sentinel / incomplete flag) → reject.
    """
    if raw is None:
        return {"ok": False, "error_code": "incomplete_streaming_args", "error": "arguments are null"}
    if isinstance(raw, dict):
        if raw.get("__streaming_incomplete__") is True:
            return {
                "ok": False,
                "error_code": "incomplete_streaming_args",
                "error": "streaming arguments incomplete",
            }
        return {"ok": True, "args": raw}
    if isinstance(raw, str):
        s = raw.strip()
        if not s or s in {"{", "[", "null"}:
            return {
                "ok": False,
                "error_code": "incomplete_streaming_args",
                "error": "incomplete JSON fragment",
            }
        try:
            data = json.loads(s)
        except json.JSONDecodeError as exc:
            return {
                "ok": False,
                "error_code": "malformed_json",
                "error": f"malformed JSON: {exc}",
            }
        if not isinstance(data, dict):
            return {
                "ok": False,
                "error_code": "invalid_input",
                "error": "arguments must be a JSON object",
            }
        return {"ok": True, "args": data}
    return {
        "ok": False,
        "error_code": "invalid_input",
        "error": f"unsupported arguments type: {type(raw).__name__}",
    }


def validate_and_correct(
    args: dict[str, Any],
    schema: dict[str, Any],
    *,
    allow_one_correction: bool = True,
) -> dict[str, Any]:
    """
    Validate against schema. Optionally apply one bounded correction
    (e.g. stringified ints, path separators) then re-validate once.
    """
    first = validate_against_schema(args, schema)
    if first["ok"]:
        return {"ok": True, "args": args, "corrected": False, "corrections": []}

    if not allow_one_correction:
        return {
            "ok": False,
            "error_code": "invalid_input",
            "error": "invalid inputs",
            "details": first["errors"],
        }

    corrected, notes = _bounded_correct(args, schema)
    if not notes:
        return {
            "ok": False,
            "error_code": "invalid_input",
            "error": "invalid inputs",
            "details": first["errors"],
        }
    second = validate_against_schema(corrected, schema)
    if second["ok"]:
        return {
            "ok": True,
            "args": corrected,
            "corrected": True,
            "corrections": notes,
        }
    return {
        "ok": False,
        "error_code": "invalid_input",
        "error": "invalid inputs after one correction attempt",
        "details": second["errors"],
        "corrections_attempted": notes,
    }


def _bounded_correct(
    args: dict[str, Any], schema: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """At most one class of fix applied (still may touch multiple fields of same class)."""
    props = schema.get("properties") or {}
    out = dict(args)
    notes: list[str] = []

    # Correction class 1: coerce string integers for integer fields
    coerced = False
    for key, sub in props.items():
        if key not in out:
            continue
        if sub.get("type") == "integer" and isinstance(out[key], str) and out[key].isdigit():
            out[key] = int(out[key])
            notes.append(f"coerced {key} str→int")
            coerced = True
    if coerced:
        return out, notes

    # Correction class 2: normalize path separators
    for key, sub in props.items():
        if key not in out:
            continue
        if sub.get("type") == "string" and key in {"path", "file", "rel_path"}:
            if isinstance(out[key], str) and "\\" in out[key]:
                out[key] = out[key].replace("\\", "/")
                notes.append(f"normalized separators in {key}")
                return out, notes

    return out, notes
