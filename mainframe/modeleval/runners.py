"""Eligible model discovery + deterministic fixture runners (local measurements)."""

from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from mainframe.eligibility import ELIGIBLE_PROVIDERS
from mainframe.local_model.ollama_native import list_local_models
from mainframe.local_model.llamacpp import probe_llamacpp
from mainframe.modeleval.catalog import tasks as load_tasks
from mainframe.modeleval.metrics import score_task
from mainframe.quota.admit import AdmissionController
from mainframe.quota.types import ActualUsage, UsageEstimate


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ModelRef:
    provider_id: str
    model_id: str
    model_version: str
    context_settings: dict[str, Any]
    eligible: bool
    available: bool
    availability_kind: str  # local_runtime | account_dependent | unavailable
    marketing_label: str | None = None
    params_b_claim: float | None = None  # published/marketing — not used for routing
    supports_vision: bool = False

    def fingerprint(self) -> str:
        raw = f"{self.provider_id}|{self.model_id}|{self.model_version}|{json_dumps(self.context_settings)}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["fingerprint"] = self.fingerprint()
        return d


def json_dumps(obj: Any) -> str:
    import json

    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def discover_eligible_models() -> list[ModelRef]:
    """Only eligible providers; availability measured locally (never invent live success)."""
    found: list[ModelRef] = []
    # Always include deterministic fixture models for offline eval (eligible local).
    found.append(
        ModelRef(
            provider_id="fixture_local",
            model_id="fixture-strong",
            model_version="1.0.0",
            context_settings={"num_ctx": 2048, "temperature": 0},
            eligible=True,
            available=True,
            availability_kind="local_runtime",
            marketing_label="tiny",  # intentionally small marketing label
            params_b_claim=0.1,
            supports_vision=False,
        )
    )
    found.append(
        ModelRef(
            provider_id="fixture_local",
            model_id="fixture-weak-huge-label",
            model_version="1.0.0",
            context_settings={"num_ctx": 8192, "temperature": 0},
            eligible=True,
            available=True,
            availability_kind="local_runtime",
            marketing_label="frontier-70b-class",  # marketing — must NOT win routing
            params_b_claim=70.0,
            supports_vision=False,
        )
    )
    found.append(
        ModelRef(
            provider_id="fixture_local",
            model_id="fixture-vision",
            model_version="1.0.0",
            context_settings={"num_ctx": 2048},
            eligible=True,
            available=True,
            availability_kind="local_runtime",
            marketing_label="vision-small",
            params_b_claim=1.0,
            supports_vision=True,
        )
    )

    if "ollama_local" in ELIGIBLE_PROVIDERS:
        tags = list_local_models("http://127.0.0.1:11434", timeout_s=0.5)
        if tags.get("available"):
            for name in tags.get("models") or []:
                found.append(
                    ModelRef(
                        provider_id="ollama_local",
                        model_id=str(name),
                        model_version=str(name),  # digest unknown without /api/show
                        context_settings={"num_ctx": "unmeasured"},
                        eligible=True,
                        available=True,
                        availability_kind="local_runtime",
                    )
                )
        else:
            found.append(
                ModelRef(
                    provider_id="ollama_local",
                    model_id="(none)",
                    model_version="n/a",
                    context_settings={},
                    eligible=True,
                    available=False,
                    availability_kind="unavailable",
                )
            )

    llama = probe_llamacpp(timeout_s=0.4)
    if "llamacpp_local" in ELIGIBLE_PROVIDERS:
        found.append(
            ModelRef(
                provider_id="llamacpp_local",
                model_id=str(llama.get("model_path") or "llamacpp"),
                model_version="runtime",
                context_settings={},
                eligible=True,
                available=bool(llama.get("available")),
                availability_kind="local_runtime" if llama.get("available") else "unavailable",
            )
        )

    # Hosted candidates remain account-dependent / not eligible for live eval here
    for pid in ("groq_cloud", "google_gemini_api", "mistral_api"):
        found.append(
            ModelRef(
                provider_id=pid,
                model_id="unspecified",
                model_version="n/a",
                context_settings={},
                eligible=False,
                available=False,
                availability_kind="account_dependent",
                marketing_label="hosted_free_tier_claim",
            )
        )
    return found


def _fixture_respond(model: ModelRef, task: dict[str, Any]) -> dict[str, Any]:
    """Deterministic local responses — measured behavior, not published claims."""
    mid = model.model_id
    cls = task["class"]
    tid = task["id"]

    if mid == "fixture-weak-huge-label":
        # Intentionally poor on holdout/tool tasks despite huge marketing label
        if cls == "tool_selection":
            return {"text": "", "tool": "write_file", "invalid_tool_calls": 1, "retries": 2}
        if cls == "code_repair" and "hold" in tid:
            return {"text": "def sum_to(n):\n    return 0\n", "retries": 1}
        if cls == "structured_extraction":
            return {"text": '{"name":"WRONG"}', "retries": 1}
        if cls == "planning":
            return {"text": '{"steps":["guess"]}', "retries": 0}
        if cls == "vision":
            return {"vision_unsupported": True}
        return {"text": "nope", "retries": 1}

    if mid == "fixture-vision":
        if cls == "vision":
            return {"vision_ok": True, "text": "button labeled Save", "retries": 0}
        # Deliberately weak on non-vision classes (routing must follow class measurements)
        if cls == "tool_selection":
            return {"text": "", "tool": "list_tree", "invalid_tool_calls": 1, "retries": 1}
        if cls == "code_repair":
            return {"text": "pass", "retries": 1}
        if cls == "structured_extraction":
            return {"text": "{}", "retries": 1}
        if cls == "planning":
            return {"text": '{"steps":[]}', "retries": 1}
        return {"text": "{}", "retries": 0}

    # fixture-strong: correct answers for all non-vision text tasks
    if cls == "code_repair":
        if "hold" in tid:
            return {
                "text": "def sum_to(n):\n    return sum(range(1, n+1))\n",
                "retries": 0,
            }
        return {"text": "def add(a, b):\n    return a + b\n", "retries": 0}
    if cls == "tool_selection":
        return {"text": "", "tool": task.get("expect", {}).get("tool"), "retries": 0}
    if cls == "structured_extraction":
        exp = task.get("expect") or {}
        return {"text": json_dumps(exp), "retries": 0}
    if cls == "planning":
        if "order" in (task.get("expect") or {}):
            return {"text": json_dumps({"steps": task["expect"]["order"]}), "retries": 0}
        return {"text": json_dumps({"steps": ["reproduce", "patch", "test"]}), "retries": 0}
    if cls == "vision":
        return {"vision_unsupported": True}
    return {"text": "", "retries": 0}


def run_task_on_model(
    model: ModelRef,
    task: dict[str, Any],
    *,
    quota: AdmissionController | None = None,
) -> dict[str, Any]:
    """Run one task; only available eligible models produce measurements."""
    evaluated_at = _utc()
    base = {
        "task_id": task["id"],
        "task_class": task["class"],
        "split": task.get("split"),
        "model": model.to_dict(),
        "evaluated_at": evaluated_at,
        "measurement_kind": "local_measurement",
        "published_claim": False,
        "account_dependent": model.availability_kind == "account_dependent",
    }
    if not model.eligible:
        return {
            **base,
            "skipped": True,
            "reason": "provider_not_eligible",
            "correctness": None,
            "latency_ms": None,
            "status": "unknown",
        }
    if not model.available:
        return {
            **base,
            "skipped": True,
            "reason": f"unavailable:{model.availability_kind}",
            "correctness": None,
            "latency_ms": None,
            "status": "unknown",
        }
    if task.get("vision") and not model.supports_vision:
        return {
            **base,
            "skipped": True,
            "reason": "vision_unsupported_by_model",
            "correctness": None,
            "latency_ms": None,
            "status": "unknown",
            "measurement_kind": "local_measurement",
        }

    est = UsageEstimate(requests=1, tokens=64, context_tokens=128, tool_overhead_tokens=8)
    reservation_id = None
    retries_quota = 0
    if quota is not None:
        decision = quota.admit(
            provider_id=model.provider_id if model.provider_id in ELIGIBLE_PROVIDERS or model.provider_id == "fixture_local" else "ollama_local",
            estimate=est,
            priority="interactive",
            window_id="modeleval",
            limits={
                "limit_requests": 1000,
                "limit_tokens": 1_000_000,
                "limit_context": 1_000_000,
                "limit_concurrency": 8,
            },
        )
        if not decision.allowed:
            return {
                **base,
                "skipped": True,
                "reason": f"quota_denied:{decision.denied_code}",
                "correctness": None,
                "latency_ms": None,
                "status": "unknown",
                "quota": decision.to_dict(),
            }
        reservation_id = decision.reservation_id

    t0 = time.perf_counter()
    if model.provider_id == "fixture_local":
        response = _fixture_respond(model, task)
    else:
        # Live path reserved for eligible available runtimes — not claimed without probe success.
        # For ollama we still mark as unknown unless we actually call; keep conservative.
        response = {"text": "", "retries": 0, "live_unrun": True}
        base["status"] = "unknown"
        base["reason"] = "live_eligible_but_not_auto_executed_in_eval_harness"
        if reservation_id and quota is not None:
            quota.release(reservation_id, reason="live_skipped")
        return {
            **base,
            "skipped": True,
            "correctness": None,
            "latency_ms": None,
            "invalid_tool_calls": None,
            "retries": None,
            "quota_tokens": None,
        }

    latency_ms = round((time.perf_counter() - t0) * 1000.0, 3)
    scored = score_task(task, response)
    quota_tokens = est.total_tokens()
    if reservation_id and quota is not None:
        quota.reconcile(
            reservation_id,
            ActualUsage(
                requests=1,
                tokens=32,
                context_tokens=64,
                tool_overhead_tokens=scored["invalid_tool_calls"] * 4,
                reasoning_overhead_tokens=0,
            ),
        )
        quota_tokens = 32 + 64 + scored["invalid_tool_calls"] * 4

    return {
        **base,
        "skipped": False,
        "status": "measured",
        "correctness": scored["correct"],
        "latency_ms": latency_ms,
        "invalid_tool_calls": scored["invalid_tool_calls"],
        "retries": scored["retries"] + retries_quota,
        "quota_tokens": quota_tokens,
        "score_detail": scored["detail"],
        "response_excerpt": str(response.get("text") or response.get("tool") or "")[:200],
    }


def run_eval(
    *,
    split: str | None = "holdout",
    models: list[ModelRef] | None = None,
    use_quota: bool = True,
) -> dict[str, Any]:
    models = models or [m for m in discover_eligible_models() if m.eligible and m.available]
    task_list = load_tasks(split=split, include_optional_vision=True)
    quota = AdmissionController() if use_quota else None
    rows = []
    for model in models:
        for task in task_list:
            rows.append(run_task_on_model(model, task, quota=quota))
    return {
        "evaluated_at": _utc(),
        "split": split,
        "holdout_from_tuning": split == "holdout",
        "models": [m.to_dict() for m in models],
        "results": rows,
        "note": "Local measurements only unless status=measured on live runtime.",
    }
