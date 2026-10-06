"""Derive important edge cases from the task contract (not only from the patch)."""

from __future__ import annotations

import re
from typing import Any


def derive_edge_cases(contract: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Produce evaluator-side edge case descriptors from desired behavior,
    invariants, and acceptance checks — independent of proposed implementation.
    """
    edges: list[dict[str, Any]] = []
    text = " ".join(
        [
            str(contract.get("desired_behavior") or ""),
            str(contract.get("intent_natural_language") or ""),
            " ".join(str(c) for c in (contract.get("constraints") or [])),
            " ".join(str(i) for i in (contract.get("invariants") or [])),
            " ".join(str(a) for a in (contract.get("acceptance_checks") or [])),
        ]
    ).casefold()

    # Numeric / aggregate heuristics from contract language
    if any(w in text for w in ("sum", "total", "add", "aggregate")):
        edges.append(
            {
                "id": "empty_input",
                "rationale": "contract implies aggregation — empty collection is an edge",
                "source": "task_contract",
            }
        )
        edges.append(
            {
                "id": "single_element",
                "rationale": "single-element collection",
                "source": "task_contract",
            }
        )
    if any(w in text for w in ("negative", "signed", "withdraw", "debit")):
        edges.append(
            {
                "id": "negative_values",
                "rationale": "contract mentions signed/negative behavior",
                "source": "task_contract",
            }
        )
    if "empty" in text or "zero" in text:
        edges.append(
            {
                "id": "zero_or_empty",
                "rationale": "contract explicitly mentions empty/zero",
                "source": "task_contract",
            }
        )

    # Explicit acceptance check ids/names
    for ac in contract.get("acceptance_checks") or []:
        if isinstance(ac, dict):
            edges.append(
                {
                    "id": f"acceptance:{ac.get('id') or ac.get('type')}",
                    "rationale": str(ac),
                    "source": "acceptance_checks",
                }
            )

    for inv in contract.get("invariants") or []:
        if isinstance(inv, dict):
            edges.append(
                {
                    "id": f"invariant:{inv.get('id') or inv.get('type')}",
                    "rationale": str(inv),
                    "source": "invariants",
                }
            )

    # Dedup by id
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for e in edges:
        if e["id"] in seen:
            continue
        seen.add(e["id"])
        out.append(e)
    return out


def edge_ids_from_contract(contract: dict[str, Any]) -> list[str]:
    return [e["id"] for e in derive_edge_cases(contract)]
