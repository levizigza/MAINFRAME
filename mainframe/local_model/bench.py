"""Benchmarks: extraction, tool-use, coding — latency + peak memory; no quality inflation."""

from __future__ import annotations

import json
import os
import time
from typing import Any

from mainframe.local_model.cloud_guard import assert_local_only
from mainframe.local_model.ollama_native import chat, list_local_models
from mainframe.local_model.select import select_candidate

# Optional Windows peak working set via ctypes; degrade gracefully.
def _peak_rss_mib() -> float | None:
    if os.name != "nt":
        try:
            import resource

            # ru_maxrss is KiB on Linux
            return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 2)
        except Exception:  # noqa: BLE001
            return None
    try:
        import ctypes
        from ctypes import wintypes

        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        psapi = ctypes.WinDLL("psapi")
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        GetCurrentProcess = kernel32.GetCurrentProcess
        GetCurrentProcess.restype = wintypes.HANDLE
        GetProcessMemoryInfo = psapi.GetProcessMemoryInfo
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        if not GetProcessMemoryInfo(GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return None
        return round(counters.PeakWorkingSetSize / (1024.0 * 1024.0), 2)
    except Exception:  # noqa: BLE001
        return None


EXTRACTION_PROMPT = (
    "Extract JSON with keys name and version from: "
    "Package MAINFRAME version 0.1.18. Reply with JSON only."
)
CODING_PROMPT = (
    "Write a Python function add(a, b) that returns a+b. "
    "Reply with code only, no markdown."
)

TOOL_DEF = [
    {
        "type": "function",
        "function": {
            "name": "lookup_symbol",
            "description": "Look up a symbol in the local codebase",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    }
]


def _score_extraction(text: str) -> dict[str, Any]:
    ok = False
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            obj = json.loads(text[start : end + 1])
            ok = (
                str(obj.get("name", "")).upper().find("MAINFRAME") >= 0
                or str(obj.get("version", "")).startswith("0.1")
            )
    except Exception:  # noqa: BLE001
        ok = False
    return {"task_ok": ok, "note": "Measured string/JSON check only — not frontier QA."}


def _score_coding(text: str) -> dict[str, Any]:
    ok = "def add" in text and "return" in text and ("a + b" in text or "a+b" in text)
    return {
        "task_ok": ok,
        "note": (
            "Shallow pattern check only. CPU availability does not imply "
            "acceptable coding quality."
        ),
        "coding_quality_claimed": False,
    }


def _score_tools(result: dict[str, Any]) -> dict[str, Any]:
    calls = result.get("tool_calls")
    if calls:
        return {
            "task_ok": True,
            "tool_calls_seen": True,
            "note": "Model emitted tool_calls on native /api/chat.",
        }
    # Some small models print JSON instead — not counted as native tool support
    content = str(result.get("content") or "")
    return {
        "task_ok": False,
        "tool_calls_seen": False,
        "content_excerpt": content[:200],
        "note": "No structured tool_calls; do not claim tool support.",
    }


def run_benchmarks(
    *,
    base_url: str = "http://127.0.0.1:11434",
    model: str | None = None,
    timeout_s: float = 90.0,
) -> dict[str, Any]:
    guard = assert_local_only(base_url, model)
    if not guard["ok"]:
        return {
            "ok": False,
            "feature_status": "unavailable",
            "reason": guard["reason"],
            "frontier_parity_claimed": False,
        }

    tags = list_local_models(base_url, timeout_s=1.5)
    if not tags.get("available"):
        return {
            "ok": True,
            "feature_status": "unavailable",
            "reason": tags.get("reason") or "No local model; benchmarks not run.",
            "tasks": [],
            "measured_limits": {
                "latency_ms": None,
                "peak_client_rss_mib": _peak_rss_mib(),
            },
            "frontier_parity_claimed": False,
            "coding_quality_claimed": False,
            "message": "Local-model feature visibly unavailable; no-local-model mode supported.",
        }

    sel = select_candidate(base_url=base_url)
    chosen = model
    if not chosen:
        if sel.get("selected") and sel["selected"].get("installed"):
            chosen = sel["selected"]["resolved_ollama_name"]
        else:
            chosen = (tags.get("models") or [None])[0]
    if not chosen:
        return {
            "ok": True,
            "feature_status": "unavailable",
            "reason": "No model name to bench.",
            "frontier_parity_claimed": False,
        }

    tasks_spec = [
        ("extraction", EXTRACTION_PROMPT, None, _score_extraction),
        (
            "tool_use",
            "Use the lookup_symbol tool for name=total",
            TOOL_DEF,
            None,  # scored from full result
        ),
        ("coding", CODING_PROMPT, None, _score_coding),
    ]

    results: list[dict[str, Any]] = []
    peak = _peak_rss_mib()
    for name, prompt, tools, scorer in tasks_spec:
        t0 = time.perf_counter()
        rss_before = _peak_rss_mib()
        out = chat(
            base_url,
            chosen,
            [{"role": "user", "content": prompt}],
            tools=tools,
            timeout_s=timeout_s,
        )
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 1)
        rss_after = _peak_rss_mib()
        if rss_after is not None:
            peak = max(peak or 0, rss_after)

        if name == "tool_use":
            score = _score_tools(out) if out.get("ok") else {"task_ok": False, "error": out.get("message")}
        else:
            content = str(out.get("content") or "")
            score = scorer(content) if out.get("ok") and scorer else {"task_ok": False}

        results.append(
            {
                "task": name,
                "ok": bool(out.get("ok")),
                "latency_ms": elapsed_ms,
                "client_rss_mib_before": rss_before,
                "client_rss_mib_after": rss_after,
                "score": score,
                "route": out.get("route"),
                "model": chosen,
            }
        )

    return {
        "ok": True,
        "feature_status": "available",
        "model": chosen,
        "endpoint": base_url,
        "selection": sel,
        "tasks": results,
        "measured_limits": {
            "peak_client_rss_mib": peak,
            "note": (
                "Client RSS only — server/model process memory is not attached here. "
                "Report as measured client-side limits, not frontier parity."
            ),
        },
        "frontier_parity_claimed": False,
        "coding_quality_claimed": False,
        "disclaimer": (
            "Measured latency/memory only. Successful shallow checks are not "
            "frontier-model parity and do not certify coding quality."
        ),
    }
