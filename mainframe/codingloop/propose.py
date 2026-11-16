"""Propose edits — deterministic fixtures first; optional eligibility-gated local model.

Phase 3: model proposer never replaces the offline fixture path used by accept.
No paid / hosted fallback when Mode B is paused.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from mainframe.ai import probe_free_inference, run_ai_step
from mainframe.cache import cached_model_response
from mainframe.codingloop.import_align import propose_import_align_edits
from mainframe.codingloop.ui_wire import propose_ui_wire_edits
from mainframe.eligibility import decide_provider


def propose_fixes_deterministic(root: Path, hypothesis: str) -> dict[str, Any]:
    """Known-fixture proposer — returns a *proposal* only. Never marks applied/verified."""
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
            "source": "deterministic_fixture",
        }

    # Cross-file import ↔ definition alignment (camelCase/snake_case near-miss).
    if not edits:
        align = propose_import_align_edits(root)
        if align.get("edits"):
            return {
                "proposal_only": True,
                "applied": False,
                "verified": False,
                "edits": list(align["edits"]),
                "impossible": False,
                "hypothesis": hypothesis,
                "source": "import_symbol_align",
                "evidence": align.get("evidence"),
                "model_service_used": False,
            }

    # Local UI: missing Prepare click → markReady wiring
    if not edits:
        ui = propose_ui_wire_edits(root)
        if ui.get("edits"):
            return {
                "proposal_only": True,
                "applied": False,
                "verified": False,
                "edits": list(ui["edits"]),
                "impossible": False,
                "hypothesis": hypothesis,
                "source": "ui_wire",
                "evidence": ui.get("evidence"),
                "model_service_used": False,
            }

    return {
        "proposal_only": True,
        "applied": False,
        "verified": False,
        "edits": edits,
        "impossible": False,
        "hypothesis": hypothesis,
        "source": "deterministic_fixture",
    }


def _extract_edits_json(text: str) -> list[dict[str, Any]]:
    """Parse model output for a JSON object containing an edits array."""
    if not text:
        return []
    text = text.strip()
    # Fenced block
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidates = [m.group(1)] if m else []
    candidates.append(text)
    # Brace slice
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start : end + 1])
    for raw in candidates:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and isinstance(data.get("edits"), list):
            out = []
            for e in data["edits"]:
                if not isinstance(e, dict):
                    continue
                path = str(e.get("path") or "").replace("\\", "/")
                old = e.get("old")
                new = e.get("new")
                if path and isinstance(old, str) and isinstance(new, str):
                    out.append({"path": path, "old": old, "new": new})
            return out
    return []


def _build_model_prompt(root: Path, hypothesis: str, *, max_files: int = 8) -> str:
    snippets: list[str] = []
    # Prefer tests first so the model sees the failing assertion, then sources.
    paths = sorted(root.rglob("*.py"), key=lambda p: (0 if "test" in p.name.lower() else 1, str(p)))
    for p in paths:
        if any(part.startswith(".") for part in p.parts):
            continue
        rel = str(p.relative_to(root)).replace("\\", "/")
        try:
            body = p.read_text(encoding="utf-8")
        except OSError:
            continue
        if len(body) > 4000:
            body = body[:4000] + "\n# …truncated\n"
        snippets.append(f"### {rel}\n{body}")
        if len(snippets) >= max_files:
            break
    # Also surface TASK.md / PROBLEM.md when present.
    for name in ("TASK.md", "PROBLEM.md"):
        tp = root / name
        if tp.is_file():
            snippets.insert(0, f"### {name}\n{tp.read_text(encoding='utf-8')[:2000]}")
            break
    files_blob = "\n\n".join(snippets) if snippets else "(no python files)"
    return (
        "You are a local coding assistant. Fix the failing tests with minimal edits.\n"
        "Reply with JSON only (no markdown fences):\n"
        '{"edits":[{"path":"rel/path.py","old":"exact old substring","new":"replacement"}]}\n'
        "Rules:\n"
        "- old must be copied exactly from the file contents below\n"
        "- prefer changing the buggy implementation, not deleting tests\n"
        "- one or few small edits; no apply/verified claims\n"
        f"Goal/hypothesis: {hypothesis}\n\n"
        f"Workspace files:\n{files_blob}\n"
    )


def propose_fixes_model(root: Path, hypothesis: str) -> dict[str, Any]:
    """Eligibility + quota-aware local model propose. Pauses without paid fallback."""
    decision = decide_provider("ollama_local", endpoint="http://127.0.0.1:11434")
    probe = probe_free_inference()
    pd = probe.to_dict() if hasattr(probe, "to_dict") else {}
    if not decision.eligible:
        return {
            "proposal_only": True,
            "applied": False,
            "verified": False,
            "edits": [],
            "impossible": False,
            "paused": True,
            "fallback_used": False,
            "source": "model_gated",
            "reason": decision.reason,
            "hypothesis": hypothesis,
            "eligibility": decision.to_dict(),
        }
    if pd.get("status") != "available":
        return {
            "proposal_only": True,
            "applied": False,
            "verified": False,
            "edits": [],
            "impossible": False,
            "paused": True,
            "fallback_used": False,
            "source": "model_gated",
            "reason": "Mode B paused — no local model; fixture path remains available",
            "hypothesis": hypothesis,
            "probe": {"status": pd.get("status"), "detail": pd.get("detail")},
        }

    # Light quota admit (never evade; on deny pause). Always reconcile/release.
    ctrl = None
    reservation_id: str | None = None
    admit_d: dict[str, Any] = {}
    try:
        from mainframe.quota import AdmissionController, ActualUsage, UsageEstimate

        ctrl = AdmissionController()
        admit = ctrl.admit(
            provider_id="ollama_local",
            estimate=UsageEstimate(requests=1, tokens=1200, context_tokens=800),
            priority="interactive",
            require_cost_gate=True,
        )
        admit_d = admit.to_dict() if hasattr(admit, "to_dict") else dict(admit or {})
        reservation_id = admit_d.get("reservation_id") or getattr(admit, "reservation_id", None)
        if not admit_d.get("allowed", True):
            return {
                "proposal_only": True,
                "applied": False,
                "verified": False,
                "edits": [],
                "paused": True,
                "source": "model_gated",
                "reason": "quota_denied",
                "quota": admit_d,
                "hypothesis": hypothesis,
            }
    except Exception as exc:  # noqa: BLE001
        admit_d = {"note": f"quota_skipped:{exc}"}

    try:
        prompt = _build_model_prompt(root, hypothesis)
        model_meta = {"provider_id": "ollama_local", "route": "propose_fixes_model"}

        def compute() -> dict[str, Any]:
            step = run_ai_step(prompt)
            text = ""
            if isinstance(step, dict):
                text = step.get("response") or step.get("text") or ""
                if not text and isinstance(step.get("message"), dict):
                    text = step["message"].get("content") or ""
                elif not text and isinstance(step.get("message"), str) and step.get("ok"):
                    text = step["message"]
                if step.get("paused") and not text:
                    return {"text": "", "raw": step, "paused": True}
            return {"text": str(text or ""), "raw": step}

        cached = cached_model_response(
            root,
            prompt=prompt,
            model=model_meta,
            compute_response=compute,
        )
        body = cached.get("result") or {}
        text = str(body.get("text") or "")
        edits = _extract_edits_json(text)
        # Validate old substrings exist
        valid: list[dict[str, Any]] = []
        for e in edits:
            path = root / e["path"]
            if not path.is_file():
                continue
            disk = path.read_text(encoding="utf-8")
            if e["old"] in disk:
                valid.append(e)
        paused = bool(body.get("paused"))
        return {
            "proposal_only": True,
            "applied": False,
            "verified": False,
            "edits": valid,
            "impossible": False,
            "paused": paused,
            "source": "model_gated",
            "hypothesis": hypothesis,
            "cache_hit": cached.get("cache_hit"),
            "quota": admit_d,
            "parse_edits_raw": len(edits),
            "parse_edits_valid": len(valid),
            "fallback_used": False,
        }
    finally:
        if ctrl is not None and reservation_id:
            try:
                from mainframe.quota import ActualUsage

                ctrl.reconcile(
                    reservation_id,
                    ActualUsage(requests=1, tokens=400, context_tokens=800),
                )
            except Exception:  # noqa: BLE001
                try:
                    ctrl.release(reservation_id, reason="propose_cleanup")
                except Exception:  # noqa: BLE001
                    pass


def propose_fixes(
    root: Path,
    hypothesis: str,
    *,
    allow_model: bool = True,
) -> dict[str, Any]:
    """
    Deterministic-first propose. If no fixture edits and ``allow_model``, try Mode B.
    Offline accept keeps fixture coverage; model path pauses honestly when unavailable.
    """
    det = propose_fixes_deterministic(root, hypothesis)
    if det.get("impossible") or det.get("edits"):
        return det
    if not allow_model:
        return {**det, "model_skipped": True}
    model = propose_fixes_model(root, hypothesis)
    if model.get("edits"):
        return {
            **model,
            "deterministic_empty": True,
        }
    # Merge: still empty — surface pause/reason from model attempt
    return {
        "proposal_only": True,
        "applied": False,
        "verified": False,
        "edits": [],
        "impossible": False,
        "hypothesis": hypothesis,
        "source": "deterministic_then_model",
        "deterministic": det,
        "model": model,
        "paused": bool(model.get("paused")),
        "reason": model.get("reason") or "no_edits_from_deterministic_or_model",
    }
