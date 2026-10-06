"""Provenance attached to live (and fixture) connector results."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_provenance(
    *,
    source: str,
    docs_url: str,
    attribution: str | None,
    freshness_s: int,
    retrieved_via: str,
    request_url: str | None = None,
) -> dict[str, Any]:
    retrieved_at = _utc()
    return {
        "source": source,
        "docs_url": docs_url,
        "retrieved_at": retrieved_at,
        "retrieval_time": retrieved_at,
        "attribution": attribution,
        "freshness_limit_s": freshness_s,
        "fresh_until_hint": None,  # filled by caller if needed
        "retrieved_via": retrieved_via,  # live | fixture
        "request_url": request_url,
    }
