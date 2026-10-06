"""Database migration recovery and saved-workflow migrate."""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from mainframe.config import STATE_DIR, ensure_state
from mainframe.workflows.load import load_fixture, materialize_fixture
from mainframe.workflows.receipts import WorkflowReceiptStore
from mainframe.workflows.schema import FORMAT_VERSION, normalize_workflow
from mainframe.workflows.validate import validate_workflow


def migrate_workflow_doc(doc: dict[str, Any]) -> dict[str, Any]:
    """Upgrade a saved workflow document to the current format version."""
    before = doc.get("format_version")
    # Legacy alias seen in early drafts
    if before in (None, "0.9", "0.1"):
        doc = dict(doc)
        doc["format_version"] = FORMAT_VERSION
    normalized = normalize_workflow(doc)
    validation = validate_workflow(normalized)
    ok = bool(validation.get("ok")) if isinstance(validation, dict) else False
    return {
        "ok": ok,
        "from_version": before,
        "to_version": normalized.get("format_version"),
        "workflow_id": normalized.get("id"),
        "validation": validation,
        "workflow": normalized,
    }


def migrate_saved_workflow(
    *,
    fixture: str | None = None,
    path: Path | str | None = None,
    dest: Path | None = None,
) -> dict[str, Any]:
    ensure_state()
    if fixture:
        raw = load_fixture(fixture)
        # Simulate an older saved copy with legacy version tag
        legacy = dict(raw)
        legacy["format_version"] = "0.9"
        result = migrate_workflow_doc(legacy)
        out_dir = dest or (STATE_DIR / "workflows" / "migrated" / fixture)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "workflow.json"
        if result["ok"]:
            out_path.write_text(
                json.dumps(result["workflow"], indent=2) + "\n", encoding="utf-8"
            )
            # Keep fixture data beside it for offline use
            materialize_fixture(fixture, out_dir / "_fixture_copy")
        result["saved_to"] = str(out_path)
        result["source"] = f"fixture:{fixture}"
        return result

    if path:
        p = Path(path)
        raw = json.loads(p.read_text(encoding="utf-8"))
        result = migrate_workflow_doc(raw)
        out = dest or (p.parent / "workflow.migrated.json")
        if result["ok"]:
            Path(out).write_text(
                json.dumps(result["workflow"], indent=2) + "\n", encoding="utf-8"
            )
        result["saved_to"] = str(out)
        result["source"] = str(p)
        return result

    return {"ok": False, "error": "fixture_or_path_required"}


def recover_workflow_db(db_path: Path | None = None) -> dict[str, Any]:
    """
    Prove migration recovery: open a deliberately-old schema DB, then let
    WorkflowReceiptStore migrate additive columns.
    """
    ensure_state()
    tmp = Path(tempfile.mkdtemp(prefix="mf-migrate-"))
    legacy = tmp / "legacy_receipts.sqlite"
    conn = sqlite3.connect(str(legacy))
    conn.executescript(
        """
        CREATE TABLE workflow_runs (
          run_id TEXT PRIMARY KEY,
          workflow_id TEXT NOT NULL,
          format_version TEXT NOT NULL,
          state TEXT NOT NULL,
          inputs_json TEXT NOT NULL,
          outputs_json TEXT,
          error TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE step_receipts (
          receipt_id TEXT PRIMARY KEY,
          run_id TEXT NOT NULL,
          step_id TEXT NOT NULL,
          kind TEXT NOT NULL,
          state TEXT NOT NULL,
          attempt INTEGER NOT NULL,
          output_json TEXT,
          artifact_refs_json TEXT,
          checkpoint_json TEXT,
          error TEXT,
          created_at TEXT NOT NULL
        );
        CREATE TABLE effect_index (
          operation_id TEXT PRIMARY KEY,
          run_id TEXT NOT NULL,
          step_id TEXT NOT NULL,
          effect_json TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE concurrency (
          slot_key TEXT PRIMARY KEY,
          holder_run_id TEXT,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE control (
          key TEXT PRIMARY KEY,
          value_json TEXT NOT NULL
        );
        INSERT INTO workflow_runs(
          run_id, workflow_id, format_version, state, inputs_json, created_at, updated_at
        ) VALUES (
          'run_legacy','wf_demo','1.0','completed','{}','2026-01-01T00:00:00+00:00',
          '2026-01-01T00:00:00+00:00'
        );
        """
    )
    conn.commit()
    conn.close()

    # Before migrate: cancel_requested missing
    conn = sqlite3.connect(str(legacy))
    cols_before = {r[1] for r in conn.execute("PRAGMA table_info(workflow_runs)").fetchall()}
    conn.close()

    store = WorkflowReceiptStore(path=legacy)
    conn = sqlite3.connect(str(legacy))
    cols_after = {r[1] for r in conn.execute("PRAGMA table_info(workflow_runs)").fetchall()}
    row = conn.execute(
        "SELECT run_id, cancel_requested FROM workflow_runs WHERE run_id='run_legacy'"
    ).fetchone()
    conn.close()

    ok = (
        "cancel_requested" not in cols_before
        and "cancel_requested" in cols_after
        and row is not None
        and row[1] == 0
    )
    # Keep a copy under state for inspection
    keep = (db_path or (STATE_DIR / "migrate_recovery" / "recovered_receipts.sqlite"))
    keep.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(legacy, keep)
    shutil.rmtree(tmp, ignore_errors=True)
    return {
        "ok": ok,
        "cols_before": sorted(cols_before),
        "cols_after": sorted(cols_after),
        "legacy_row_preserved": row[0] if row else None,
        "recovered_db": str(keep),
        "store_path": str(store.path),
    }
