"""Apply FreeForge permissions + cost policy to scheduler command payloads.

Model-tool approvals (tools.exec) do **not** govern these commands.
"""

from __future__ import annotations

from typing import Any

from mainframe.cost_gate import authorize


def authorize_scheduler_command(argv: list[str], *, local: bool = True) -> dict[str, Any]:
    """Gate the command itself before schedule registration or fire."""
    target = "local.scheduler_command"
    gate = authorize("tool", target, local=local)
    # Explicit separation from model-tool approval path
    return {
        "allowed": gate.allowed,
        "gate": gate.to_dict(),
        "governed_by_model_tool_approvals": False,
        "policy_owner": "freeforge",
        "argv": list(argv),
        "reason": gate.reason if not gate.allowed else "local_zero_fee_command_allowed",
    }
