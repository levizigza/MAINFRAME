"""
Central capability & cost gate.

Enforcement boundary: every inference, connector, search, storage, remote
execution, auxiliary model call, retry, summary, tool, and nested integration
must call ``authorize()`` **before** dispatch. Local zero-fee ops are eligible.
External ops need current verified free entitlement evidence — not trials,
promos, unknown pricing, paid overages, or auto-upgrades.

A published token price of $0 is **not** treated as zero-cost (egress, seats,
metered adjacent services, and account billing risk remain).

There is **no** runtime switch that silently enables spending. Env vars such as
ENABLE_SPENDING / ALLOW_PAID / FORCE_PAID are ignored and logged as denied.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from mainframe.config import ROOT, STATE_DIR, ensure_state
from mainframe.eligibility import (
    DISABLED_PROVIDERS,
    ELIGIBLE_PROVIDERS,
    LOOPBACK_HOSTS,
    is_loopback_url,
)

CapabilityKind = Literal[
    "inference",
    "connector",
    "search",
    "storage",
    "remote_execution",
    "tool",
    "auxiliary",  # retries, summaries, nested model calls
]

ENTITLEMENTS_PATH = STATE_DIR / "entitlements.json"

# Names that look like spend unlocks — never honored.
SPENDING_SWITCH_NAMES = frozenset(
    {
        "ENABLE_SPENDING",
        "ALLOW_PAID",
        "FORCE_PAID",
        "MAINFRAME_ALLOW_PAID",
        "FREEFORGE_ALLOW_PAID",
        "ALLOW_BILLING",
        "UNLOCK_PAID_ROUTES",
        "AUTO_UPGRADE",
    }
)

# Host patterns for known billable / promo cloud endpoints (fake or real).
PAID_ENDPOINT_HOST_SUFFIXES = (
    "openai.com",
    "api.openai.com",
    "anthropic.com",
    "api.anthropic.com",
    "googleapis.com",
    "generativelanguage.googleapis.com",
    "amazonaws.com",
    "bedrock.",
    "azure.com",
    "openai.azure.com",
    "mistral.ai",
    "api.mistral.ai",
    "groq.com",
    "together.xyz",
    "fireworks.ai",
    "replicate.com",
    "api-inference.huggingface.co",
    "supabase.co",
    "firebaseio.com",
    "mongodb.net",
    "neon.tech",
    "planetscale.com",
    "algolia.net",
    "elastic-cloud.com",
    "sentry.io",
    "segment.io",
    "posthog.com",
)

# Model aliases that resolve to hosted billable stacks — blocked even if "free tier".
PAID_MODEL_ALIASES = frozenset(
    {
        "gpt-4",
        "gpt-4o",
        "gpt-4-turbo",
        "gpt-3.5-turbo",
        "o1",
        "o1-mini",
        "o3",
        "o3-mini",
        "claude-3-opus",
        "claude-3-sonnet",
        "claude-3-haiku",
        "claude-3-5-sonnet",
        "claude-opus-4",
        "claude-sonnet-4",
        "gemini-pro",
        "gemini-1.5-pro",
        "gemini-2.0-flash",
        "command-r-plus",
    }
)

# Tools that became / are chargeable — denied until registered local-free.
CHARGEABLE_TOOL_IDS = frozenset(
    {
        "web_search_paid",
        "browserbase_cloud",
        "remote_sandbox",
        "s3_upload",
        "vector_cloud_index",
        "stripe_billing_probe",
    }
)

# Credential-shaped env keys never forwarded into untrusted child processes.
CREDENTIAL_ENV_PATTERNS = (
    re.compile(r"(?i)api[_-]?key"),
    re.compile(r"(?i)secret"),
    re.compile(r"(?i)token"),
    re.compile(r"(?i)password"),
    re.compile(r"(?i)authorization"),
    re.compile(r"(?i)bearer"),
    re.compile(r"(?i)aws_"),
    re.compile(r"(?i)azure_"),
    re.compile(r"(?i)openai"),
    re.compile(r"(?i)anthropic"),
    re.compile(r"(?i)private[_-]?key"),
)


@dataclass
class GateDecision:
    allowed: bool
    capability: CapabilityKind
    target: str
    reason: str
    local_zero_fee: bool = False
    entitlement_id: str | None = None
    denied_code: str | None = None
    spending_switch_attempted: bool = False
    zero_token_price_rejected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EntitlementEvidence:
    """Verified free entitlement — must be current, non-trial, non-promo."""

    id: str
    capability: CapabilityKind
    target: str
    verified_at: str
    expires_at: str
    usage_terms: str
    billing_dependency: bool
    paid_subscription_dependency: bool
    trial: bool
    promotional: bool
    allows_paid_overage: bool
    allows_automatic_upgrade: bool
    pricing_known: bool
    zero_token_price_only: bool = False  # if True → still not enough

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str) -> datetime | None:
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def load_entitlements() -> list[EntitlementEvidence]:
    ensure_state()
    if not ENTITLEMENTS_PATH.exists():
        # Default: no external entitlements on file.
        ENTITLEMENTS_PATH.write_text(
            json.dumps(
                {
                    "note": (
                        "Only verified free entitlements belong here. "
                        "Trials, promos, unknown pricing, and billing-linked accounts are invalid."
                    ),
                    "entitlements": [],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return []
    raw = json.loads(ENTITLEMENTS_PATH.read_text(encoding="utf-8"))
    out: list[EntitlementEvidence] = []
    for item in raw.get("entitlements") or []:
        try:
            out.append(EntitlementEvidence(**item))
        except TypeError:
            continue
    return out


def spending_switch_attempted() -> bool:
    for name in SPENDING_SWITCH_NAMES:
        if os.environ.get(name):
            return True
    return False


def _host_is_paid_cloud(url_or_host: str) -> bool:
    host = url_or_host
    if "://" in url_or_host:
        try:
            host = (urlparse(url_or_host).hostname or "").lower()
        except Exception:  # noqa: BLE001
            host = url_or_host.lower()
    else:
        host = url_or_host.lower()
    if not host or host in LOOPBACK_HOSTS:
        return False
    for suffix in PAID_ENDPOINT_HOST_SUFFIXES:
        s = suffix.lstrip(".")
        if host == s or host.endswith("." + s) or host.endswith(s):
            return True
        # dotted product markers (e.g. bedrock.*.amazonaws.com already covered)
        if s.endswith(".") and s[:-1] in host.split("."):
            return True
    return False


def _find_entitlement(
    capability: CapabilityKind,
    target: str,
    entitlements: list[EntitlementEvidence] | None = None,
) -> tuple[EntitlementEvidence | None, str | None]:
    now = _utc_now()
    ents = entitlements if entitlements is not None else load_entitlements()
    for ent in ents:
        if ent.capability != capability:
            continue
        if ent.target != target and ent.target != "*":
            continue
        exp = _parse_iso(ent.expires_at)
        if exp is None:
            return None, "entitlement_expiry_unparseable"
        if exp <= now:
            return None, "entitlement_expired"
        if ent.billing_dependency or ent.paid_subscription_dependency:
            return None, "entitlement_billing_dependency"
        if ent.trial:
            return None, "entitlement_trial"
        if ent.promotional:
            return None, "entitlement_promotional"
        if ent.allows_paid_overage:
            return None, "entitlement_paid_overage"
        if ent.allows_automatic_upgrade:
            return None, "entitlement_automatic_upgrade"
        if not ent.pricing_known:
            return None, "entitlement_unknown_pricing"
        if ent.zero_token_price_only:
            return None, "zero_token_price_not_zero_cost"
        return ent, None
    return None, "entitlement_missing"


def authorize(
    capability: CapabilityKind,
    target: str,
    *,
    endpoint: str | None = None,
    local: bool = False,
    token_price_usd: float | None = None,
    model_alias: str | None = None,
    nested: bool = False,
    auxiliary_kind: str | None = None,
) -> GateDecision:
    """
    Authorize a capability **before dispatch**.

    ``local=True`` means a true local zero-fee path (loopback / local disk /
    local process) with no external account.
    """
    switch = spending_switch_attempted()
    # Nested / auxiliary still go through the same gate.
    effective_capability: CapabilityKind = "auxiliary" if (nested or auxiliary_kind) else capability

    if switch:
        return GateDecision(
            allowed=False,
            capability=effective_capability,
            target=target,
            reason=(
                "Spending unlock env var present but ignored — "
                "no runtime switch can silently enable spending."
            ),
            denied_code="spending_switch_ignored",
            spending_switch_attempted=True,
        )

    # Explicit zero token price is insufficient.
    if token_price_usd is not None and token_price_usd == 0 and not local:
        return GateDecision(
            allowed=False,
            capability=effective_capability,
            target=target,
            reason=(
                "Zero token price is not zero-cost: external accounts may still "
                "imply billing dependency, overage, or ToS risk."
            ),
            denied_code="zero_token_price_not_zero_cost",
            zero_token_price_rejected=True,
        )

    alias = (model_alias or target).strip().lower()
    if effective_capability in {"inference", "auxiliary"} and alias in PAID_MODEL_ALIASES:
        return GateDecision(
            allowed=False,
            capability=effective_capability,
            target=target,
            reason=f"Model alias '{alias}' maps to hosted billable stacks — blocked before dispatch.",
            denied_code="paid_model_alias",
        )

    if endpoint and _host_is_paid_cloud(endpoint):
        return GateDecision(
            allowed=False,
            capability=effective_capability,
            target=target,
            reason=f"Endpoint host is a known billable/cloud surface ({endpoint!r}) — blocked.",
            denied_code="paid_endpoint",
        )

    if target in DISABLED_PROVIDERS or target in CHARGEABLE_TOOL_IDS:
        return GateDecision(
            allowed=False,
            capability=effective_capability,
            target=target,
            reason=f"Target '{target}' is registered as non-free / chargeable — blocked before dispatch.",
            denied_code="chargeable_or_disabled_target",
        )

    # Local zero-fee paths
    if local:
        if endpoint and not is_loopback_url(endpoint) and effective_capability == "inference":
            return GateDecision(
                allowed=False,
                capability=effective_capability,
                target=target,
                reason="Claimed local inference but endpoint is not loopback.",
                denied_code="local_claim_non_loopback",
            )
        if target in ELIGIBLE_PROVIDERS or target.startswith("local.") or target in {
            "local_command",
            "local_sqlite",
            "local_fs",
            "workspace_inspect",
            "deterministic_task",
            "ollama_local",
            "llamacpp_local",
        }:
            return GateDecision(
                allowed=True,
                capability=effective_capability,
                target=target,
                reason="Eligible local zero-fee operation (no external account).",
                local_zero_fee=True,
            )
        # Unknown local tool — fail closed unless clearly local.* 
        if target.startswith("local."):
            return GateDecision(
                allowed=True,
                capability=effective_capability,
                target=target,
                reason="Eligible local.* zero-fee operation.",
                local_zero_fee=True,
            )
        return GateDecision(
            allowed=False,
            capability=effective_capability,
            target=target,
            reason=f"Unknown local target '{target}' — refuse by default.",
            denied_code="unknown_local_target",
        )

    # External: require verified free entitlement
    ent, deny = _find_entitlement(capability if not nested else capability, target)
    # For auxiliary nested calls, still require entitlement on underlying capability target
    if ent is None:
        # also try effective capability key
        if deny is None:
            deny = "entitlement_missing"
        return GateDecision(
            allowed=False,
            capability=effective_capability,
            target=target,
            reason=f"External operation denied ({deny}). No verified current free entitlement.",
            denied_code=deny,
        )

    return GateDecision(
        allowed=True,
        capability=effective_capability,
        target=target,
        reason="External operation allowed under verified free entitlement (no billing dependency).",
        entitlement_id=ent.id,
        local_zero_fee=False,
    )


def require_authorized(capability: CapabilityKind, target: str, **kwargs: Any) -> GateDecision:
    decision = authorize(capability, target, **kwargs)
    if not decision.allowed:
        raise PermissionError(decision.reason)
    return decision


def scrub_env_for_child(env: dict[str, str] | None = None) -> dict[str, str]:
    """Return env without credential-shaped keys for untrusted child processes."""
    source = env if env is not None else dict(os.environ)
    clean: dict[str, str] = {}
    for key, value in source.items():
        if key in SPENDING_SWITCH_NAMES:
            continue
        if any(p.search(key) for p in CREDENTIAL_ENV_PATTERNS):
            continue
        clean[key] = value
    return clean


def gate_self_test() -> dict[str, Any]:
    """Executable acceptance probes — must all deny before any dispatch."""
    cases: list[dict[str, Any]] = []

    def check(name: str, decision: GateDecision, expect_allowed: bool, code: str | None = None) -> None:
        ok = decision.allowed is expect_allowed and (
            code is None or decision.denied_code == code or (expect_allowed and decision.allowed)
        )
        cases.append(
            {
                "id": name,
                "ok": ok,
                "expect_allowed": expect_allowed,
                "decision": decision.to_dict(),
            }
        )

    check(
        "fake_paid_endpoint",
        authorize("inference", "openai_api", endpoint="https://api.openai.com/v1/chat", local=False),
        False,
        "paid_endpoint",
    )
    check(
        "newly_chargeable_tool",
        authorize("tool", "web_search_paid", local=False),
        False,
        "chargeable_or_disabled_target",
    )
    # Expired evidence
    ensure_state()
    expired = EntitlementEvidence(
        id="expired-demo",
        capability="search",
        target="example_search",
        verified_at="2020-01-01T00:00:00+00:00",
        expires_at="2020-01-02T00:00:00+00:00",
        usage_terms="n/a",
        billing_dependency=False,
        paid_subscription_dependency=False,
        trial=False,
        promotional=False,
        allows_paid_overage=False,
        allows_automatic_upgrade=False,
        pricing_known=True,
    )
    missing, code = _find_entitlement("search", "example_search", [expired])
    check(
        "expired_evidence",
        GateDecision(
            allowed=False,
            capability="search",
            target="example_search",
            reason="expired",
            denied_code=code,
        )
        if missing is None
        else GateDecision(True, "search", "example_search", "unexpected"),
        False,
        "entitlement_expired",
    )
    check(
        "paid_model_alias",
        authorize("inference", "cloud", model_alias="gpt-4o", local=False),
        False,
        "paid_model_alias",
    )
    check(
        "zero_token_price_external",
        authorize("inference", "hosted_zero", local=False, token_price_usd=0.0),
        False,
        "zero_token_price_not_zero_cost",
    )
    check(
        "local_ollama_eligible",
        authorize("inference", "ollama_local", endpoint="http://127.0.0.1:11434", local=True),
        True,
    )
    check(
        "local_command_eligible",
        authorize("tool", "local_command", local=True),
        True,
    )
    check(
        "auxiliary_nested_paid_alias",
        authorize("inference", "helper", model_alias="claude-3-5-sonnet", local=False, nested=True, auxiliary_kind="summary"),
        False,
        "paid_model_alias",
    )

    # Spending switch cannot enable
    os.environ["ENABLE_SPENDING"] = "1"
    try:
        d = authorize("inference", "ollama_local", endpoint="http://127.0.0.1:11434", local=True)
        check("spending_switch_cannot_enable", d, False, "spending_switch_ignored")
    finally:
        os.environ.pop("ENABLE_SPENDING", None)

    # Scrub credentials
    scrubbed = scrub_env_for_child(
        {"PATH": "/usr/bin", "OPENAI_API_KEY": "sk-secret", "FOO": "bar", "ALLOW_PAID": "1"}
    )
    scrub_ok = "OPENAI_API_KEY" not in scrubbed and "ALLOW_PAID" not in scrubbed and scrubbed.get("FOO") == "bar"
    cases.append({"id": "credential_scrub_child_env", "ok": scrub_ok, "detail": list(scrubbed.keys())})

    passed = sum(1 for c in cases if c["ok"])
    return {
        "suite": "cost-gate-self-test",
        "passed": passed,
        "failed": len(cases) - passed,
        "ok": passed == len(cases),
        "cases": cases,
        "enforcement_boundary": str((ROOT / "docs" / "COST_GATE.md").as_posix()),
    }
