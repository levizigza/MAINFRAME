"""Lightweight JSON-schema-ish validation (stdlib only)."""

from __future__ import annotations

from typing import Any


def validate_against_schema(data: Any, schema: dict[str, Any] | None) -> dict[str, Any]:
    if not schema:
        return {"ok": True, "errors": []}
    errors: list[str] = []
    _check(data, schema, "$", errors)
    return {"ok": len(errors) == 0, "errors": errors}


def _check(data: Any, schema: dict[str, Any], path: str, errors: list[str]) -> None:
    t = schema.get("type")
    if t == "object":
        if not isinstance(data, dict):
            errors.append(f"{path}: expected object")
            return
        for req in schema.get("required") or []:
            if req not in data:
                errors.append(f"{path}: missing required '{req}'")
        props = schema.get("properties") or {}
        if schema.get("additionalProperties") is False:
            for k in data:
                if k not in props:
                    errors.append(f"{path}: unexpected property '{k}'")
        for k, sub in props.items():
            if k in data:
                _check(data[k], sub, f"{path}.{k}", errors)
    elif t == "array":
        if not isinstance(data, list):
            errors.append(f"{path}: expected array")
            return
        item_schema = schema.get("items")
        if item_schema:
            for i, item in enumerate(data):
                _check(item, item_schema, f"{path}[{i}]", errors)
    elif t == "string":
        if not isinstance(data, str):
            errors.append(f"{path}: expected string")
            return
        if "minLength" in schema and len(data) < int(schema["minLength"]):
            errors.append(f"{path}: minLength")
        if "maxLength" in schema and len(data) > int(schema["maxLength"]):
            errors.append(f"{path}: maxLength")
    elif t == "integer":
        if not isinstance(data, int) or isinstance(data, bool):
            errors.append(f"{path}: expected integer")
            return
        if "minimum" in schema and data < int(schema["minimum"]):
            errors.append(f"{path}: below minimum")
    elif t == "number":
        if not isinstance(data, (int, float)) or isinstance(data, bool):
            errors.append(f"{path}: expected number")
    elif t == "boolean":
        if not isinstance(data, bool):
            errors.append(f"{path}: expected boolean")
