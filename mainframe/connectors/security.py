"""Hostname allowlists, redirects, and credential-to-URL refusals."""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin, urlparse

from mainframe.secretdata.http_guard import validate_redirect, validate_url


def assert_host_allowed(url: str, allowed_hosts: list[str]) -> dict[str, Any]:
    first = validate_url(url)
    if not first.get("allowed"):
        return {"ok": False, "error": "ssrf_or_invalid_url", "detail": first}
    host = (urlparse(url).hostname or "").lower()
    allowed = {h.lower() for h in allowed_hosts}
    if host not in allowed:
        return {
            "ok": False,
            "error": "host_not_allowed",
            "host": host,
            "allowed_hosts": sorted(allowed),
        }
    return {"ok": True, "host": host, "url": url}


def validate_redirect_chain(
    start_url: str,
    locations: list[str],
    allowed_hosts: list[str],
) -> dict[str, Any]:
    prev = start_url
    checked: list[str] = [start_url]
    for loc in locations:
        nxt = validate_redirect(prev, loc)
        if not nxt.get("allowed"):
            return {"ok": False, "error": "redirect_blocked", "detail": nxt, "chain": checked}
        url = str(nxt.get("url") or loc)
        host_ok = assert_host_allowed(url, allowed_hosts)
        if not host_ok.get("ok"):
            return {
                "ok": False,
                "error": "redirect_host_not_allowed",
                "detail": host_ok,
                "chain": checked + [url],
            }
        checked.append(url)
        prev = url
    return {"ok": True, "final_url": prev, "chain": checked}


def refuse_model_chosen_url(args: dict[str, Any]) -> dict[str, Any] | None:
    """
    Never allow callers (including model output) to supply a free-form URL that
    receives credentials or overrides the connector base host.
    """
    for key in ("url", "base_url", "endpoint", "href", "request_url", "absolute_url"):
        if key in args and args[key] is not None:
            return {
                "ok": False,
                "error": "model_chosen_url_refused",
                "message": (
                    f"Argument '{key}' is not allowed. Connectors build URLs only from "
                    "verified base_url + typed path params — never from model-chosen URLs."
                ),
                "key": key,
            }
    return None


def refuse_credentials_to_foreign_url(
    *,
    target_url: str,
    allowed_hosts: list[str],
    has_credentials: bool,
) -> dict[str, Any] | None:
    if not has_credentials:
        return None
    host_ok = assert_host_allowed(target_url, allowed_hosts)
    if not host_ok.get("ok"):
        return {
            "ok": False,
            "error": "credential_url_refused",
            "message": "Refusing to send credentials to a host outside the connector allowlist.",
            "detail": host_ok,
        }
    return None


def build_url(base_url: str, path: str, path_params: dict[str, Any]) -> str:
    filled = path
    for k, v in path_params.items():
        filled = filled.replace("{" + k + "}", str(v))
    return urljoin(base_url.rstrip("/") + "/", filled.lstrip("/"))
