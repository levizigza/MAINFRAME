"""Load measured evidence artifacts — never invent success metrics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mainframe.config import ROOT

HELDOUT_JSON = ROOT / "docs" / "eval" / "workloads" / "HELDOUT_EVAL.json"
HELDOUT_MD = ROOT / "docs" / "eval" / "workloads" / "HELDOUT_EVAL.md"
DISABLE_POLICY = ROOT / "docs" / "eval" / "workloads" / "feature_disable_policy.json"
COST_AUDIT = ROOT / "docs" / "COST_AUDIT.json"
RELEASE = ROOT / "docs" / "RELEASE.json"
PROVIDERS = ROOT / "docs" / "PROVIDERS.md"
CODINGBENCH_DIR = ROOT / "docs" / "eval" / "coding_benchmark"


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def load_evidence() -> dict[str, Any]:
    heldout = _load_json(HELDOUT_JSON) or {}
    disable = _load_json(DISABLE_POLICY) or {}
    cost = _load_json(COST_AUDIT) or {}
    release = _load_json(RELEASE) or {}

    # Prefer published codingbench report if present
    cb_report = None
    for cand in (
        CODINGBENCH_DIR / "RESULTS.json",
        CODINGBENCH_DIR / "report.json",
        ROOT / ".mainframe" / "runs",
    ):
        if cand.is_file() and cand.suffix == ".json":
            cb_report = _load_json(cand)
            break
    if cb_report is None and (ROOT / ".mainframe" / "runs").is_dir():
        runs = sorted(
            (ROOT / ".mainframe" / "runs").glob("codingbench-*.json"),
            reverse=True,
        )
        if runs:
            cb_report = _load_json(runs[0])

    return {
        "heldout": heldout,
        "heldout_md_present": HELDOUT_MD.is_file(),
        "disable_policy": disable,
        "cost_audit": cost,
        "release": release,
        "providers_doc_present": PROVIDERS.is_file(),
        "codingbench_report": cb_report,
        "sources": {
            "heldout": str(HELDOUT_JSON.relative_to(ROOT)).replace("\\", "/")
            if HELDOUT_JSON.is_file()
            else None,
            "disable_policy": str(DISABLE_POLICY.relative_to(ROOT)).replace("\\", "/")
            if DISABLE_POLICY.is_file()
            else None,
            "cost_audit": str(COST_AUDIT.relative_to(ROOT)).replace("\\", "/")
            if COST_AUDIT.is_file()
            else None,
            "providers": "docs/PROVIDERS.md",
        },
    }
