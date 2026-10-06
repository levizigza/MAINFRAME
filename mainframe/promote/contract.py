"""Validate inputs against promoted program supported conditions (reject out-of-contract)."""

from __future__ import annotations

from typing import Any


def validate_against_contract(
    payload: dict[str, Any],
    supported: dict[str, Any],
) -> dict[str, Any]:
    """
    Strict contract check. Out-of-contract → ok=False, no side effects.
    Does not invent generality from a single example.
    """
    schema = supported.get("input_schema") or {}
    errors: list[str] = []

    if schema.get("type") == "object":
        if not isinstance(payload, dict):
            return {"ok": False, "error": "out_of_contract", "detail": "payload_not_object"}
        if schema.get("additionalProperties") is False:
            allowed = set((schema.get("properties") or {}).keys())
            extra = sorted(set(payload.keys()) - allowed)
            if extra:
                errors.append(f"additional_properties:{','.join(extra)}")
        for req in schema.get("required") or []:
            if req not in payload:
                errors.append(f"missing_required:{req}")

        props = schema.get("properties") or {}
        if "records" in props and "records" in payload:
            records = payload["records"]
            if not isinstance(records, list):
                errors.append("records_not_array")
            else:
                min_r = supported.get("min_records")
                max_r = supported.get("max_records")
                if min_r is not None and len(records) < int(min_r):
                    errors.append("below_min_records")
                if max_r is not None and len(records) > int(max_r):
                    errors.append("above_max_records")
                item_schema = (props["records"].get("items") or {}) if isinstance(props["records"], dict) else {}
                req_fields = item_schema.get("required") or []
                allow_extra = item_schema.get("additionalProperties")
                for i, row in enumerate(records):
                    if not isinstance(row, dict):
                        errors.append(f"record_{i}_not_object")
                        continue
                    for f in req_fields:
                        if f not in row:
                            errors.append(f"record_{i}_missing:{f}")
                    if allow_extra is False:
                        allowed_f = set((item_schema.get("properties") or {}).keys())
                        extra_f = sorted(set(row.keys()) - allowed_f)
                        if extra_f:
                            errors.append(f"record_{i}_extra:{','.join(extra_f)}")

        if "html_text" in props and "html_text" in payload:
            if not isinstance(payload["html_text"], str):
                errors.append("html_text_not_string")
            elif supported.get("requires_patch_anchor"):
                # Anchor from website demo fixture
                if "legacy #legacy-submit removed" not in payload["html_text"] and "<!-- legacy" not in payload[
                    "html_text"
                ]:
                    # Still allow already-patched pages that contain Apply fix for verify-only — but
                    # promotion contract requires the known break marker OR apply-fix present.
                    if 'id="apply-fix"' not in payload["html_text"]:
                        errors.append("missing_patch_anchor")

    if errors:
        return {
            "ok": False,
            "error": "out_of_contract",
            "detail": errors,
            "rejected_safely": True,
            "side_effects": False,
        }
    return {"ok": True, "rejected_safely": False}
