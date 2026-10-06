"""Persistent quota ledger — reservations survive process restart."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.config import STATE_DIR, ensure_state
from mainframe.quota.types import ActualUsage, UsageEstimate

LEDGER_PATH = STATE_DIR / "quota_ledger.sqlite"

_LOCK = threading.RLock()


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect(path: Path | None = None) -> sqlite3.Connection:
    ensure_state()
    p = path or LEDGER_PATH
    conn = sqlite3.connect(str(p), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS buckets (
            key TEXT PRIMARY KEY,
            provider_id TEXT NOT NULL,
            entitlement_id TEXT,
            window_id TEXT NOT NULL,
            limit_requests INTEGER NOT NULL,
            limit_tokens INTEGER NOT NULL,
            limit_context INTEGER NOT NULL,
            limit_concurrency INTEGER NOT NULL,
            reset_at TEXT,
            reset_unknown INTEGER NOT NULL DEFAULT 0,
            cooldown_until TEXT,
            meta_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reservations (
            id TEXT PRIMARY KEY,
            bucket_key TEXT NOT NULL,
            state TEXT NOT NULL,
            priority TEXT NOT NULL,
            est_requests INTEGER NOT NULL,
            est_tokens INTEGER NOT NULL,
            est_context INTEGER NOT NULL,
            est_tool INTEGER NOT NULL,
            est_reasoning INTEGER NOT NULL,
            act_requests INTEGER,
            act_tokens INTEGER,
            act_context INTEGER,
            act_tool INTEGER,
            act_reasoning INTEGER,
            unknown_usage INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(bucket_key) REFERENCES buckets(key)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            at TEXT NOT NULL,
            kind TEXT NOT NULL,
            payload_json TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


class QuotaLedger:
    """Thread-safe local quota ledger with file persistence."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or LEDGER_PATH
        self._conn = _connect(self.path)

    def close(self) -> None:
        with _LOCK:
            self._conn.close()

    def ensure_bucket(
        self,
        *,
        provider_id: str,
        entitlement_id: str | None,
        window_id: str,
        limit_requests: int,
        limit_tokens: int,
        limit_context: int,
        limit_concurrency: int,
        reset_at: str | None = None,
        reset_unknown: bool = False,
    ) -> str:
        key = f"{provider_id}|{entitlement_id or 'local'}|{window_id}"
        with _LOCK:
            cur = self._conn.execute("SELECT key FROM buckets WHERE key=?", (key,))
            if cur.fetchone() is None:
                self._conn.execute(
                    """
                    INSERT INTO buckets(
                        key, provider_id, entitlement_id, window_id,
                        limit_requests, limit_tokens, limit_context, limit_concurrency,
                        reset_at, reset_unknown, cooldown_until, meta_json
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,NULL,'{}')
                    """,
                    (
                        key,
                        provider_id,
                        entitlement_id,
                        window_id,
                        int(limit_requests),
                        int(limit_tokens),
                        int(limit_context),
                        int(limit_concurrency),
                        reset_at,
                        1 if reset_unknown else 0,
                    ),
                )
                self._conn.commit()
            return key

    def _active_reservations(self, bucket_key: str) -> list[sqlite3.Row]:
        return list(
            self._conn.execute(
                "SELECT * FROM reservations WHERE bucket_key=? AND state='reserved'",
                (bucket_key,),
            )
        )

    def snapshot(self, bucket_key: str) -> dict[str, Any]:
        with _LOCK:
            b = self._conn.execute("SELECT * FROM buckets WHERE key=?", (bucket_key,)).fetchone()
            if b is None:
                return {"error": "missing_bucket", "key": bucket_key}
            rows = self._active_reservations(bucket_key)
            used_req = sum(int(r["est_requests"]) for r in rows)
            used_tok = sum(
                int(r["est_tokens"]) + int(r["est_context"]) + int(r["est_tool"]) + int(r["est_reasoning"])
                for r in rows
            )
            used_ctx = sum(int(r["est_context"]) for r in rows)
            conc = len(rows)
            return {
                "bucket_key": bucket_key,
                "provider_id": b["provider_id"],
                "entitlement_id": b["entitlement_id"],
                "window_id": b["window_id"],
                "limits": {
                    "requests": b["limit_requests"],
                    "tokens": b["limit_tokens"],
                    "context": b["limit_context"],
                    "concurrency": b["limit_concurrency"],
                },
                "in_flight": {
                    "reservations": conc,
                    "requests": used_req,
                    "tokens": used_tok,
                    "context": used_ctx,
                    "concurrency": conc,
                },
                "remaining": {
                    "requests": max(0, int(b["limit_requests"]) - used_req),
                    "tokens": max(0, int(b["limit_tokens"]) - used_tok),
                    "context": max(0, int(b["limit_context"]) - used_ctx),
                    "concurrency": max(0, int(b["limit_concurrency"]) - conc),
                },
                "reset_at": b["reset_at"],
                "reset_unknown": bool(b["reset_unknown"]),
                "cooldown_until": b["cooldown_until"],
            }

    def set_cooldown(
        self,
        bucket_key: str,
        *,
        cooldown_until: str | None,
        reset_at: str | None = None,
        reset_unknown: bool = False,
    ) -> None:
        with _LOCK:
            self._conn.execute(
                """
                UPDATE buckets SET cooldown_until=?, reset_at=COALESCE(?, reset_at),
                    reset_unknown=? WHERE key=?
                """,
                (cooldown_until, reset_at, 1 if reset_unknown else 0, bucket_key),
            )
            self._log("cooldown", {"bucket_key": bucket_key, "cooldown_until": cooldown_until, "reset_unknown": reset_unknown})
            self._conn.commit()

    def try_reserve(
        self,
        bucket_key: str,
        estimate: UsageEstimate,
        *,
        priority: str,
        reservation_id: str | None = None,
    ) -> tuple[bool, str | None, dict[str, Any]]:
        """Atomically reserve if capacity remains. Returns (ok, id, snapshot_or_deny)."""
        with _LOCK:
            b = self._conn.execute("SELECT * FROM buckets WHERE key=?", (bucket_key,)).fetchone()
            if b is None:
                return False, None, {"denied_code": "missing_bucket", "reason": "Quota bucket missing."}

            now = datetime.now(timezone.utc)
            cool = b["cooldown_until"]
            if cool:
                try:
                    cdt = datetime.fromisoformat(cool.replace("Z", "+00:00"))
                    if cdt > now:
                        snap = self.snapshot(bucket_key)
                        return False, None, {
                            "denied_code": "cooldown",
                            "reason": "Provider cooldown active after rate limit / pause.",
                            "retry_after_s": max(0.0, (cdt - now).total_seconds()),
                            "reset_unknown": False,
                            "snapshot": snap,
                        }
                except ValueError:
                    pass

            rows = self._active_reservations(bucket_key)
            used_req = sum(int(r["est_requests"]) for r in rows)
            used_tok = sum(
                int(r["est_tokens"]) + int(r["est_context"]) + int(r["est_tool"]) + int(r["est_reasoning"])
                for r in rows
            )
            used_ctx = sum(int(r["est_context"]) for r in rows)
            conc = len(rows)

            need_tok = estimate.total_tokens()
            if used_req + estimate.requests > int(b["limit_requests"]):
                return False, None, self._deny_capacity("requests", b, used_req, estimate.requests)
            if used_tok + need_tok > int(b["limit_tokens"]):
                return False, None, self._deny_capacity("tokens", b, used_tok, need_tok)
            if used_ctx + estimate.context_tokens > int(b["limit_context"]):
                return False, None, self._deny_capacity("context", b, used_ctx, estimate.context_tokens)
            if conc + 1 > int(b["limit_concurrency"]):
                return False, None, self._deny_capacity("concurrency", b, conc, 1)

            rid = reservation_id or str(uuid.uuid4())
            ts = _utc()
            self._conn.execute(
                """
                INSERT INTO reservations(
                    id, bucket_key, state, priority,
                    est_requests, est_tokens, est_context, est_tool, est_reasoning,
                    created_at, updated_at
                ) VALUES (?,?, 'reserved', ?, ?,?,?,?,?, ?,?)
                """,
                (
                    rid,
                    bucket_key,
                    priority,
                    int(estimate.requests),
                    int(estimate.tokens),
                    int(estimate.context_tokens),
                    int(estimate.tool_overhead_tokens),
                    int(estimate.reasoning_overhead_tokens),
                    ts,
                    ts,
                ),
            )
            self._log("reserve", {"id": rid, "bucket_key": bucket_key, "estimate": estimate.to_dict(), "priority": priority})
            self._conn.commit()
            return True, rid, self.snapshot(bucket_key)

    def _deny_capacity(self, dim: str, b: sqlite3.Row, used: int, need: int) -> dict[str, Any]:
        snap = self.snapshot(b["key"])
        reset_unknown = bool(b["reset_unknown"]) or not b["reset_at"]
        retry_after_s = None
        if b["reset_at"] and not reset_unknown:
            try:
                rdt = datetime.fromisoformat(str(b["reset_at"]).replace("Z", "+00:00"))
                retry_after_s = max(0.0, (rdt - datetime.now(timezone.utc)).total_seconds())
                reset_unknown = False
            except ValueError:
                reset_unknown = True
                retry_after_s = None
        return {
            "denied_code": f"capacity_{dim}",
            "reason": (
                f"Local quota ledger lacks {dim} capacity "
                f"(in_use={used}, need={need}, limit={b[f'limit_{dim}' if dim != 'tokens' else 'limit_tokens']})."
            ),
            "retry_after_s": retry_after_s,
            "reset_unknown": reset_unknown,
            "snapshot": snap,
        }

    def reconcile(self, reservation_id: str, actual: ActualUsage) -> dict[str, Any]:
        """Replace estimate with actual; unknown usage kept conservatively (max of est/actual)."""
        with _LOCK:
            row = self._conn.execute("SELECT * FROM reservations WHERE id=?", (reservation_id,)).fetchone()
            if row is None:
                return {"ok": False, "error": "missing_reservation"}
            if row["state"] != "reserved":
                return {"ok": False, "error": f"bad_state:{row['state']}"}

            def pick(est: int, act: int | None, unknown: bool) -> int:
                if act is None or unknown:
                    # Conservative: keep estimate (do not free capacity on unknown)
                    return est
                # If actual higher, charge more; if lower, release difference
                return int(act)

            unknown = bool(actual.unknown) or (
                actual.tokens is None and actual.context_tokens is None
            )
            act_req = pick(int(row["est_requests"]), actual.requests if actual.requests else None, False)
            # requests always at least 1 if we ran
            if actual.requests:
                act_req = int(actual.requests)
            act_tok = pick(int(row["est_tokens"]), actual.tokens, unknown)
            act_ctx = pick(int(row["est_context"]), actual.context_tokens, unknown)
            act_tool = pick(int(row["est_tool"]), actual.tool_overhead_tokens, unknown)
            act_rea = pick(int(row["est_reasoning"]), actual.reasoning_overhead_tokens, unknown)

            # When known and lower than estimate, shrink held amounts by updating est_* to actual
            # (in-flight capacity uses est_* columns).
            ts = _utc()
            self._conn.execute(
                """
                UPDATE reservations SET
                    state='reconciled',
                    est_requests=?, est_tokens=?, est_context=?, est_tool=?, est_reasoning=?,
                    act_requests=?, act_tokens=?, act_context=?, act_tool=?, act_reasoning=?,
                    unknown_usage=?, updated_at=?
                WHERE id=?
                """,
                (
                    act_req,
                    act_tok,
                    act_ctx,
                    act_tool,
                    act_rea,
                    act_req,
                    actual.tokens,
                    actual.context_tokens,
                    actual.tool_overhead_tokens,
                    actual.reasoning_overhead_tokens,
                    1 if unknown else 0,
                    ts,
                    reservation_id,
                ),
            )
            # After reconcile, reservation no longer in-flight — move off reserved
            # (state already reconciled; active query filters state='reserved')
            self._log(
                "reconcile",
                {
                    "id": reservation_id,
                    "unknown": unknown,
                    "charged_tokens": act_tok + act_ctx + act_tool + act_rea,
                },
            )
            self._conn.commit()
            return {
                "ok": True,
                "reservation_id": reservation_id,
                "unknown_usage": unknown,
                "charged": {
                    "requests": act_req,
                    "tokens": act_tok,
                    "context": act_ctx,
                    "tool": act_tool,
                    "reasoning": act_rea,
                },
            }

    def release(self, reservation_id: str, *, reason: str = "cancelled") -> dict[str, Any]:
        with _LOCK:
            row = self._conn.execute("SELECT * FROM reservations WHERE id=?", (reservation_id,)).fetchone()
            if row is None:
                return {"ok": False, "error": "missing_reservation"}
            if row["state"] != "reserved":
                return {"ok": False, "error": f"bad_state:{row['state']}"}
            self._conn.execute(
                "UPDATE reservations SET state='released', updated_at=? WHERE id=?",
                (_utc(), reservation_id),
            )
            self._log("release", {"id": reservation_id, "reason": reason})
            self._conn.commit()
            return {"ok": True, "released": reservation_id, "reason": reason}

    def _log(self, kind: str, payload: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT INTO events(at, kind, payload_json) VALUES (?,?,?)",
            (_utc(), kind, json.dumps(payload)),
        )

    def reload(self) -> "QuotaLedger":
        """Re-open connection — simulates process restart reading persisted state."""
        with _LOCK:
            self._conn.close()
            self._conn = _connect(self.path)
        return self
