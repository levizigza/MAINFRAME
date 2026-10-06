"""Live HTTP transport with allowlisted hosts, redirects, bounded retries."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from mainframe.connectors.security import assert_host_allowed, validate_redirect_chain
from mainframe.connectors.types import RateLimitSpec
from mainframe.secretdata.http_guard import MAX_REDIRECTS, validate_payload


class LiveTransport:
    def __init__(
        self,
        *,
        allowed_hosts: list[str],
        rate_limit: RateLimitSpec,
        timeout_s: float = 20.0,
        max_retries: int = 2,
    ) -> None:
        self.allowed_hosts = allowed_hosts
        self.rate_limit = rate_limit
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self._window: list[float] = []

    def _rate_gate(self) -> dict[str, Any] | None:
        now = time.monotonic()
        self._window = [t for t in self._window if now - t < 60.0]
        if len(self._window) >= self.rate_limit.max_requests_per_minute:
            return {
                "ok": False,
                "status": 429,
                "error": "rate_limited",
                "retryable": True,
                "retry_after_s": self.rate_limit.retry_after_default_s,
            }
        self._window.append(now)
        return None

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        host_ok = assert_host_allowed(url, self.allowed_hosts)
        if not host_ok.get("ok"):
            return {"ok": False, "error": "host_not_allowed", "detail": host_ok, "status": 0}

        gate = self._rate_gate()
        if gate:
            return gate

        full = url
        if query:
            qs = urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
            full = f"{url}?{qs}" if qs else url

        attempt = 0
        last: dict[str, Any] = {}
        while attempt <= self.max_retries:
            attempt += 1
            try:
                req = urllib.request.Request(
                    full,
                    headers={
                        "User-Agent": "MAINFRAME-connector/0.1",
                        "Accept": "application/json",
                        **(headers or {}),
                    },
                    method=method.upper(),
                )
                # Manual redirect handling so we can validate each hop
                opener = urllib.request.build_opener(urllib.request.HTTPHandler())
                # Disable auto redirect by using a custom redirect handler count 0
                class _NoRedirect(urllib.request.HTTPRedirectHandler):
                    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: N802
                        return None

                opener = urllib.request.build_opener(_NoRedirect)
                with opener.open(req, timeout=self.timeout_s) as resp:
                    raw = resp.read()
                    status = getattr(resp, "status", None) or resp.getcode()
                    hdrs = {k.lower(): v for k, v in resp.headers.items()}
                    payload = validate_payload(
                        size_bytes=len(raw), content_type=hdrs.get("content-type")
                    )
                    if not payload.get("allowed"):
                        return {
                            "ok": False,
                            "status": status,
                            "error": "payload_rejected",
                            "detail": payload,
                        }
                    text = raw.decode("utf-8", errors="replace")
                    body_json = None
                    try:
                        body_json = json.loads(text)
                    except json.JSONDecodeError:
                        body_json = None
                    return {
                        "ok": True,
                        "status": int(status),
                        "headers": hdrs,
                        "body_text": text,
                        "body_json": body_json,
                        "url": full,
                        "redirect_chain": [],
                    }
            except urllib.error.HTTPError as exc:
                # Redirect responses
                if exc.code in {301, 302, 303, 307, 308}:
                    loc = exc.headers.get("Location") or ""
                    chain_ok = validate_redirect_chain(full, [loc], self.allowed_hosts)
                    if not chain_ok.get("ok"):
                        return {
                            "ok": False,
                            "status": exc.code,
                            "error": "redirect_blocked",
                            "detail": chain_ok,
                        }
                    full = str(chain_ok.get("final_url") or loc)
                    if len(getattr(self, "_redir", [])) > MAX_REDIRECTS:
                        return {"ok": False, "status": exc.code, "error": "too_many_redirects"}
                    continue
                body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
                retry_after = None
                if self.rate_limit.respect_retry_after_header:
                    ra = exc.headers.get("Retry-After") if exc.headers else None
                    try:
                        retry_after = float(ra) if ra is not None else None
                    except ValueError:
                        retry_after = None
                last = {
                    "ok": False,
                    "status": int(exc.code),
                    "error": "http_error",
                    "body_text": body,
                    "retry_after_s": retry_after,
                    "retryable": exc.code in {408, 429, 500, 502, 503, 504},
                    "url": full,
                }
                if last["retryable"] and attempt <= self.max_retries:
                    time.sleep(min(retry_after or self.rate_limit.retry_after_default_s, 5.0))
                    continue
                return last
            except urllib.error.URLError as exc:
                last = {
                    "ok": False,
                    "status": 0,
                    "error": "network_error",
                    "message": str(exc.reason),
                    "retryable": True,
                }
                if attempt <= self.max_retries:
                    time.sleep(self.rate_limit.retry_after_default_s)
                    continue
                return last
            except TimeoutError:
                last = {"ok": False, "status": 0, "error": "timeout", "retryable": True}
                if attempt <= self.max_retries:
                    continue
                return last
        return last or {"ok": False, "error": "exhausted_retries"}
