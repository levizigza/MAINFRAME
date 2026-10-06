"""Minimal stdlib HTTP helpers for local inference adapters."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse


def tcp_reachable(url: str, timeout_s: float = 0.25) -> bool:
    """Fast loopback liveness check before HTTP (avoids long Windows connect hangs)."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def http_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    timeout_s: float = 30.0,
) -> dict[str, Any]:
    if not tcp_reachable(url, timeout_s=min(0.35, timeout_s)):
        return {
            "ok": False,
            "status": None,
            "error": f"TCP unreachable for {urlparse(url).hostname}:{urlparse(url).port}",
        }
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            parsed = json.loads(body) if body.strip() else {}
            return {
                "ok": True,
                "status": getattr(resp, "status", 200),
                "data": parsed,
            }
    except urllib.error.HTTPError as exc:
        err_body = ""
        try:
            err_body = exc.read().decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
        return {
            "ok": False,
            "status": exc.code,
            "error": f"HTTP {exc.code}",
            "body": err_body[:2000],
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "status": None,
            "error": f"{type(exc).__name__}: {exc}",
        }
