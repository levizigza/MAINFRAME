"""Coding loop — contract → retrieve → propose → apply → verify → report."""

from __future__ import annotations

import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.codingloop.churn import (
    detect_irrelevant_churn,
    detect_oscillation,
    detect_repeated_patch,
    patch_fingerprint,
)
from mainframe.codingloop.lifecycle import LIFECYCLE_PHASES, engine_binding, next_phase
from mainframe.config import ROOT, RUNS_DIR, STATE_DIR, ensure_state
from mainframe.contracts.build import build_contract
from mainframe.patching.apply import apply_batch, inspect_and_snapshot
from mainframe.retrieval.retrieve import retrieve
from mainframe.verify.runner import reproduce_failure

CHECKPOINT_DIR = STATE_DIR / "codingloop_checkpoints"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save_state(state: dict[str, Any]) -> Path:
    ensure_state()
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    cid = state.get("checkpoint_id") or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    state["checkpoint_id"] = cid
    path = CHECKPOINT_DIR / f"{cid}.json"
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return path


def load_checkpoint(checkpoint_id: str) -> dict[str, Any] | None:
    path = CHECKPOINT_DIR / f"{checkpoint_id}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _phase_record(phase: str, **payload: Any) -> dict[str, Any]:
    return {"phase": phase, "at": _utc(), **payload}


def propose_fixes(root: Path, hypothesis: str) -> dict[str, Any]:
    """
    Deterministic proposer for known fixtures — returns a *proposal* only.
    Never marks applied/verified.
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
    # Impossible fixture: no safe deterministic fix without oracle
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


def run_coding_loop(
    workspace: Path,
    *,
    goal: str,
    max_attempts: int = 3,
    resume_from: dict[str, Any] | None = None,
    interrupt_after_phase: str | None = None,
    user_protected_paths: list[str] | None = None,
) -> dict[str, Any]:
    """
    Single lifecycle loop for the selected engine.
    Attempts are successive passes through the same phases — not a nested supervisor.
    """
    started = time.perf_counter()
    engine = engine_binding()
    workspace = workspace.resolve()
    user_protected = set(user_protected_paths or [])

    if resume_from:
        state = dict(resume_from)
        state["resumed"] = True
        attempt = int(state.get("attempt") or 1)
        hypothesis = str(state.get("hypothesis") or "Resume prior hypothesis")
        patch_history = list(state.get("patch_history") or [])
        diagnostics = list(state.get("diagnostics") or [])
        phase_log = list(state.get("phase_log") or [])
        relevant_paths = set(state.get("relevant_paths") or [])
        proposal = state.get("proposal")
        applied = bool(state.get("applied"))
        verified = bool(state.get("verified"))
        if state.get("interrupted"):
            # Apply interruptions resume the apply phase; others advance to the next phase.
            if state.get("awaiting_apply") or state.get("phase") == "apply":
                phase = "apply"
                if not proposal:
                    proposal = propose_fixes(workspace, hypothesis)
            else:
                phase = next_phase(state.get("phase")) or "report"
            state["interrupted"] = False
        else:
            phase = state.get("phase") or "reproduce"
    else:
        state = {
            "resumed": False,
            "workspace": str(workspace),
            "goal": goal,
            "engine": engine,
        }
        phase = "reproduce"
        attempt = 1
        hypothesis = "Failure is reproducible in workspace tests; localize via retrieval."
        patch_history = []
        diagnostics = []
        phase_log = []
        relevant_paths = set()
        proposal = None
        applied = False
        verified = False

    contract = build_contract(goal)
    apply_result: dict[str, Any] | None = None
    check_result: dict[str, Any] | None = None
    stop_reason = "completed"

    while attempt <= max_attempts:
        state.update(
            {
                "attempt": attempt,
                "phase": phase,
                "hypothesis": hypothesis,
                "patch_history": patch_history,
                "diagnostics": diagnostics,
                "phase_log": phase_log,
                "relevant_paths": sorted(relevant_paths),
                "proposal": proposal,
                "applied": applied,
                "verified": verified,
            }
        )
        completed = phase

        if phase == "reproduce":
            repro = reproduce_failure(
                workspace,
                test_target="tests",
                pythonpath=str(workspace),
            )
            phase_log.append(_phase_record("reproduce", result=repro, proposal_only=False, applied=False, verified=False))
            if not repro.get("reproduced") and repro.get("run", {}).get("ok"):
                verified = True
                stop_reason = "already_passing"
                phase = "report"
            else:
                diagnostics.append({"attempt": attempt, "kind": "reproduce", "detail": repro})
                phase = "investigate"

        elif phase == "investigate":
            hits = retrieve(workspace, issue_text=goal, goal=goal, top_k=8)
            files = []
            for h in hits.get("hits") or hits.get("results") or []:
                p = h.get("path") or h.get("file") or h.get("rel_path")
                if p:
                    files.append(str(p).replace("\\", "/"))
            for p in workspace.rglob("*.py"):
                if "tests" in p.parts:
                    continue
                files.append(str(p.relative_to(workspace)).replace("\\", "/"))
            relevant_paths = set(files)
            phase_log.append(
                _phase_record(
                    "investigate",
                    contract_id=(contract.get("contract") or {}).get("id") or contract.get("id"),
                    retrieval_ok=bool(hits.get("ok", True)),
                    relevant_paths=sorted(relevant_paths),
                    hypothesis=hypothesis,
                    proposal_only=False,
                    applied=False,
                    verified=False,
                )
            )
            phase = "propose"

        elif phase == "propose":
            proposal = propose_fixes(workspace, hypothesis)
            phase_log.append(
                _phase_record(
                    "propose",
                    proposal=proposal,
                    proposal_only=True,
                    applied=False,
                    verified=False,
                    note="Proposal is not an implemented or verified fix.",
                )
            )
            if proposal.get("impossible"):
                stop_reason = "impossible_unavailable_dependency"
                phase = "report"
            elif not proposal.get("edits"):
                stop_reason = "no_proposal"
                phase = "report"
            else:
                phase = "apply"

        elif phase == "apply":
            assert proposal is not None
            edits = list(proposal.get("edits") or [])
            fp = patch_fingerprint(edits)
            if detect_repeated_patch(patch_history, fp):
                stop_reason = "repeated_patch"
                diagnostics.append({"attempt": attempt, "kind": "repeated_patch", "fingerprint": fp})
                phase = "report"
            elif detect_oscillation(patch_history + [fp]):
                stop_reason = "oscillation"
                diagnostics.append({"attempt": attempt, "kind": "oscillation", "history": patch_history + [fp]})
                phase = "report"
            else:
                churn = detect_irrelevant_churn(
                    [e["path"] for e in edits],
                    relevant_paths=relevant_paths or {e["path"] for e in edits},
                )
                if churn.get("churn"):
                    stop_reason = "irrelevant_file_churn"
                    diagnostics.append({"attempt": attempt, "kind": "irrelevant_churn", **churn})
                    phase = "report"
                elif any(e["path"] in user_protected for e in edits):
                    stop_reason = "user_edit_preserved"
                    diagnostics.append({"attempt": attempt, "kind": "user_protected"})
                    phase = "report"
                else:
                    snap = inspect_and_snapshot(workspace, [e["path"] for e in edits])
                    state["pre_apply_snapshot"] = snap
                    cp_path = _save_state({**state, "phase": "apply", "awaiting_apply": True})
                    phase_log.append(
                        _phase_record(
                            "checkpoint_before_apply",
                            path=str(cp_path),
                            snapshot=snap.get("snapshot_id"),
                        )
                    )
                    if interrupt_after_phase == "apply":
                        state["interrupted"] = True
                        state["phase"] = "apply"
                        path = _save_state(state)
                        return {
                            "ok": False,
                            "interrupted": True,
                            "resume_checkpoint_id": state["checkpoint_id"],
                            "checkpoint_path": str(path),
                            "phase": "apply",
                            "proposal_only": True,
                            "applied": False,
                            "verified": False,
                            "engine": engine,
                            "phase_log": phase_log,
                            "note": "Interrupted before apply completed — proposal not claimed as implemented.",
                        }
                    apply_result = apply_batch(
                        workspace,
                        edits,
                        snapshot_id=str(snap["snapshot_id"]),
                        scope_paths=[e["path"] for e in edits],
                    )
                    applied = bool(apply_result.get("ok"))
                    patch_history.append(fp)
                    phase_log.append(
                        _phase_record(
                            "apply",
                            result=apply_result,
                            proposal_only=False,
                            applied=applied,
                            verified=False,
                            actual_diffs=[
                                a.get("unified_diff") for a in (apply_result.get("applied") or [])
                            ],
                        )
                    )
                    if not applied:
                        hypothesis = (
                            f"Apply failed ({apply_result.get('error')}); "
                            "re-investigate hashes/user edits."
                        )
                        diagnostics.append(
                            {"attempt": attempt, "kind": "apply_failure", "detail": apply_result}
                        )
                        attempt += 1
                        phase = "investigate"
                    else:
                        phase = "check"

        elif phase == "check":
            check_result = reproduce_failure(
                workspace,
                test_target="tests",
                pythonpath=str(workspace),
            )
            passed = bool(check_result.get("run", {}).get("ok")) and not check_result.get(
                "reproduced"
            )
            phase_log.append(
                _phase_record(
                    "check",
                    result=check_result,
                    proposal_only=False,
                    applied=applied,
                    verified=passed,
                )
            )
            if passed:
                verified = True
                stop_reason = "verified"
                phase = "report"
            else:
                diagnostics.append(
                    {
                        "attempt": attempt,
                        "kind": "verification_failure",
                        "stdout": (check_result.get("run") or {}).get("stdout", "")[-500:],
                        "stderr": (check_result.get("run") or {}).get("stderr", "")[-500:],
                        "classification": check_result.get("classification"),
                    }
                )
                hypothesis = (
                    "Verification failed after apply; update hypothesis using diagnostic "
                    f"classification="
                    f"{(check_result.get('classification') or {}).get('kind') or 'unknown'}."
                )
                attempt += 1
                if attempt > max_attempts:
                    stop_reason = "max_attempts"
                    phase = "report"
                else:
                    phase = "investigate"
                    applied = False
                    proposal = None

        elif phase == "report":
            break
        else:
            stop_reason = f"unknown_phase:{phase}"
            break

        # Interrupt after a completed non-terminal phase (resume continues lifecycle)
        if (
            interrupt_after_phase
            and interrupt_after_phase == completed
            and completed not in {"report", "apply"}
            and phase != "report"
        ):
            state["interrupted"] = True
            state["phase"] = completed
            state["phase_log"] = phase_log
            state["hypothesis"] = hypothesis
            path = _save_state(state)
            return {
                "ok": False,
                "interrupted": True,
                "resume_checkpoint_id": state["checkpoint_id"],
                "checkpoint_path": str(path),
                "phase": completed,
                "next_phase": phase,
                "proposal_only": True,
                "applied": applied,
                "verified": verified,
                "engine": engine,
                "phase_log": phase_log,
            }

    # Report — honest status
    actual_diffs = []
    if apply_result and apply_result.get("applied"):
        actual_diffs = [a.get("unified_diff") for a in apply_result["applied"] if a.get("unified_diff")]

    report = {
        "ok": bool(verified and applied),
        "stop_reason": stop_reason,
        "engine": engine,
        "lifecycle_phases": list(LIFECYCLE_PHASES),
        "attempts": attempt,
        "hypothesis": hypothesis,
        "diagnostics": diagnostics,
        "phase_log": phase_log,
        "resumed": bool(state.get("resumed")),
        "contract": {
            "kind": (contract.get("contract") or contract).get("kind")
            if isinstance(contract.get("contract") or contract, dict)
            else None,
        },
        "proposal": proposal,
        "proposal_only": not applied,
        "applied": applied,
        "verified": verified,
        "actual_diffs": actual_diffs,
        "checks": check_result,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "nested_independent_supervisor": False,
        "claims": {
            "generated_proposal_described_as_implemented": False,
            "generated_proposal_described_as_verified": False,
            "report_uses_actual_diff_and_checks": True,
        },
    }
    # Honesty: if only proposed
    if proposal and not applied:
        report["ok"] = False
        report["status_label"] = "proposal_not_implemented"
    if applied and not verified:
        report["ok"] = False
        report["status_label"] = "applied_not_verified"
    if verified and applied:
        report["status_label"] = "implemented_and_verified"

    out_path = RUNS_DIR / f"codingloop-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    ensure_state()
    out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    report["report_path"] = str(out_path)
    _save_state({**state, "phase": "report", "final": report.get("status_label")})
    return report
