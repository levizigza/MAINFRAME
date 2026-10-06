"""Execute promoted programs via allowlisted handlers — never blind-exec generated code."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from mainframe.promote.contract import validate_against_contract
from mainframe.promote.types import PromotedProgram

# Website patch constants (same as browser demo — frozen behavior reuse)
PATCH_OLD = """    <!-- legacy #legacy-submit removed — fix must restore semantic control -->
  </main>"""

PATCH_NEW = """    <button type="button" role="button" aria-label="Apply fix" id="apply-fix">Apply fix</button>
  </main>
  <script>
    document.getElementById("apply-fix").addEventListener("click", function () {
      var el = document.getElementById("status");
      el.textContent = "healthy";
      el.className = "status-healthy";
    });
  </script>"""


def run_promoted(
    program: PromotedProgram,
    payload: dict[str, Any],
    *,
    work_dir: Path,
    require_trust: bool = True,
) -> dict[str, Any]:
    """
    Run allowlisted steps only. Generated .py is for human review — not executed here.
    """
    if require_trust and program.trust not in ("tested", "accepted"):
        return {
            "ok": False,
            "error": "program_untrusted",
            "trust": program.trust,
            "detail": "Refuse run until reviewed and tested (or pass require_trust=False for harness).",
            "model_calls": 0,
            "side_effects": False,
        }

    contract = validate_against_contract(payload, program.supported_conditions)
    if not contract.get("ok"):
        return {
            "ok": False,
            "error": "out_of_contract",
            "contract": contract,
            "model_calls": 0,
            "model_calls_avoided": program.model_calls_avoided,
            "side_effects": False,
            "rejected_safely": True,
        }

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    ctx: dict[str, Any] = {**payload, **program.frozen_parameters}
    model_calls = 0
    step_log: list[dict[str, Any]] = []

    for step in program.steps:
        kind = step["kind"]
        handler = step["handler"]
        args = dict(step.get("args") or {})

        if kind == "ai" and step.get("genuinely_semantic"):
            # Explicit AI step — count but do not auto-call models in promote runner
            model_calls += int(step.get("model_calls") or 1)
            step_log.append(
                {
                    "id": step["id"],
                    "handler": handler,
                    "status": "deferred_explicit_ai",
                    "note": "Genuine semantic AI left explicit; not silently executed.",
                }
            )
            continue

        if kind == "human":
            step_log.append(
                {
                    "id": step["id"],
                    "handler": handler,
                    "status": "explicit_human",
                    "decision": ctx.get("human_decision", "hold"),
                }
            )
            ctx["human_held"] = True
            continue

        result = _dispatch(handler, args, ctx, work_dir)
        step_log.append({"id": step["id"], "handler": handler, "status": "ok" if result.get("ok", True) else "fail", "result": result})
        if result.get("ok") is False:
            return {
                "ok": False,
                "error": "step_failed",
                "step": step["id"],
                "detail": result,
                "steps": step_log,
                "model_calls": model_calls,
                "model_calls_avoided": program.model_calls_avoided,
            }
        ctx.update({k: v for k, v in result.items() if not k.startswith("_")})

    return {
        "ok": True,
        "steps": step_log,
        "outputs": {
            "artifact_path": ctx.get("artifact_path"),
            "sha256": ctx.get("sha256"),
            "report": ctx.get("report"),
            "html_text": ctx.get("html_text"),
            "status": ctx.get("status"),
            "patch_ok": ctx.get("patch_ok"),
        },
        "model_calls": model_calls,
        "model_calls_avoided": program.model_calls_avoided,
        "model_calls_in_source": program.model_calls_in_source,
        "trust": program.trust,
        "generality_claim": False,
    }


def _dispatch(handler: str, args: dict[str, Any], ctx: dict[str, Any], work: Path) -> dict[str, Any]:
    if handler == "load_records":
        if "records" in ctx and isinstance(ctx["records"], list):
            return {"ok": True, "records": ctx["records"], "count": len(ctx["records"])}
        path = work / (args.get("path") or "records.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        return {"ok": True, "records": data, "count": len(data)}

    if handler == "transform_report":
        records = ctx.get("records") or []
        title = args.get("title") or ctx.get("title") or "Report"
        rows = []
        for r in records:
            rows.append(
                {
                    "id": r.get("id"),
                    "label": r.get("label") or r.get("metric"),
                    "value": r.get("value"),
                    "unit": r.get("unit"),
                }
            )
        report = {
            "title": title,
            "row_count": len(rows),
            "rows": rows,
            "generated_by": "mainframe.promote.runner.transform_report",
            "promoted": True,
        }
        return {"ok": True, "report": report}

    if handler == "write_artifact":
        report = ctx.get("report")
        if report is None:
            return {"ok": False, "error": "missing_report"}
        rel = args.get("path") or "report.json"
        text = json.dumps(report, indent=2) + "\n"
        out = work / rel
        out.write_text(text, encoding="utf-8")
        digest = hashlib.sha256(text.encode()).hexdigest()
        return {"ok": True, "artifact_path": rel, "sha256": digest, "bytes": len(text.encode())}

    if handler == "detect_missing_button":
        html = ctx.get("html_text") or ""
        present = 'aria-label="Apply fix"' in html or 'id="apply-fix"' in html
        return {"ok": True, "missing_control": not present, "present": present}

    if handler == "apply_html_patch":
        html = ctx.get("html_text") or ""
        if PATCH_OLD not in html:
            if 'id="apply-fix"' in html:
                return {"ok": True, "html_text": html, "patch_ok": True, "already_patched": True}
            return {"ok": False, "error": "patch_anchor_missing"}
        updated = html.replace(PATCH_OLD, PATCH_NEW, 1)
        return {"ok": True, "html_text": updated, "patch_ok": True}

    if handler == "verify_status_healthy":
        html = ctx.get("html_text") or ""
        # Deterministic verify: patched markup contains apply-fix and healthy script
        healthy = 'id="apply-fix"' in html and "healthy" in html
        expected = args.get("expected") or "healthy"
        return {"ok": healthy, "status": expected if healthy else "broken", "verify_ok": healthy}

    if handler == "hold_external_submit":
        return {"ok": True, "held": True, "human": True}

    return {"ok": False, "error": "unknown_handler", "handler": handler}
