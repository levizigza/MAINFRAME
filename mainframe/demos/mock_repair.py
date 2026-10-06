"""
Mock-inference issue→patch fixture.

Uses the same Broker tools a real model would call. Model output is scripted;
filesystem patches and test verification are real.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from mainframe.ai import probe_free_inference, run_ai_step
from mainframe.config import ROOT
from mainframe.cost_gate import authorize
from mainframe.demos.broker import Broker

FIXTURES = ROOT / "docs" / "demo" / "fixtures" / "issue_patch"
WORK = ROOT / ".mainframe" / "demo_work"


def _workspace(name: str = "issue_patch") -> Path:
    path = WORK / name
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    shutil.copytree(FIXTURES, path, dirs_exist_ok=True)
    return path


def mock_model_decide(issue: dict[str, Any]) -> dict[str, Any]:
    """Scripted model output — same shape a real model broker response would use."""
    return dict(issue["scripted_model_output"])


def run_mock_issue_to_patch() -> dict[str, Any]:
    gate = authorize("tool", "local.mock_issue_patch", local=True)
    if not gate.allowed:
        return {"ok": False, "cost_gate": gate.to_dict()}

    work = _workspace("issue_patch")
    broker = Broker(work)
    issue = json.loads((work / "issue.json").read_text(encoding="utf-8"))

    # 1) Prove failing test is real
    before = broker.run_tests(issue["failing_test"])
    if before.ok:
        return {
            "ok": False,
            "error": "expected_failing_test_passed_unexpectedly",
            "before": before.to_dict(),
        }

    # 2) Scripted inference → tool call via shared broker
    decision = mock_model_decide(issue)
    progress = {
        "issue_id": issue["issue_id"],
        "stage": "mock_inference_tool_call",
        "tool": decision.get("tool"),
        "inputs_preserved": {
            "issue": issue["title"],
            "file": issue["file"],
            "failing_test": issue["failing_test"],
        },
    }
    if decision.get("tool") != "apply_patch":
        return {"ok": False, "error": "unexpected_tool", "progress": progress}

    patch = broker.apply_patch(
        str(decision["path"]),
        str(decision["old"]),
        str(decision["new"]),
    )
    if not patch.ok:
        return {"ok": False, "error": "patch_failed", "patch": patch.to_dict(), "progress": progress}

    # 3) Real verification — test must now pass
    after = broker.run_tests(issue["failing_test"])
    progress["stage"] = "verified"
    return {
        "ok": bool(after.ok and after.detail.get("passed")),
        "name": "mock_issue_to_patch",
        "inference_kind": "mock_scripted",
        "tools": "shared_broker",
        "before_tests_passed": before.detail.get("passed"),
        "after_tests_passed": after.detail.get("passed"),
        "patch": patch.detail,
        "progress": progress,
        "broker_tools_used": [e["tool"] for e in broker.log],
        "workspace": str(work.relative_to(ROOT)).replace("\\", "/"),
        "note": "Filesystem change and test verification are real; model output was scripted.",
    }


def run_failure_path() -> dict[str, Any]:
    """Deliberate failure: apply_patch with wrong old string."""
    work = _workspace("issue_patch_fail")
    broker = Broker(work)
    before = broker.run_tests("test_mathlib.py")
    patch = broker.apply_patch("mathlib.py", "THIS_STRING_DOES_NOT_EXIST", "x")
    after = broker.run_tests("test_mathlib.py")
    return {
        "ok": (not before.ok) and (not patch.ok) and (not after.ok),
        "name": "failure_path_bad_patch",
        "patch_error": patch.detail.get("error"),
        "tests_still_failing": not after.ok,
        "automation_kind": "non_ai_deterministic",
    }


def run_cancellation_path() -> dict[str, Any]:
    """Cancel mid-broker — subsequent tools must report cancelled."""
    work = _workspace("issue_patch_cancel")
    broker = Broker(work)
    first = broker.read_file("mathlib.py")
    broker.cancel()
    second = broker.write_file("should_not_write.txt", "nope")
    return {
        "ok": first.ok and second.cancelled and not second.ok,
        "name": "cancellation_path",
        "first_ok": first.ok,
        "second_cancelled": second.cancelled,
        "file_created": (work / "should_not_write.txt").exists(),
        "automation_kind": "non_ai_deterministic",
    }


def run_ai_dependent_pause() -> dict[str, Any]:
    """
    AI-dependent task without a model: must pause honestly with inputs/progress intact.
    Does not invent a successful completion.
    """
    prompt = "Repair ISSUE-42 multiply bug using tools"
    progress = {
        "task": "ai_dependent_repair",
        "stage": "awaiting_eligible_inference",
        "inputs_preserved": {"prompt": prompt, "issue_id": "ISSUE-42"},
    }
    probe = probe_free_inference()
    if probe.status == "available":
        # Still run through run_ai_step; may succeed if local model exists — report honestly.
        out = run_ai_step(prompt)
        progress["stage"] = "inference_attempted"
        return {
            "ok": True,
            "name": "ai_dependent_task",
            "paused": bool(out.get("paused")),
            "probe": probe.to_dict(),
            "ai_result": {k: out.get(k) for k in ("ok", "paused", "message", "prompt_preserved")},
            "progress": progress,
            "note": "Local model was available; pause not required.",
        }

    # No model: pause with progress intact (do not call paid fallback).
    out = run_ai_step(prompt)
    progress["stage"] = "paused_no_model"
    progress["inputs_preserved"]["prompt_still"] = out.get("prompt_preserved")
    return {
        "ok": bool(out.get("paused")) and out.get("prompt_preserved") == prompt,
        "name": "ai_dependent_task",
        "paused": True,
        "probe": probe.to_dict(),
        "ai_result": {
            "ok": out.get("ok"),
            "paused": out.get("paused"),
            "message": out.get("message"),
            "prompt_preserved": out.get("prompt_preserved"),
            "fallback_used": out.get("fallback_used", False),
        },
        "progress": progress,
        "note": "Honest pause — no invented success; inputs/progress retained.",
    }
