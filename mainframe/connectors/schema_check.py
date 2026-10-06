"""Response schema validation and drift detection."""

from __future__ import annotations

from typing import Any

from mainframe.workflows.typesafe import validate_value_against_schema


def validate_output(value: Any, schema: dict[str, Any] | None) -> dict[str, Any]:
    ok, reason = validate_value_against_schema(value, schema)
    if not ok:
        return {
            "ok": False,
            "drift": True,
            "reason": reason,
            "code": "schema_drift",
        }
    # Soft property type checks for declared properties
    if isinstance(value, dict) and schema and schema.get("type") == "object":
        props = schema.get("properties") or {}
        mismatches: list[str] = []
        for key, sub in props.items():
            if key not in value:
                continue
            expect = (sub or {}).get("type")
            got = value[key]
            if expect == "string" and not isinstance(got, str):
                mismatches.append(f"{key}:expected_string")
            elif expect == "integer" and not (isinstance(got, int) and not isinstance(got, bool)):
                mismatches.append(f"{key}:expected_integer")
            elif expect == "number" and not isinstance(got, (int, float)):
                mismatches.append(f"{key}:expected_number")
            elif expect == "array" and not isinstance(got, list):
                mismatches.append(f"{key}:expected_array")
            elif expect == "object" and not isinstance(got, dict):
                mismatches.append(f"{key}:expected_object")
            elif expect == "boolean" and not isinstance(got, bool):
                mismatches.append(f"{key}:expected_boolean")
        if mismatches:
            return {
                "ok": False,
                "drift": True,
                "reason": "property_type_mismatch:" + ",".join(mismatches),
                "code": "schema_drift",
                "mismatches": mismatches,
            }
    return {"ok": True, "drift": False, "reason": "ok"}
