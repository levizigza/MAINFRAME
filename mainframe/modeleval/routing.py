"""Interpretable, reversible routing from measured performance within budget."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mainframe.config import STATE_DIR, ensure_state
from mainframe.modeleval.matrix import build_matrix

ROUTES_PATH = STATE_DIR / "model_routes.json"


def _budget_ok(cell: dict[str, Any], budget: dict[str, float]) -> bool:
    if cell.get("status") != "measured":
        return False
    if budget.get("max_latency_ms") is not None:
        if float(cell.get("latency_ms_mean") or 0) > float(budget["max_latency_ms"]):
            return False
    if budget.get("max_quota_tokens") is not None:
        if float(cell.get("quota_tokens") or 0) > float(budget["max_quota_tokens"]):
            return False
    if budget.get("max_invalid_tools") is not None:
        if float(cell.get("invalid_tool_calls") or 0) > float(budget["max_invalid_tools"]):
            return False
    return True


def select_routes(
    matrix: dict[str, Any],
    *,
    budgets: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    """
    For each task class pick the best *measured* model by correctness,
    then lower invalid tools, retries, latency — never by size/marketing.
    """
    budgets = budgets or {}
    default_budget = {"max_latency_ms": 60_000, "max_quota_tokens": 100_000, "max_invalid_tools": 10}
    cells = matrix.get("cells") or {}
    models = matrix.get("models") or {}
    classes: set[str] = set()
    for mcells in cells.values():
        classes.update(mcells.keys())

    routes: dict[str, Any] = {}
    for cls in sorted(classes):
        budget = {**default_budget, **(budgets.get(cls) or {})}
        candidates = []
        for mkey, mcells in cells.items():
            cell = mcells.get(cls) or {"status": "unknown"}
            if cell.get("status") != "measured":
                continue
            if not _budget_ok(cell, budget):
                continue
            meta = models.get(mkey) or {}
            candidates.append(
                {
                    "model_key": mkey,
                    "fingerprint": meta.get("fingerprint"),
                    "correctness": float(cell["correctness"]),
                    "invalid_tool_calls": int(cell["invalid_tool_calls"]),
                    "retries": int(cell["retries"]),
                    "latency_ms_mean": float(cell["latency_ms_mean"]),
                    "quota_tokens": int(cell["quota_tokens"]),
                    "marketing_label": meta.get("marketing_label"),
                    "params_b_claim": meta.get("params_b_claim"),
                }
            )
        # Sort by measured performance only
        candidates.sort(
            key=lambda c: (
                -c["correctness"],
                c["invalid_tool_calls"],
                c["retries"],
                c["latency_ms_mean"],
                c["quota_tokens"],
            )
        )
        if not candidates:
            routes[cls] = {
                "selected": None,
                "status": "unknown",
                "reason": "no_measured_candidate_within_budget",
                "rule": "argmax measured correctness within budget; unknown if none",
            }
            continue
        best = candidates[0]
        routes[cls] = {
            "selected": best["model_key"],
            "fingerprint": best["fingerprint"],
            "status": "measured",
            "score": {
                "correctness": best["correctness"],
                "invalid_tool_calls": best["invalid_tool_calls"],
                "retries": best["retries"],
                "latency_ms_mean": best["latency_ms_mean"],
                "quota_tokens": best["quota_tokens"],
            },
            "rule": (
                "Select max correctness among measured models within latency/quota/invalid-tool "
                "budget; tie-break fewer invalid tools, fewer retries, lower latency. "
                "Ignore marketing_label and params_b_claim."
            ),
            "rejected_marketing_bias": [
                c["model_key"]
                for c in candidates[1:]
                if (c.get("params_b_claim") or 0) > (best.get("params_b_claim") or 0)
                and c["correctness"] < best["correctness"]
            ],
            "reversible": True,
            "budget": budget,
        }
    return {
        "evaluated_at": matrix.get("evaluated_at"),
        "split": matrix.get("split"),
        "routes": routes,
        "interpretable": True,
        "uses_model_size": False,
        "uses_marketing_labels": False,
    }


def save_routes(routes: dict[str, Any], path: Path | None = None) -> Path:
    ensure_state()
    p = path or ROUTES_PATH
    p.write_text(json.dumps(routes, indent=2) + "\n", encoding="utf-8")
    return p


def load_routes(path: Path | None = None) -> dict[str, Any] | None:
    p = path or ROUTES_PATH
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def invalidate_if_fingerprint_changed(
    stored_routes: dict[str, Any],
    current_models: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Model change invalidates stale conclusions — do not inherit unsupported ranking.
    """
    current_fp = {
        f"{m.get('provider_id')}/{m.get('model_id')}@{m.get('model_version')}": m.get("fingerprint")
        for m in current_models
    }
    invalidated: list[str] = []
    new_routes = dict(stored_routes.get("routes") or {})
    for cls, route in list(new_routes.items()):
        sel = route.get("selected")
        if not sel:
            continue
        old_fp = route.get("fingerprint")
        cur_fp = current_fp.get(sel)
        if cur_fp is None or old_fp != cur_fp:
            new_routes[cls] = {
                "selected": None,
                "status": "unknown",
                "reason": "model_fingerprint_changed_or_missing",
                "previous_selected": sel,
                "previous_fingerprint": old_fp,
                "current_fingerprint": cur_fp,
                "inherited_ranking": False,
            }
            invalidated.append(cls)
    return {
        "ok": True,
        "invalidated_classes": invalidated,
        "routes": new_routes,
        "note": "Stale rankings cleared; missing measurements remain unknown.",
    }


def build_and_route(eval_report: dict[str, Any], **budget_kwargs: Any) -> dict[str, Any]:
    matrix = build_matrix(eval_report)
    routes = select_routes(matrix, budgets=budget_kwargs.get("budgets"))
    path = save_routes(routes)
    return {"matrix": matrix, "routes": routes, "saved_to": str(path)}
