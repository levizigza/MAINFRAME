"""Network access boundary — policy deny; OS network jail is often unavailable."""

from __future__ import annotations

import socket
from typing import Any

from mainframe.eligibility import is_loopback_url


def authorize_network(
    *,
    trust: str,
    url_or_host: str | None = None,
    allow_loopback: bool = True,
) -> dict[str, Any]:
    """
    Unauthorized network for untrusted / non-loopback is denied by policy.

    This is not an OS firewall sandbox unless isolation.report says so.
    """
    if trust != "trusted_local":
        return {
            "allowed": False,
            "reason": "untrusted_network_denied",
            "boundary": "network_access",
            "enforced": True,
            "enforcement_layer": "policy",
            "os_network_isolation": False,
        }
    if url_or_host:
        candidate = url_or_host
        if "://" not in candidate:
            candidate = f"http://{candidate}"
        if allow_loopback and is_loopback_url(candidate):
            return {
                "allowed": True,
                "reason": "trusted_loopback",
                "boundary": "network_access",
                "enforced": True,
                "enforcement_layer": "policy",
            }
        # Trusted local may still be denied for arbitrary internet unless explicitly needed —
        # default deny non-loopback for executable tools unless marked trusted+explicit
        return {
            "allowed": False,
            "reason": "non_loopback_denied_for_executable_tools",
            "host": url_or_host,
            "boundary": "network_access",
            "enforced": True,
            "enforcement_layer": "policy",
        }
    return {
        "allowed": False,
        "reason": "network_requires_explicit_target",
        "boundary": "network_access",
        "enforced": True,
        "enforcement_layer": "policy",
    }


def attempt_connect(host: str, port: int, timeout_s: float = 0.4) -> dict[str, Any]:
    """Probe used by acceptance — does not bypass authorize_network."""
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return {"connected": True, "host": host, "port": port}
    except OSError as exc:
        return {"connected": False, "host": host, "port": port, "error": str(exc)}
