"""Enforceable vs policy-only boundaries for outbound network."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from mainframe.boundaries.isolation import probe_isolation
from mainframe.eligibility import is_loopback_url


@lru_cache(maxsize=1)
def _isolation_snapshot() -> dict[str, Any]:
    # Lightweight: do not spawn Job Object children on every call
    return probe_isolation(verify_enforcement=False)


def clear_isolation_cache() -> None:
    _isolation_snapshot.cache_clear()


def network_enforcement_status() -> dict[str, Any]:
    iso = _isolation_snapshot()
    os_net = bool(iso.get("os_network_isolation"))
    return {
        "os_network_isolation": os_net,
        "application_policy_alone_constrains_arbitrary_processes": False,
        "note": (
            "Application-level policy cannot constrain arbitrary processes that already "
            "have network access. Non-loopback live outbound is disabled unless OS "
            "network isolation is verified on this host."
            if not os_net
            else "OS network isolation reported available; still prefer allowlists."
        ),
        "job_object_process_limits": bool(iso.get("reliable_process_isolation")),
        "isolation_mechanism": iso.get("mechanism"),
    }


def allow_non_loopback_live(*, purpose: str) -> dict[str, Any]:
    """
    Gate for live HTTP outside loopback (connectors, plugins, workers).

    When OS network isolation is unavailable, refuse — callers must use fixtures
    or loopback-only endpoints.
    """
    status = network_enforcement_status()
    if status["os_network_isolation"]:
        return {
            "allowed": True,
            "purpose": purpose,
            "enforcement": "os_network_isolation",
            **status,
        }
    return {
        "allowed": False,
        "purpose": purpose,
        "error": "non_loopback_live_disabled_without_os_network_isolation",
        "fallback": "fixture_or_loopback_only",
        "paid_fallback_used": False,
        "hosted_fallback_used": False,
        **status,
    }


def gate_url(url: str, *, purpose: str) -> dict[str, Any]:
    if is_loopback_url(url):
        return {
            "allowed": True,
            "reason": "loopback",
            "url": url,
            "purpose": purpose,
            "enforcement": "loopback_policy",
        }
    live = allow_non_loopback_live(purpose=purpose)
    if not live.get("allowed"):
        return {**live, "url": url, "allowed": False}
    return {**live, "url": url, "allowed": True}
