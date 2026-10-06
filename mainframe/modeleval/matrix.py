"""Capability matrix from measured results — unknowns stay unknown."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def build_matrix(eval_report: dict[str, Any]) -> dict[str, Any]:
    """
    Rows = models, columns = task classes.
    Cells are measured aggregates or explicitly unknown.
    """
    results = eval_report.get("results") or []
    by_model: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    meta: dict[str, dict[str, Any]] = {}

    for r in results:
        m = r.get("model") or {}
        key = f"{m.get('provider_id')}/{m.get('model_id')}@{m.get('model_version')}"
        meta[key] = {
            "provider_id": m.get("provider_id"),
            "model_id": m.get("model_id"),
            "model_version": m.get("model_version"),
            "fingerprint": m.get("fingerprint"),
            "context_settings": m.get("context_settings"),
            "marketing_label": m.get("marketing_label"),
            "params_b_claim": m.get("params_b_claim"),
            "availability_kind": m.get("availability_kind"),
        }
        by_model[key][str(r.get("task_class"))].append(r)

    matrix: dict[str, dict[str, Any]] = {}
    for mkey, classes in by_model.items():
        matrix[mkey] = {}
        for cls, rows in classes.items():
            measured = [x for x in rows if x.get("status") == "measured" and not x.get("skipped")]
            if not measured:
                matrix[mkey][cls] = {
                    "status": "unknown",
                    "correctness": None,
                    "latency_ms_mean": None,
                    "invalid_tool_calls": None,
                    "retries": None,
                    "quota_tokens": None,
                    "n": 0,
                    "reason": "missing_measurement",
                }
                continue
            n = len(measured)
            matrix[mkey][cls] = {
                "status": "measured",
                "correctness": sum(1 for x in measured if x.get("correctness")) / n,
                "latency_ms_mean": sum(float(x.get("latency_ms") or 0) for x in measured) / n,
                "invalid_tool_calls": sum(int(x.get("invalid_tool_calls") or 0) for x in measured),
                "retries": sum(int(x.get("retries") or 0) for x in measured),
                "quota_tokens": sum(int(x.get("quota_tokens") or 0) for x in measured),
                "n": n,
                "measurement_kind": "local_measurement",
                "published_claim": False,
            }

    return {
        "evaluated_at": eval_report.get("evaluated_at"),
        "split": eval_report.get("split"),
        "models": meta,
        "cells": matrix,
        "legend": {
            "unknown": "No local measurement — do not inherit rankings",
            "measured": "Local measurement on recorded fingerprint",
            "not_used_for_routing": ["marketing_label", "params_b_claim", "published_size"],
        },
    }
