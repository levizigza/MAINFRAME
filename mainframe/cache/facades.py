"""Facades: exact caches for scan, retrieve, tools, workflows, model responses."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from mainframe.cache.runtime import cached_exact


def cached_repo_scan(root: Path, *, incremental: bool = True) -> dict[str, Any]:
    from mainframe.inventory.scan import scan_repository

    def compute() -> dict[str, Any]:
        return scan_repository(root, incremental=incremental)

    wrapped = cached_exact(
        root=root,
        kind="repo_scan",
        operation=f"scan_repository:incremental={incremental}",
        compute=compute,
        work_units_on_miss=1,
        read_only=True,
    )
    out = dict(wrapped["result"])
    out["exact_cache"] = {
        "hit": wrapped["cache_hit"],
        "work_units": wrapped["work_units"],
        "cache_key": wrapped.get("cache_key"),
    }
    return out


def cached_retrieve(
    root: Path,
    *,
    issue_text: str,
    goal: str,
    follow_up: str | None = None,
    top_k: int = 8,
) -> dict[str, Any]:
    from mainframe.retrieval.retrieve import retrieve

    def compute() -> dict[str, Any]:
        return retrieve(
            root,
            issue_text=issue_text,
            goal=goal,
            follow_up=follow_up,
            top_k=top_k,
            use_fts5=False,
        )

    wrapped = cached_exact(
        root=root,
        kind="retrieval",
        operation="retrieve",
        compute=compute,
        extra={"issue": issue_text, "goal": goal, "follow_up": follow_up, "top_k": top_k},
        work_units_on_miss=1,
        read_only=True,
    )
    out = dict(wrapped["result"])
    out["exact_cache"] = {
        "hit": wrapped["cache_hit"],
        "work_units": wrapped["work_units"],
        "cache_key": wrapped.get("cache_key"),
    }
    return out


def cached_tool_output(
    tool_name: str,
    arguments: dict[str, Any],
    *,
    root: Path,
    call_id: str,
    side_effects: bool = False,
    permission: str = "read",
) -> dict[str, Any]:
    """Cache read-only tool outputs only. Mutating tools always miss/store-refused."""
    from mainframe.tools.invoke import invoke
    from mainframe.tools.registry import get_tool

    entry = get_tool(tool_name)
    se = side_effects
    perm = permission
    if entry:
        spec, _ = entry
        se = bool(spec.side_effects)
        perm = spec.permission

    def compute() -> dict[str, Any]:
        # Use a unique call_id suffix for cache-fill so audit duplicate rules don't block
        return invoke(tool_name, arguments, call_id=call_id, root=root)

    wrapped = cached_exact(
        root=root,
        kind="tool_output",
        operation=f"tool:{tool_name}",
        compute=compute,
        extra={"tool": tool_name, "arguments": arguments, "permission": perm},
        read_only=perm == "read" and not se,
        side_effects=se,
        work_units_on_miss=1,
    )
    out = dict(wrapped["result"]) if isinstance(wrapped["result"], dict) else {"result": wrapped["result"]}
    out["exact_cache"] = {
        "hit": wrapped["cache_hit"],
        "work_units": wrapped["work_units"],
        "stored": wrapped.get("cache_stored"),
        "policy": wrapped.get("policy"),
        "cache_key": wrapped.get("cache_key"),
    }
    return out


def store_workflow_artifact(
    root: Path,
    *,
    workflow_id: str,
    artifact: dict[str, Any],
    accepted: bool = True,
) -> dict[str, Any]:
    """Store accepted workflow artifacts only (exact)."""
    if not accepted:
        return {"ok": False, "error": "refused_unaccepted_artifact"}

    def compute() -> dict[str, Any]:
        return {"workflow_id": workflow_id, "artifact": artifact, "accepted": True}

    wrapped = cached_exact(
        root=root,
        kind="workflow_artifact",
        operation=f"workflow:{workflow_id}",
        compute=compute,
        extra={"workflow_id": workflow_id, "artifact_fp": _fp(artifact)},
        read_only=True,
        work_units_on_miss=1,
    )
    return {
        "ok": True,
        "cache_hit": wrapped["cache_hit"],
        "work_units": wrapped["work_units"],
        "cache_key": wrapped.get("cache_key"),
        "artifact": wrapped["result"],
    }


def get_workflow_artifact(root: Path, *, workflow_id: str, artifact: dict[str, Any]) -> dict[str, Any]:
    return store_workflow_artifact(root, workflow_id=workflow_id, artifact=artifact, accepted=True)


def cached_model_response(
    root: Path,
    *,
    prompt: str,
    model: dict[str, Any],
    compute_response: Any = None,
    is_time_sensitive: bool = False,
    freshness_required: bool = False,
) -> dict[str, Any]:
    """
    Exact model-response reuse when valid. Prefer avoiding the request entirely.
    Provider prompt caching is separate and only used where officially supported.
    """
    from mainframe.cache.prompt_cache import prompt_cache_status, prefer_avoid_request

    provider = str((model or {}).get("provider_id") or "unknown")
    pc = prompt_cache_status(provider)

    def compute() -> dict[str, Any]:
        if compute_response is None:
            return {
                "text": f"echo:{hashlib.sha256(prompt.encode()).hexdigest()[:16]}",
                "model": model,
                "prompt_hash": hashlib.sha256(prompt.encode()).hexdigest(),
            }
        return compute_response()

    wrapped = cached_exact(
        root=root,
        kind="model_response",
        operation="model.generate",
        compute=compute,
        model=model,
        extra={"prompt_hash": hashlib.sha256(prompt.encode()).hexdigest()},
        read_only=True,
        is_time_sensitive=is_time_sensitive,
        freshness_required=freshness_required,
        work_units_on_miss=1,
    )
    return {
        "ok": True,
        "cache_hit": wrapped["cache_hit"],
        "work_units": wrapped["work_units"],
        "result": wrapped["result"],
        "request_avoided": wrapped["cache_hit"],
        "provider_prompt_cache": pc,
        "prefer_avoid_request": prefer_avoid_request(),
        "policy": wrapped.get("policy"),
        "exact": True,
        "approximate_used": False,
    }


def authorization_never_cached(decision: dict[str, Any], root: Path) -> dict[str, Any]:
    """Explicitly refuse caching authorization decisions."""
    wrapped = cached_exact(
        root=root,
        kind="tool_output",
        operation="authorization",
        compute=lambda: decision,
        is_authorization=True,
        read_only=True,
        work_units_on_miss=1,
    )
    return {
        "cache_hit": wrapped["cache_hit"],
        "cache_stored": wrapped.get("cache_stored"),
        "policy": wrapped["policy"],
        "result": wrapped["result"],
    }


def _fp(obj: Any) -> str:
    import json

    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode()
    ).hexdigest()[:24]
