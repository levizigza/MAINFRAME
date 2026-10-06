"""HTTP URL / redirect / size / content-type validation — SSRF and LAN protections."""

from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import urljoin, urlparse

# Default caps for generic HTTP tools
MAX_PAYLOAD_BYTES = 2 * 1024 * 1024  # 2 MiB
MAX_REDIRECTS = 3
ALLOWED_CONTENT_PREFIXES = (
    "text/",
    "application/json",
    "application/xml",
    "application/javascript",
    "application/xhtml",
)


def _host_is_blocked(host: str) -> dict[str, Any]:
    h = host.strip().lower().rstrip(".")
    if not h:
        return {"blocked": True, "reason": "empty_host"}
    if h in {"localhost", "metadata.google.internal"}:
        return {"blocked": True, "reason": "localhost_or_metadata", "host": h}
    # Literal IP?
    try:
        ip = ipaddress.ip_address(h)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or str(ip) == "169.254.169.254"
        ):
            return {"blocked": True, "reason": "private_or_link_local_or_metadata", "ip": str(ip)}
        return {"blocked": False, "ip": str(ip)}
    except ValueError:
        pass
    # Resolve DNS and check all addresses
    try:
        infos = socket.getaddrinfo(h, None)
    except socket.gaierror as exc:
        return {"blocked": True, "reason": f"dns_failed:{exc}", "host": h}
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or str(ip).startswith("169.254.")
        ):
            return {
                "blocked": True,
                "reason": "resolves_to_local_or_private",
                "host": h,
                "ip": str(ip),
            }
    return {"blocked": False, "host": h}


def validate_url(url: str, *, allow_http: bool = True) -> dict[str, Any]:
    try:
        parsed = urlparse(url)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "allowed": False, "error": f"parse:{exc}"}
    scheme = (parsed.scheme or "").lower()
    if scheme in {"file", "ftp", "gopher", "dict", "sftp", "jar"}:
        return {"ok": False, "allowed": False, "error": "scheme_forbidden", "scheme": scheme}
    if scheme not in {"http", "https"}:
        return {"ok": False, "allowed": False, "error": "scheme_not_http", "scheme": scheme}
    if scheme == "http" and not allow_http:
        return {"ok": False, "allowed": False, "error": "http_not_allowed"}
    if not parsed.hostname:
        return {"ok": False, "allowed": False, "error": "missing_host"}
    block = _host_is_blocked(parsed.hostname)
    if block.get("blocked"):
        return {
            "ok": False,
            "allowed": False,
            "error": "ssrf_or_local_network_blocked",
            "detail": block,
            "url": url,
        }
    return {"ok": True, "allowed": True, "url": url, "host": parsed.hostname, "scheme": scheme}


def validate_redirect(previous_url: str, location: str) -> dict[str, Any]:
    next_url = urljoin(previous_url, location)
    return validate_url(next_url)


def validate_payload(
    *,
    size_bytes: int,
    content_type: str | None,
    max_bytes: int = MAX_PAYLOAD_BYTES,
) -> dict[str, Any]:
    if size_bytes < 0 or size_bytes > max_bytes:
        return {
            "ok": False,
            "allowed": False,
            "error": "payload_size_exceeded",
            "size_bytes": size_bytes,
            "max_bytes": max_bytes,
        }
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct and not any(ct.startswith(p) or ct == p.rstrip("/") for p in ALLOWED_CONTENT_PREFIXES):
        # allow empty unknown from accept fixtures; deny binary/octet-stream installers
        if ct in {"application/octet-stream", "application/zip", "application/x-msdownload"}:
            return {
                "ok": False,
                "allowed": False,
                "error": "content_type_denied",
                "content_type": ct,
            }
    return {
        "ok": True,
        "allowed": True,
        "size_bytes": size_bytes,
        "content_type": ct or None,
        "max_bytes": max_bytes,
    }


def guard_generic_http(
    url: str,
    *,
    redirect_chain: list[str] | None = None,
    size_bytes: int = 0,
    content_type: str | None = None,
) -> dict[str, Any]:
    """Full guard for generic HTTP tools — SSRF, redirects, size, content-type."""
    first = validate_url(url)
    if not first.get("allowed"):
        return {"ok": False, "stage": "url", **first}
    chain = list(redirect_chain or [])
    if len(chain) > MAX_REDIRECTS:
        return {"ok": False, "stage": "redirect", "error": "too_many_redirects", "n": len(chain)}
    checked = [first]
    prev = url
    for loc in chain:
        nxt = validate_redirect(prev, loc)
        checked.append(nxt)
        if not nxt.get("allowed"):
            return {"ok": False, "stage": "redirect", **nxt}
        prev = nxt.get("url") or loc
    body = validate_payload(size_bytes=size_bytes, content_type=content_type)
    if not body.get("allowed"):
        return {"ok": False, "stage": "payload", **body}
    return {
        "ok": True,
        "allowed": True,
        "url": url,
        "redirects_validated": len(chain),
        "payload": body,
        "ssrf_protection": True,
        "local_network_blocked": True,
    }
