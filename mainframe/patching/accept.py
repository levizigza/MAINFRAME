"""Acceptance: duplicates, Unicode, concurrent edits, interrupted multi-file write."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from mainframe.config import ROOT
from mainframe.patching.apply import apply_batch, inspect_and_snapshot, rollback_batch
from mainframe.patching.validate import validate_batch

FIXTURE = ROOT / "docs" / "patching" / "fixtures" / "precise_lab"


def run_patching_accept() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    FIXTURE.mkdir(parents=True, exist_ok=True)

    # --- Files ---
    dup = FIXTURE / "dup.py"
    dup.write_bytes(
        b"def f():\n    return 1  # marker\n\ndef g():\n    return 1  # marker\n"
    )
    uni = FIXTURE / "unicode.txt"
    # UTF-8 BOM + CRLF + Unicode
    uni.write_bytes("\ufeffline one — café\r\nline two\r\n".encode("utf-8-sig"))
    a = FIXTURE / "a.py"
    b = FIXTURE / "b.py"
    a.write_text("value = 1\n", encoding="utf-8", newline="\n")
    b.write_text("value = 2\n", encoding="utf-8", newline="\n")
    user = FIXTURE / "user_notes.txt"
    user.write_text("keep me\n", encoding="utf-8")

    # --- Duplicate block rejection ---
    snap_dup = inspect_and_snapshot(FIXTURE, ["dup.py"])
    v_dup = validate_batch(
        FIXTURE,
        [{"path": "dup.py", "old": "return 1  # marker", "new": "return 2  # marker"}],
        snapshot_id=snap_dup["snapshot_id"],
    )
    checks.append(
        {
            "id": "reject_ambiguous_duplicate_blocks",
            "ok": (
                v_dup.get("ok") is False
                and any(e.get("error") == "ambiguous_replacement" for e in v_dup.get("errors") or [])
                and v_dup.get("writes_executed") is False
            ),
            "detail": v_dup,
        }
    )

    # --- Unicode + CRLF preserved ---
    snap_u = inspect_and_snapshot(FIXTURE, ["unicode.txt"])
    sha_u = snap_u["files"]["unicode.txt"]["sha256"]
    applied_u = apply_batch(
        FIXTURE,
        [
            {
                "path": "unicode.txt",
                "old": "line one — café",
                "new": "line one — café (ok)",
                "content_sha256": sha_u,
            }
        ],
        snapshot_id=snap_u["snapshot_id"],
    )
    raw_u = uni.read_bytes()
    checks.append(
        {
            "id": "unicode_and_crlf_preserved",
            "ok": (
                applied_u.get("ok") is True
                and raw_u.startswith(b"\xef\xbb\xbf")
                and b"\r\n" in raw_u
                and "café (ok)".encode("utf-8") in raw_u
            ),
            "detail": {
                "io": (applied_u.get("applied") or [{}])[0].get("io"),
                "head": raw_u[:40],
            },
        }
    )

    # --- Concurrent user edit → stale reject ---
    snap_a = inspect_and_snapshot(FIXTURE, ["a.py"])
    # User edits after inspection
    a.write_text("value = 1\n# user concurrent edit\n", encoding="utf-8")
    stale = apply_batch(
        FIXTURE,
        [{"path": "a.py", "old": "value = 1", "new": "value = 9"}],
        snapshot_id=snap_a["snapshot_id"],
    )
    checks.append(
        {
            "id": "reject_concurrent_user_edit",
            "ok": (
                stale.get("ok") is False
                and stale.get("error") == "stale_patch_or_concurrent_edit"
                and "# user concurrent edit" in a.read_text(encoding="utf-8")
                and "value = 9" not in a.read_text(encoding="utf-8")
            ),
            "detail": stale,
        }
    )
    # Restore a.py for later
    a.write_text("value = 1\n", encoding="utf-8")

    # --- Interrupted multi-file write + recovery ---
    snap_ab = inspect_and_snapshot(FIXTURE, ["a.py", "b.py"])
    user_before = user.read_text(encoding="utf-8")
    interrupted = apply_batch(
        FIXTURE,
        [
            {"path": "a.py", "old": "value = 1", "new": "value = 10"},
            {"path": "b.py", "old": "value = 2", "new": "value = 20"},
        ],
        snapshot_id=snap_ab["snapshot_id"],
        simulate_interrupt_after=1,
    )
    checks.append(
        {
            "id": "interrupted_multi_file_partial",
            "ok": (
                interrupted.get("ok") is False
                and interrupted.get("error") == "interrupted_multi_file_write"
                and interrupted.get("filesystem_atomicity_claimed") is False
                and "value = 10" in a.read_text(encoding="utf-8")
                and "value = 2" in b.read_text(encoding="utf-8")  # second not written
            ),
            "detail": {
                "batch_id": interrupted.get("batch_id"),
                "applied": interrupted.get("applied"),
            },
        }
    )
    # Unrelated user file should still be intact
    user.write_text("keep me\nuser added line during agent work\n", encoding="utf-8")
    rec = rollback_batch(FIXTURE, interrupted["batch_id"])
    checks.append(
        {
            "id": "recover_consistent_without_discarding_unrelated",
            "ok": (
                rec.get("ok") is True
                and rec.get("working_tree_reset") is False
                and rec.get("entire_working_tree_reset") is not True
                and "value = 1" in a.read_text(encoding="utf-8")
                and "value = 2" in b.read_text(encoding="utf-8")
                and "user added line during agent work" in user.read_text(encoding="utf-8")
                and rec.get("filesystem_atomicity_claimed") is False
            ),
            "detail": {
                "recovery": rec,
                "a": a.read_text(encoding="utf-8"),
                "user": user.read_text(encoding="utf-8"),
            },
        }
    )

    # --- Successful multi-file bound to snapshot with reviewable diffs ---
    a.write_text("value = 1\n", encoding="utf-8")
    b.write_text("value = 2\n", encoding="utf-8")
    snap2 = inspect_and_snapshot(FIXTURE, ["a.py", "b.py"])
    ok_batch = apply_batch(
        FIXTURE,
        [
            {"path": "a.py", "old": "value = 1", "new": "value = 3"},
            {"path": "b.py", "old": "value = 2", "new": "value = 4"},
        ],
        snapshot_id=snap2["snapshot_id"],
    )
    checks.append(
        {
            "id": "valid_batch_reviewable_diffs",
            "ok": (
                ok_batch.get("ok") is True
                and len(ok_batch.get("reviewable_diffs") or []) == 2
                and all("---" in d or "@@" in d for d in ok_batch["reviewable_diffs"])
                and ok_batch.get("filesystem_atomicity_claimed") is False
            ),
            "detail": {
                "batch_id": ok_batch.get("batch_id"),
                "diffs": ok_batch.get("reviewable_diffs"),
            },
        }
    )

    # Selective rollback of that batch leaves user file
    user_txt = user.read_text(encoding="utf-8")
    rb = rollback_batch(FIXTURE, ok_batch["batch_id"])
    checks.append(
        {
            "id": "selective_rollback_agent_owned_only",
            "ok": (
                rb.get("ok")
                and "value = 1" in a.read_text(encoding="utf-8")
                and "value = 2" in b.read_text(encoding="utf-8")
                and user.read_text(encoding="utf-8") == user_txt
                and rb.get("entire_working_tree_reset") is False
            ),
            "detail": rb,
        }
    )

    passed = sum(1 for c in checks if c["ok"])
    failed = len(checks) - passed
    return {
        "ok": failed == 0,
        "passed": passed,
        "failed": failed,
        "checks": checks,
        "filesystem_atomicity_claimed": False,
    }
