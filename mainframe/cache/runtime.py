"""Exact-reuse runtime — prefer avoiding work; track work units for acceptance."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from mainframe.cache import store
from mainframe.cache.keys import (
    config_version,
    content_version,
    environment_version,
    exact_cache_key,
    model_version,
    permission_version,
    project_id,
)
from mainframe.cache.policy import approximate_lookup_refused, may_exact_cache
from mainframe.cache.prompt_cache import prefer_avoid_request, record_observed_benefit


def cached_exact(
    *,
    root: Path,
    kind: str,
    operation: str,
    compute: Callable[[], Any],
    content_paths: list[str] | None = None,
    model: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
    read_only: bool = True,
    side_effects: bool = False,
    is_authorization: bool = False,
    is_external_mutation: bool = False,
    is_time_sensitive: bool = False,
    freshness_required: bool = False,
    work_units_on_miss: int = 1,
    permissions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Exact cache get-or-compute. Approximate similarity is never consulted.
    """
    policy = may_exact_cache(
        kind,
        read_only=read_only,
        side_effects=side_effects,
        is_authorization=is_authorization,
        is_external_mutation=is_external_mutation,
        is_time_sensitive=is_time_sensitive,
        freshness_required=freshness_required,
    )
    if not policy["allowed"]:
        # Still compute but do not store / do not claim hit
        value = compute()
        return {
            "ok": True,
            "cache_hit": False,
            "cache_stored": False,
            "policy": policy,
            "work_units": work_units_on_miss,
            "result": value,
            "approximate_used": False,
        }

    cv = content_version(root, content_paths)
    perm = permission_version(permissions)
    cfg = config_version()
    env = environment_version()
    key = exact_cache_key(
        kind=kind,
        project=project_id(root),
        operation=operation,
        content=cv,
        environment=env,
        model=model,
        config_ver=cfg,
        permission_ver=perm,
        extra=extra,
    )

    hit = store.get_exact(
        root=root,
        cache_key=key,
        expect_content_hash=cv["content_hash"],
        expect_permission_ver=perm,
    )
    if hit is not None:
        record_observed_benefit(
            provider_id="local_exact_cache",
            tokens_saved=0,
            latency_ms_saved=None,
            request_avoided=True,
            detail={"kind": kind, "operation": operation, "cache_key": key[:16]},
        )
        return {
            "ok": True,
            "cache_hit": True,
            "cache_stored": False,
            "cache_key": key,
            "work_units": 0,
            "result": hit["payload"],
            "policy": policy,
            "avoid_request": prefer_avoid_request(),
            "exact": True,
            "approximate_used": False,
            "content_hash": cv["content_hash"],
            "permission_ver": perm,
        }

    value = compute()
    store.put_exact(
        root=root,
        kind=kind,
        cache_key=key,
        payload=value,
        content_hash=cv["content_hash"],
        permission_ver=perm,
        config_ver=cfg,
        model_ver=model_version(model),
        work_units=work_units_on_miss,
    )
    return {
        "ok": True,
        "cache_hit": False,
        "cache_stored": True,
        "cache_key": key,
        "work_units": work_units_on_miss,
        "result": value,
        "policy": policy,
        "exact": True,
        "approximate_used": False,
        "content_hash": cv["content_hash"],
        "permission_ver": perm,
    }


def refuse_approximate(query: str) -> dict[str, Any]:
    _ = query
    return approximate_lookup_refused()
