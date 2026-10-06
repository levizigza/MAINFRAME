"""Exact-reuse caches — project-isolated; never approximate-as-current."""

from __future__ import annotations

from mainframe.cache.accept import run_cache_accept
from mainframe.cache.facades import (
    cached_model_response,
    cached_repo_scan,
    cached_retrieve,
    cached_tool_output,
    store_workflow_artifact,
)
from mainframe.cache.invalidate import (
    invalidate_for_freshness,
    invalidate_on_permission_change,
    invalidate_on_source_change,
)

__all__ = [
    "cached_model_response",
    "cached_repo_scan",
    "cached_retrieve",
    "cached_tool_output",
    "invalidate_for_freshness",
    "invalidate_on_permission_change",
    "invalidate_on_source_change",
    "run_cache_accept",
    "store_workflow_artifact",
]
