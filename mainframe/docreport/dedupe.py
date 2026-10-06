"""Deduplicate records by stable record_key; preserve provenance of duplicates."""

from __future__ import annotations

from typing import Any


def deduplicate(records: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Keep first occurrence of each record_key.
    Records without a key are never merged (each kept; flagged).
    """
    seen: dict[str, int] = {}
    kept: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []

    for rec in records:
        key = rec.get("record_key")
        if not key:
            out = {**rec, "dedupe": {"status": "no_key_kept", "duplicate_of": None}}
            kept.append(out)
            continue
        if key in seen:
            duplicates.append(
                {
                    **rec,
                    "dedupe": {
                        "status": "duplicate",
                        "duplicate_of_index": seen[key],
                        "record_key": key,
                    },
                }
            )
            # Annotate original
            kept[seen[key]] = {
                **kept[seen[key]],
                "dedupe": {
                    **(kept[seen[key]].get("dedupe") or {"status": "kept"}),
                    "status": "kept_with_duplicates",
                    "duplicate_count": (kept[seen[key]].get("dedupe") or {}).get("duplicate_count", 0) + 1,
                },
            }
        else:
            seen[key] = len(kept)
            kept.append({**rec, "dedupe": {"status": "kept", "record_key": key, "duplicate_count": 0}})

    return {
        "records": kept,
        "duplicates": duplicates,
        "input_count": len(records),
        "kept_count": len(kept),
        "duplicate_count": len(duplicates),
    }
