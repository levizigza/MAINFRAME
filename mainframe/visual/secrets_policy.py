"""Secrets policy: never store credentials inside exported visual / Node-RED flows."""

from __future__ import annotations

from typing import Any

from mainframe.secretdata.facility import LocalSecretFacility


def secrets_policy() -> dict[str, Any]:
    return {
        "store_in_exported_flows": False,
        "store_in_workflow_json": False,
        "facility": "mainframe.secretdata.LocalSecretFacility",
        "reference_form": "secret_ref:<id>",
        "note": "Visual bridge and Node-RED exports must only carry secret_ref ids, never raw secrets.",
    }


def resolve_secret_ref(ref: str, facility: LocalSecretFacility | None = None) -> dict[str, Any]:
    if not isinstance(ref, str) or not ref.startswith("secret_ref:"):
        return {"ok": False, "error": "not_a_secret_ref"}
    secret_id = ref.split(":", 1)[1]
    if secret_id == "REDACTED_USE_FACILITY":
        return {"ok": False, "error": "placeholder_ref"}
    fac = facility or LocalSecretFacility()
    idx = fac._index()  # noqa: SLF001 — presence check only; never return values to visual
    entries = idx.get("entries") or {}
    present = secret_id in entries
    return {
        "ok": True,
        "secret_id": secret_id,
        "present": bool(present),
        "value_exposed_to_visual": False,
    }
