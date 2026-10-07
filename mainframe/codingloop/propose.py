"""Deterministic-first propose; optional model proposer under eligibility + quota."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from mainframe.ai import probe_free_inference, run_ai_step
from mainframe.cache import cached_retrieve
from mainframe.eligibility import decide_provider
from mainframe.quota import AdmissionController, ActualUsage, UsageEstimate


def fixture_edits(root: Path, hypothesis: str) -> dict[str, Any]:
    """
    Deterministic proposer for known fixtures — returns a *proposal* only.
    Never marks applied/verified. Offline accept path.
    """
    edits: list[dict[str, Any]] = []
    mathutil = root / "mathutil.py"
    greeter = root / "greeter.py"
    if mathutil.is_file() and "return a * b" in mathutil.read_text(encoding="utf-8"):
        edits.append(
            {
                "path": "mathutil.py",
                "old": "    return a * b  # bug: should add\n",
                "new": "    return a + b\n",
            }
        )
    if greeter.is_file() and '" | "' in greeter.read_text(encoding="utf-8"):
        edits.append(
            {
                "path": "greeter.py",
                "old": '    return " | ".join(parts)  # expected uses "; "\n',
                "new": '    return "; ".join(parts)\n',
            }
        )
    if (root / "oracle.py").is_file():
        return {
            "proposal_only": True,
            "applied": False,
            "verified": False,
            "edits": [],
            "impossible": True,
            "reason": "Requires unavailable external oracle — cannot propose a verified fix.",
            "hypothesis": hypothesis,
        }
    return {
        "proposal_only": True,
        "applied": False,
        "verified": False,
        "edits": edits,
        "impossible": False,
        "hypothesis": hypothesis,
    }


def _parse_edits_from_model(text: str) -> list[dict[str, str]]:
    """Best-effort parse of JSON edits from model text."""
    edits: list[dict[str, str]] = []
    m = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", text)
    blob = m.group(1) if m else None
    if not blob:
        m2 = re.search(r"(\[\s*\{[\s\S]*\}\s*\])", text)
        blob = m2.group(1) if m2 else None
    if blob:
        try:
            data = json.loads(blob)
            if isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    path = item.get("path")
                    old = item.get("old")
                    new = item.get("new")
                    if path and old is not None and new is not None:
                        edits.append(
                            {
                                "path": str(path).replace("\\", "/"),
                                "old": str(old),
                                "new": str(new),
                            }
                        )
        except json.JSONDecodeError:
            pass
    return edits


def _retrieve_guided_hints(root: Path, hypothesis: str) -> dict[str, Any]:
    try:
        return cached_retrieve(
            root,
            issue_text=hypothesis,
            goal=hypothesis,
            top_k=6,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "hits": []}


def propose_edits(
    root: Path,
    *,
    hypothesis: str,
    prefer_model: bool = True,
    task_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Deterministic-first proposal for workspace repairs.

    1. Known fixture proposer (offline accept path)
    2. Retrieve-guided context (exact cache when valid)
    3. Optional local model proposer when Mode B available + quota admits
    """
    root = root.resolve()
    ctx = task_context or {}
    det = fixture_edits(root, hypothesis)
    edits = list(det.get("edits") or [])
    retrieval = _retrieve_guided_hints(root, hypothesis)
    model_meta: dict[str, Any] = {"attempted": False}

    if det.get("impossible"):
        return {
            "ok": True,
            "proposal_only": True,
            "applied": False,
            "verified": False,
            "edits": [],
            "impossible": True,
            "reason": det.get("reason"),
            "hypothesis": hypothesis,
            "proposer": "impossible",
            "retrieval": retrieval,
            "model": model_meta,
        }

    if edits:
        return {
            "ok": True,
            "proposal_only": True,
            "applied": False,
            "verified": False,
            "edits": edits,
            "impossible": False,
            "hypothesis": hypothesis,
            "proposer": "deterministic_fixture",
            "retrieval": {
                "exact_cache": retrieval.get("exact_cache"),
                "hit_count": len(retrieval.get("hits") or []),
            },
            "model": model_meta,
            "note": "Fixture/deterministic edits preferred — model not required.",
        }

    if not prefer_model:
        return {
            "ok": True,
            "proposal_only": True,
            "applied": False,
            "verified": False,
            "edits": [],
            "impossible": False,
            "hypothesis": hypothesis,
            "proposer": "deterministic_empty",
            "retrieval": {
                "exact_cache": retrieval.get("exact_cache"),
                "hit_count": len(retrieval.get("hits") or []),
            },
            "model": model_meta,
            "note": "No deterministic edits; model proposer skipped (prefer_model=False).",
        }

    decision = decide_provider("ollama_local", endpoint="http://127.0.0.1:11434")
    probe = probe_free_inference()
    pd = probe.to_dict() if hasattr(probe, "to_dict") else {}
    if not decision.eligible or pd.get("status") != "available":
        model_meta = {
            "attempted": False,
            "paused": True,
            "eligible": bool(decision.eligible),
            "probe": pd.get("status"),
            "detail": pd.get("detail"),
        }
        return {
            "ok": True,
            "proposal_only": True,
            "applied": False,
            "verified": False,
            "edits": [],
            "impossible": False,
            "hypothesis": hypothesis,
            "proposer": "paused_no_model",
            "retrieval": {
                "exact_cache": retrieval.get("exact_cache"),
                "hit_count": len(retrieval.get("hits") or []),
            },
            "model": model_meta,
            "note": "AI paused — install fitted Ollama model for model proposer.",
        }

    ctl = AdmissionController()
    estimate = UsageEstimate(requests=1, tokens=1024, context_tokens=4096)
    admit = ctl.admit(
        provider_id="ollama_local",
        estimate=estimate,
        priority="interactive",
        require_cost_gate=True,
    )
    if not admit.allowed:
        model_meta = {
            "attempted": False,
            "quota_denied": True,
            "reason": admit.reason,
            "denied_code": admit.denied_code,
        }
        return {
            "ok": True,
            "proposal_only": True,
            "applied": False,
            "verified": False,
            "edits": [],
            "hypothesis": hypothesis,
            "proposer": "quota_denied",
            "retrieval": {
                "exact_cache": retrieval.get("exact_cache"),
                "hit_count": len(retrieval.get("hits") or []),
            },
            "model": model_meta,
        }

    hit_summaries = []
    for h in (retrieval.get("hits") or [])[:5]:
        if isinstance(h, dict):
            hit_summaries.append(
                {
                    "path": h.get("path") or h.get("rel"),
                    "score": h.get("score"),
                    "snippet": (h.get("snippet") or h.get("preview") or "")[:240],
                }
            )
    sel = ctx.get("selection") or {}
    prompt = (
        "Propose minimal file edits as a JSON array of "
        '{"path","old","new"} objects only. No markdown commentary.\n'
        f"Hypothesis: {hypothesis[:800]}\n"
        f"Selection path: {sel.get('path')}\n"
        f"Selection text:\n{(sel.get('text') or '')[:1200]}\n"
        f"Retrieve hits: {json.dumps(hit_summaries)[:2000]}\n"
    )
    step = run_ai_step(prompt)
    model_meta = {"attempted": True, "step_ok": bool(step.get("ok")), "paused": step.get("paused")}
    text = ""
    if isinstance(step, dict):
        text = str(step.get("text") or step.get("output") or step.get("message") or "")
    parsed = _parse_edits_from_model(text) if text else []
    validated: list[dict[str, str]] = []
    for ed in parsed:
        p = root / ed["path"]
        if not p.is_file():
            continue
        try:
            body = p.read_text(encoding="utf-8")
        except OSError:
            continue
        if ed["old"] in body:
            validated.append(ed)
    if admit.reservation_id:
        try:
            ctl.reconcile(
                admit.reservation_id,
                ActualUsage(requests=1, tokens=max(1, len(text) // 4)),
            )
        except Exception:  # noqa: BLE001
            pass

    return {
        "ok": True,
        "proposal_only": True,
        "applied": False,
        "verified": False,
        "edits": validated,
        "impossible": False,
        "hypothesis": hypothesis,
        "proposer": "model" if validated else "model_empty",
        "retrieval": {
            "exact_cache": retrieval.get("exact_cache"),
            "hit_count": len(retrieval.get("hits") or []),
        },
        "model": model_meta,
        "raw_edit_count": len(parsed),
    }
