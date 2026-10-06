"""Quota-aware admission control — reserve before dispatch, reconcile after."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe.cost_gate import authorize, load_entitlements
from mainframe.quota.identity import refuse_identity_rotation
from mainframe.quota.ledger import QuotaLedger
from mainframe.quota.retry import from_provider_headers
from mainframe.quota.schedule import record_admit, record_background_deferred, schedule_order
from mainframe.quota.types import ActualUsage, AdmitDecision, Priority, UsageEstimate

# Default local ledger caps (optional inference / fixture workloads).
DEFAULT_LIMITS = {
    "limit_requests": 60,
    "limit_tokens": 100_000,
    "limit_context": 32_000,
    "limit_concurrency": 4,
}


def _entitlement_permits_separate(entitlement_id: str | None) -> bool:
    if not entitlement_id:
        return True  # local bucket
    for ent in load_entitlements():
        if ent.id == entitlement_id:
            # Separate legitimate entitlement only if terms don't allow paid overage/upgrade
            return (
                not ent.allows_paid_overage
                and not ent.allows_automatic_upgrade
                and not ent.billing_dependency
                and not ent.trial
                and not ent.promotional
            )
    # Unknown entitlement id — do not treat as separate capacity multiplier
    return False


class AdmissionController:
    def __init__(self, ledger: QuotaLedger | None = None, path: Path | None = None) -> None:
        self.ledger = ledger or QuotaLedger(path)

    def bind_bucket(
        self,
        *,
        provider_id: str,
        entitlement_id: str | None = None,
        window_id: str = "default",
        limits: dict[str, int] | None = None,
        reset_at: str | None = None,
        reset_unknown: bool = True,
    ) -> str:
        if entitlement_id and not _entitlement_permits_separate(entitlement_id):
            # Collapse to shared local-unverified bucket — no extra capacity
            entitlement_id = None
        lim = {**DEFAULT_LIMITS, **(limits or {})}
        return self.ledger.ensure_bucket(
            provider_id=provider_id,
            entitlement_id=entitlement_id,
            window_id=window_id,
            limit_requests=int(lim["limit_requests"]),
            limit_tokens=int(lim["limit_tokens"]),
            limit_context=int(lim["limit_context"]),
            limit_concurrency=int(lim["limit_concurrency"]),
            reset_at=reset_at,
            reset_unknown=reset_unknown,
        )

    def admit(
        self,
        *,
        provider_id: str,
        estimate: UsageEstimate,
        priority: Priority = "interactive",
        entitlement_id: str | None = None,
        window_id: str = "default",
        limits: dict[str, int] | None = None,
        identity: str | None = None,
        active_identity: str | None = None,
        identity_purpose: str | None = None,
        waiting_background: bool = False,
        require_cost_gate: bool = False,
    ) -> AdmitDecision:
        rot = refuse_identity_rotation(
            provider_id=provider_id,
            requested_identity=identity,
            active_identity=active_identity,
            purpose=identity_purpose,
        )
        if rot.get("refused"):
            return AdmitDecision(
                allowed=False,
                reservation_id=None,
                reason=str(rot["reason"]),
                reset_unknown=False,
                priority=priority,
                denied_code="identity_rotation_refused",
            )

        if require_cost_gate:
            gate = authorize("inference", provider_id, local=provider_id in {"ollama_local", "llamacpp_local"})
            if not gate.allowed:
                return AdmitDecision(
                    allowed=False,
                    reservation_id=None,
                    reason=gate.reason,
                    denied_code=gate.denied_code,
                    priority=priority,
                    reset_unknown=False,
                )

        if priority == "background" and waiting_background:
            # Defer counting for anti-starvation when interactive is also contending
            pass

        bucket = self.bind_bucket(
            provider_id=provider_id,
            entitlement_id=entitlement_id,
            window_id=window_id,
            limits=limits,
        )

        # Priority: if interactive waiting and background would take last slot, defer background
        snap = self.ledger.snapshot(bucket)
        if (
            priority == "background"
            and waiting_background is False
            and snap["remaining"]["concurrency"] <= 1
        ):
            # Still try; schedule_batch handles ordering. Single admit path proceeds.
            record_background_deferred()

        ok, rid, info = self.ledger.try_reserve(bucket, estimate, priority=priority)
        if not ok:
            if priority == "background":
                record_background_deferred()
            return AdmitDecision(
                allowed=False,
                reservation_id=None,
                reason=str(info.get("reason") or "Quota denied"),
                retry_after_s=info.get("retry_after_s"),
                reset_unknown=bool(info.get("reset_unknown", True)),
                priority=priority,
                ledger_snapshot=info.get("snapshot") or snap,
                denied_code=str(info.get("denied_code") or "capacity"),
            )

        record_admit(priority)
        return AdmitDecision(
            allowed=True,
            reservation_id=rid,
            reason="Reserved on local quota ledger.",
            retry_after_s=None,
            reset_unknown=False,
            priority=priority,
            ledger_snapshot=info,
        )

    def admit_batch(self, requests: list[dict[str, Any]]) -> list[AdmitDecision]:
        """Admit multiple requests with interactive-first ordering and anti-starvation."""
        ordered = schedule_order(requests)
        waiting_bg = any(r.get("priority") == "background" for r in requests)
        out: list[AdmitDecision] = []
        for req in ordered:
            out.append(
                self.admit(
                    provider_id=str(req["provider_id"]),
                    estimate=req["estimate"],
                    priority=req.get("priority") or "interactive",
                    entitlement_id=req.get("entitlement_id"),
                    window_id=req.get("window_id") or "default",
                    limits=req.get("limits"),
                    waiting_background=waiting_bg and req.get("priority") == "interactive",
                    identity=req.get("identity"),
                    active_identity=req.get("active_identity"),
                    identity_purpose=req.get("identity_purpose"),
                )
            )
        # Preserve original order in response? Return schedule order results with index
        return out

    def reconcile(self, reservation_id: str, actual: ActualUsage) -> dict[str, Any]:
        return self.ledger.reconcile(reservation_id, actual)

    def release(self, reservation_id: str, *, reason: str = "cancelled") -> dict[str, Any]:
        return self.ledger.release(reservation_id, reason=reason)

    def note_provider_response(
        self,
        bucket_key: str,
        *,
        status: int | None = None,
        headers: dict[str, str] | None = None,
        timeout: bool = False,
        cancelled: bool = False,
        reservation_id: str | None = None,
    ) -> dict[str, Any]:
        signal = from_provider_headers(status, headers, timeout=timeout, cancelled=cancelled)
        if cancelled and reservation_id:
            self.release(reservation_id, reason="cancelled")
        if signal.get("apply_cooldown"):
            self.ledger.set_cooldown(
                bucket_key,
                cooldown_until=signal.get("cooldown_until"),
                reset_at=signal.get("cooldown_until"),
                reset_unknown=bool(signal.get("reset_unknown")),
            )
        if timeout and reservation_id:
            # Conservative: reconcile as unknown usage (keep estimate charged until explicit)
            self.reconcile(reservation_id, ActualUsage(requests=1, unknown=True))
        return signal

    def reload(self) -> None:
        self.ledger.reload()
