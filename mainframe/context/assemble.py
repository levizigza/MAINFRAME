"""Progressive context assembly with critical preservation and additional-read requests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mainframe.context.budget import TokenBudget, default_budget
from mainframe.context.gather import gather_evidence
from mainframe.context.rank import EvidenceItem, rank_items
from mainframe.context.tokens import estimate_tokens, report_token_use
from mainframe.cost_gate import authorize

CRITICAL = frozenset({"contract", "signature", "invariant", "source_pointer", "diagnostic"})


def assemble_context(
    root: Path,
    *,
    request_text: str,
    goal: str | None = None,
    contract: dict[str, Any] | None = None,
    diagnostics_text: str | None = None,
    budget: TokenBudget | None = None,
    constrained: bool = False,
    include_docs_module: str | None = None,
    include_docs_attr: str | None = None,
    probe_inference: bool = True,
) -> dict[str, Any]:
    """
    Assemble progressive context: contract → overview → symbols → ranges → diagnostics.

    Never silently drops critical evidence to meet the token limit. If critical
    items exceed capacity, reports ``critical_overflow`` and requests focused
    additional reads instead of truncating signatures/invariants/pointers.
    """
    gate = authorize("tool", "local.context_assemble", local=True)
    if not gate.allowed:
        return {"ok": False, "cost_gate": gate.to_dict()}

    root = root.resolve()
    budget = budget or default_budget(constrained=constrained)
    items = gather_evidence(
        root,
        request_text=request_text,
        goal=goal,
        contract=contract,
        diagnostics_text=diagnostics_text,
        include_docs_module=include_docs_module,
        include_docs_attr=include_docs_attr,
    )
    ranked = rank_items(items)

    selected: list[EvidenceItem] = []
    omitted: list[dict[str, Any]] = []
    used = 0
    capacity = budget.evidence_capacity

    # Pass 1: always take critical items (may overflow — never silent drop)
    critical_items = [it for it in ranked if it.critical in CRITICAL]
    normal_items = [it for it in ranked if it.critical not in CRITICAL]

    critical_overflow = False
    for it in critical_items:
        # Deduplicate near-zero novelty logs among critical only if not diagnostic-primary
        if it.kind == "log" and it.novelty < 0.15 and any(
            s.id != it.id and s.kind == "log" for s in selected
        ):
            omitted.append(
                {
                    "id": it.id,
                    "reason": "repeated_log_low_novelty",
                    "critical": it.critical,
                }
            )
            continue
        if used + it.tokens_est <= capacity:
            selected.append(it)
            used += it.tokens_est
        else:
            # Cannot silently remove — keep it and flag overflow
            selected.append(it)
            used += it.tokens_est
            critical_overflow = True

    # Pass 2: fill with high relevance/novelty normals
    for it in normal_items:
        if it.novelty < 0.2 and it.kind in {"log", "overview"}:
            omitted.append({"id": it.id, "reason": "low_novelty_or_repeated", "path": it.path})
            continue
        if it.relevance < 0.15:
            omitted.append({"id": it.id, "reason": "low_relevance", "path": it.path})
            continue
        if used + it.tokens_est <= capacity and not critical_overflow:
            selected.append(it)
            used += it.tokens_est
        else:
            omitted.append(
                {
                    "id": it.id,
                    "reason": "budget_or_overflow",
                    "path": it.path,
                    "relevance": it.relevance,
                }
            )

    # Re-rank selected for presentation order
    selected = rank_items(selected)

    # Sufficiency: need at least one signature or diagnostic for repair-like tasks
    has_sig = any(it.critical == "signature" or it.signature for it in selected)
    has_diag = any(it.critical == "diagnostic" for it in selected)
    has_contract = any(it.critical == "contract" for it in selected)
    insufficient = not (has_contract and (has_sig or has_diag))

    additional_reads: list[dict[str, Any]] = []
    if insufficient or critical_overflow:
        # Focused additional read requests — do not invent file contents
        for it in critical_items:
            if it.path and it.start_line:
                additional_reads.append(
                    {
                        "path": it.path,
                        "start_line": it.start_line,
                        "end_line": it.end_line or it.start_line,
                        "reason": "critical_overflow_or_insufficient"
                        if critical_overflow
                        else "evidence_insufficient",
                        "preserve": ["signature", "invariants", "source_pointers"],
                    }
                )
        if not additional_reads:
            # Ask for the most relevant omitted range
            for o in omitted:
                if o.get("path"):
                    additional_reads.append(
                        {
                            "path": o["path"],
                            "reason": "focused_additional_read",
                            "preserve": ["signature", "source_pointers"],
                        }
                    )
                    break

    # Dedup additional reads by path
    seen_paths: set[str] = set()
    uniq_reads: list[dict[str, Any]] = []
    for r in additional_reads:
        p = r.get("path") or ""
        if p in seen_paths:
            continue
        seen_paths.add(p)
        uniq_reads.append(r)

    pack = {
        "sections": {
            "contract": [it.to_dict() for it in selected if it.kind == "contract"],
            "overview": [it.to_dict() for it in selected if it.kind == "overview"],
            "symbols": [it.to_dict() for it in selected if it.kind == "symbol"],
            "ranges": [it.to_dict() for it in selected if it.kind == "range"],
            "diagnostics": [
                it.to_dict() for it in selected if it.kind in {"diagnostic", "log"}
            ],
            "docs": [it.to_dict() for it in selected if it.kind == "docs"],
            "invariants": [it.to_dict() for it in selected if it.kind == "invariant"],
        },
        "items": [it.to_dict() for it in selected],
    }

    assembled_text = _render_text(selected)
    token_report = report_token_use(assembled_text, probe_inference=probe_inference)

    return {
        "ok": True,
        "budget": budget.to_dict(),
        "evidence_tokens_est": used,
        "capacity": capacity,
        "critical_overflow": critical_overflow,
        "silently_dropped_critical": False,  # hard guarantee
        "insufficient_evidence": insufficient,
        "additional_reads": uniq_reads,
        "omitted": omitted,
        "pack": pack,
        "assembled_text": assembled_text,
        "token_use": token_report,
        "preserved": {
            "complete_signatures": [
                it.signature for it in selected if it.signature
            ],
            "source_pointers": [p for it in selected for p in it.pointers],
            "essential_invariants": [
                it.content for it in selected if it.critical == "invariant"
            ],
        },
        "model_service_used": False,
        "paid_embedding_used": False,
    }


def _render_text(items: list[EvidenceItem]) -> str:
    parts: list[str] = []
    for it in items:
        header = f"## {it.kind}:{it.id} [{it.critical}]"
        if it.pointers:
            header += f" ptr={it.pointers}"
        if it.signature:
            header += f"\nSIG: {it.signature}"
        parts.append(header + "\n" + it.content)
    return "\n\n".join(parts)
