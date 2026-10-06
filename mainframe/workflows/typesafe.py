"""Lightweight schema compatibility checks (stdlib only)."""

from __future__ import annotations

from typing import Any


def type_compatible(producer: dict[str, Any] | None, consumer: dict[str, Any] | None) -> tuple[bool, str]:
    """
    Check that producer output schema is compatible with consumer input schema.

    Rules (intentionally narrow):
    - If consumer has no required fields / empty properties → OK
    - If both declare type, types must match (or producer is 'any')
    - Required consumer properties must exist in producer properties
    """
    producer = producer or {}
    consumer = consumer or {}
    p_props = producer.get("properties") or {}
    c_props = consumer.get("properties") or {}
    c_req = list(consumer.get("required") or [])

    p_type = producer.get("type")
    c_type = consumer.get("type")
    if p_type and c_type and p_type != c_type and p_type != "any":
        return False, f"type_mismatch:{p_type}->{c_type}"

    for key in c_req:
        if key not in p_props and key not in (producer.get("properties") or {}):
            # Allow if producer additionalProperties is True and consumer only needs the key present at runtime
            if producer.get("additionalProperties") is True and not p_props:
                continue
            if key not in p_props:
                return False, f"missing_required_property:{key}"
        # nested type check when both declare
        if key in p_props and key in c_props:
            pt = (p_props[key] or {}).get("type")
            ct = (c_props[key] or {}).get("type")
            if pt and ct and pt != ct:
                return False, f"property_type_mismatch:{key}:{pt}->{ct}"
    return True, "ok"


def validate_value_against_schema(value: Any, schema: dict[str, Any] | None) -> tuple[bool, str]:
    schema = schema or {}
    expected = schema.get("type")
    if expected == "object":
        if not isinstance(value, dict):
            return False, "expected_object"
        req = schema.get("required") or []
        for k in req:
            if k not in value:
                return False, f"missing:{k}"
        return True, "ok"
    if expected == "array":
        if not isinstance(value, list):
            return False, "expected_array"
        return True, "ok"
    if expected == "string":
        return (isinstance(value, str), "ok" if isinstance(value, str) else "expected_string")
    if expected == "integer":
        return (isinstance(value, int) and not isinstance(value, bool), "ok" if isinstance(value, int) else "expected_integer")
    if expected == "number":
        return (isinstance(value, (int, float)) and not isinstance(value, bool), "ok" if isinstance(value, (int, float)) else "expected_number")
    if expected == "boolean":
        return (isinstance(value, bool), "ok" if isinstance(value, bool) else "expected_boolean")
    return True, "ok"
