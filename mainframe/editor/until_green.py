"""Multi-turn propose → apply → test until green (deterministic / memory first).

Does not require a loaded local model. When Mode B is available, callers may
pass allow_model=True later; offline accept keeps allow_model=False.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Callable

from mainframe.codingloop.propose import propose_fixes
from mainframe.memory.verified_patches import lookup_verified, remember_verified
from mainframe.patching.apply import apply_batch, inspect_and_snapshot
from mainframe.tools.invoke import invoke, reset_audit

EventSink = Callable[[dict[str, Any]], None]


def _emit(sink: EventSink | None, ev: dict[str, Any]) -> None:
    if sink:
        sink({"id": f"ev_{uuid.uuid4().hex[:8]}", **ev})


def _tests_passed(workspace: Path) -> dict[str, Any]:
    target = "tests" if (workspace / "tests").is_dir() else "."
    call_id = f"call_{uuid.uuid4().hex[:10]}"
    res = invoke("tests", {"target": target}, call_id=call_id, root=workspace)
    body = res.get("result") if isinstance(res.get("result"), dict) else {}
    passed = bool(body.get("passed")) if "passed" in body else bool(res.get("ok") and body.get("exit_code") == 0)
    return {
        "ok": bool(res.get("ok")),
        "passed": passed,
        "exit_code": body.get("exit_code"),
        "call_id": call_id,
        "result": body,
    }


def run_until_green(
    workspace: Path,
    *,
    goal: str,
    max_turns: int = 3,
    allow_model: bool = False,
    sink: EventSink | None = None,
) -> dict[str, Any]:
    """
    Loop: memory lookup → propose → apply → tests.
    Stops on green, impossible, no edits, or max_turns.
    """
    workspace = workspace.resolve()
    reset_audit()
    turns: list[dict[str, Any]] = []
    _emit(sink, {"type": "status", "phase": "until_green_start", "max_turns": max_turns})

    for turn in range(1, max_turns + 1):
        _emit(sink, {"type": "status", "phase": "turn", "turn": turn})

        # Memory via local stdio MCP first (agent-loop path); direct store fallback.
        mem: dict[str, Any] = {"hit": False}
        try:
            from mainframe.mcp.loop import lookup_via_mcp

            mcp_mem = lookup_via_mcp(goal)
            _emit(
                sink,
                {
                    "type": "mcp_tool",
                    "tool": "verified_patch_lookup",
                    "hit": mcp_mem.get("hit"),
                    "endpoint": mcp_mem.get("endpoint"),
                },
            )
            if mcp_mem.get("hit") and mcp_mem.get("edits"):
                mem = {
                    "hit": True,
                    "edits": mcp_mem["edits"],
                    "fingerprint": mcp_mem.get("fingerprint"),
                    "source": "verified_patch_memory_mcp",
                }
        except Exception as exc:  # noqa: BLE001
            _emit(sink, {"type": "mcp_tool", "tool": "verified_patch_lookup", "error": str(exc)})

        if not mem.get("hit"):
            mem = lookup_verified(goal=goal)
            _emit(
                sink,
                {
                    "type": "memory_lookup",
                    "hit": mem.get("hit"),
                    "fingerprint": mem.get("fingerprint"),
                    "via": "direct_fallback",
                },
            )

        if mem.get("hit") and mem.get("edits"):
            edits = list(mem["edits"])
            source = str(mem.get("source") or "verified_patch_memory")
            model_calls = 0
        else:
            prop = propose_fixes(workspace, goal, allow_model=allow_model)
            edits = list(prop.get("edits") or [])
            source = str(prop.get("source") or "propose")
            # Only pure offline sources are zero-cost. "deterministic_then_model"
            # and "model_gated" both invoke Mode B and must count.
            offline_sources = {
                "deterministic_fixture",
                "verified_patch_memory",
                "verified_patch_memory_mcp",
                "import_symbol_align",
            }
            model_calls = 0 if source in offline_sources else 1
            if prop.get("impossible"):
                turns.append(
                    {
                        "turn": turn,
                        "source": source,
                        "impossible": True,
                        "model_calls": model_calls,
                        "prop": prop,
                    }
                )
                _emit(sink, {"type": "done", "green": False, "impossible": True, "turns": turn})
                return {
                    "ok": True,
                    "green": False,
                    "impossible": True,
                    "turns": turns,
                    "reason": prop.get("reason"),
                    "model_calls_total": sum(int(t.get("model_calls") or 0) for t in turns),
                }
            if not edits:
                turns.append(
                    {
                        "turn": turn,
                        "source": source,
                        "no_edits": True,
                        "model_calls": model_calls,
                        "paused": bool(prop.get("paused")),
                    }
                )
                _emit(sink, {"type": "done", "green": False, "no_edits": True, "turns": turn})
                return {
                    "ok": True,
                    "green": False,
                    "no_edits": True,
                    "turns": turns,
                    "paused": bool(prop.get("paused")),
                    "reason": prop.get("reason"),
                    "model_calls_total": sum(int(t.get("model_calls") or 0) for t in turns),
                }

        snap = inspect_and_snapshot(workspace, [e["path"] for e in edits])
        applied = apply_batch(
            workspace,
            edits,
            snapshot_id=str(snap.get("snapshot_id")),
            scope_paths=[e["path"] for e in edits],
        )
        _emit(
            sink,
            {
                "type": "apply",
                "ok": applied.get("ok"),
                "source": source,
                "edits_n": len(edits),
            },
        )
        if not applied.get("ok"):
            turns.append({"turn": turn, "source": source, "apply_ok": False, "applied": applied})
            continue

        test = _tests_passed(workspace)
        _emit(
            sink,
            {
                "type": "tests",
                "passed": test.get("passed"),
                "exit_code": test.get("exit_code"),
            },
        )
        turns.append(
            {
                "turn": turn,
                "source": source,
                "apply_ok": True,
                "tests_passed": test.get("passed"),
                "model_calls": model_calls,
                "memory_hit": bool(mem.get("hit")),
            }
        )
        if test.get("passed"):
            remember_verified(
                goal=goal,
                edits=edits,
                paths=[e["path"] for e in edits],
                tests_ok=True,
                meta={"turns": turn, "source": source},
            )
            _emit(sink, {"type": "done", "green": True, "turns": turn, "source": source})
            return {
                "ok": True,
                "green": True,
                "turns": turns,
                "source": source,
                "memory_saved": True,
                "model_calls_total": sum(int(t.get("model_calls") or 0) for t in turns),
            }

    _emit(sink, {"type": "done", "green": False, "max_turns": True})
    return {
        "ok": True,
        "green": False,
        "max_turns": True,
        "turns": turns,
        "model_calls_total": sum(int(t.get("model_calls") or 0) for t in turns),
    }
