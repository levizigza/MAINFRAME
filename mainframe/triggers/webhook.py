"""Local loopback webhook — auth, signatures, replay/size rejection; no paid tunnel."""

from __future__ import annotations

import hashlib
import hmac
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import urlparse

from mainframe.triggers.events import normalize_event
from mainframe.triggers.store import TriggerStore

MAX_BODY_BYTES = 64 * 1024  # reject oversized
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


PUBLIC_TUNNEL_TRADEOFF = (
    "Inbound internet access is not assumed. This webhook binds loopback only "
    "(127.0.0.1). It is NOT publicly reachable — do not pretend otherwise. "
    "No paid tunnel (ngrok/cloudflare tunnel/etc.) is required or offered. "
    "When remote ingress is unavailable, use bounded polling of an eligible "
    "local/loopback source, or a manual trigger."
)


def is_loopback_host(host: str) -> bool:
    h = (host or "").split("%")[0].lower()
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]
    return h in LOOPBACK_HOSTS or h == "0:0:0:0:0:0:0:1"


def validate_webhook_request(
    store: TriggerStore,
    *,
    body: bytes,
    headers: dict[str, str],
    shared_secret: str,
    binding_id: str,
    permission_scope: str,
    max_bytes: int = MAX_BODY_BYTES,
) -> dict[str, Any]:
    """
    Authenticate webhook, validate HMAC signature when provided, reject replay/oversized.
    Does not accept command/argv in body.
    """
    if len(body) > max_bytes:
        return {"ok": False, "error": "payload_too_large", "bytes": len(body), "max": max_bytes}

    # Signature: X-Mainframe-Signature: sha256=<hex> over body with shared_secret
    sig = headers.get("X-Mainframe-Signature") or headers.get("x-mainframe-signature") or ""
    expected = "sha256=" + hmac.new(
        shared_secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    if not sig:
        return {"ok": False, "error": "missing_signature"}
    if not hmac.compare_digest(sig, expected):
        return {"ok": False, "error": "invalid_signature"}

    nonce = headers.get("X-Mainframe-Nonce") or headers.get("x-mainframe-nonce") or ""
    if not nonce:
        return {"ok": False, "error": "missing_nonce"}
    if store.nonce_seen(nonce):
        return {"ok": False, "error": "replay_rejected", "nonce": nonce}

    try:
        data = json.loads(body.decode("utf-8") if body else "{}")
    except json.JSONDecodeError:
        return {"ok": False, "error": "invalid_json"}
    if not isinstance(data, dict):
        return {"ok": False, "error": "body_must_be_object"}
    if any(k in data for k in ("command", "argv", "command_argv")):
        return {"ok": False, "error": "event_cannot_select_command"}

    # Token auth (in addition to signature)
    token = headers.get("Authorization") or headers.get("authorization") or ""
    if token != f"Bearer {shared_secret}":
        return {"ok": False, "error": "unauthorized"}

    identity = str(data.get("id") or data.get("identity") or nonce)
    fp = hashlib.sha256(body).hexdigest()[:24]
    event = normalize_event(
        source="local_webhook",
        identity=identity,
        permission_scope=permission_scope,
        content_fingerprint=fp,
        binding_id=binding_id,
        payload={k: v for k, v in data.items() if k not in ("command", "argv")},
    )
    return {
        "ok": True,
        "event": event,
        "publicly_reachable": False,
        "bind": "127.0.0.1",
        "tradeoff": PUBLIC_TUNNEL_TRADEOFF,
    }


def webhook_endpoint_info(*, port: int = 18791) -> dict[str, Any]:
    return {
        "url": f"http://127.0.0.1:{port}/hooks/trigger",
        "bind": "127.0.0.1",
        "publicly_reachable": False,
        "paid_tunnel_required": False,
        "scheduler_interface": "openclaw_gateway_http_hooks_or_freeforge_loopback",
        "tradeoff": PUBLIC_TUNNEL_TRADEOFF,
    }


class _Handler(BaseHTTPRequestHandler):
    store: TriggerStore
    secret: str
    binding_id: str
    permission_scope: str
    last_result: dict[str, Any] = {}

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        return  # quiet

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/hooks/trigger":
            self.send_response(404)
            self.end_headers()
            return
        host = (self.headers.get("Host") or "127.0.0.1").split(":")[0]
        if not is_loopback_host(host):
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b'{"error":"non_loopback_host_rejected"}')
            return
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        headers = {k: v for k, v in self.headers.items()}
        result = validate_webhook_request(
            self.store,
            body=body,
            headers=headers,
            shared_secret=self.secret,
            binding_id=self.binding_id,
            permission_scope=self.permission_scope,
        )
        _Handler.last_result = result
        code = 200 if result.get("ok") else 401 if result.get("error") in {
            "missing_signature",
            "invalid_signature",
            "unauthorized",
            "missing_nonce",
            "replay_rejected",
        } else 400
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(result).encode("utf-8"))


def serve_local_webhook_once(
    store: TriggerStore,
    *,
    secret: str,
    binding_id: str,
    permission_scope: str,
    port: int = 18791,
    timeout_s: float = 0.1,
) -> HTTPServer:
    """Create a loopback-only server (caller handles requests). Not publicly reachable."""
    class H(_Handler):
        pass

    H.store = store
    H.secret = secret
    H.binding_id = binding_id
    H.permission_scope = permission_scope
    server = HTTPServer(("127.0.0.1", port), H)
    server.timeout = timeout_s
    return server
