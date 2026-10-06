"""Bounded pagination helpers."""

from __future__ import annotations

from typing import Any

from mainframe.connectors.types import PaginationSpec


def next_page_args(
    spec: PaginationSpec,
    *,
    page_index: int,
    prior_body: dict[str, Any] | None,
    query: dict[str, Any],
) -> dict[str, Any] | None:
    """Return query updates for the next page, or None if done / capped."""
    if spec.style == "none":
        return None
    if page_index >= spec.max_pages:
        return None
    q = dict(query)
    if spec.style == "page":
        q[spec.page_param] = page_index + 1
        q.setdefault(spec.limit_param, spec.default_limit)
        return q
    if spec.style == "offset":
        limit = int(q.get(spec.limit_param) or spec.default_limit)
        q[spec.offset_param] = page_index * limit
        q[spec.limit_param] = limit
        return q
    if spec.style == "cursor":
        if not prior_body:
            return q
        nxt = prior_body.get(spec.next_field)
        if not nxt:
            return None
        q[spec.cursor_param] = nxt
        return q
    return None


def extract_items(body: dict[str, Any], spec: PaginationSpec) -> list[Any]:
    items = body.get(spec.items_field)
    if isinstance(items, list):
        return items
    # Common alternates
    for key in ("data", "results", "message"):
        v = body.get(key)
        if isinstance(v, list):
            return v
    return []


def pagination_complete(body: dict[str, Any], spec: PaginationSpec, page_index: int) -> bool:
    if spec.style == "none":
        return True
    if page_index >= spec.max_pages:
        return True
    if spec.style == "cursor":
        return not body.get(spec.next_field)
    items = extract_items(body, spec)
    limit = spec.default_limit
    if len(items) < limit:
        return True
    return False
