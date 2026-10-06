"""Block external network for offline demos; allow loopback only."""

from __future__ import annotations

import socket
from contextlib import contextmanager
from typing import Any, Iterator

_LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})


class ExternalNetworkBlocked(RuntimeError):
    """Raised when code attempts non-loopback network during offline demos."""


@contextmanager
def offline_network() -> Iterator[dict[str, Any]]:
    """Disable external network access for the duration of the context."""
    real_connect = socket.socket.connect
    blocked: list[str] = []

    def guarded_connect(self: socket.socket, address: Any) -> None:  # noqa: ANN401
        host: str
        if isinstance(address, tuple) and address:
            host = str(address[0])
        else:
            host = str(address)
        # Normalize IPv6 mapped forms
        h = host.lower().strip("[]")
        if h not in _LOOPBACK and not h.startswith("127."):
            blocked.append(h)
            raise ExternalNetworkBlocked(
                f"External network disabled for offline demo; refused connect to {host!r}"
            )
        return real_connect(self, address)

    socket.socket.connect = guarded_connect  # type: ignore[method-assign]
    meta = {"mode": "offline_external_blocked", "blocked_hosts": blocked}
    try:
        yield meta
    finally:
        socket.socket.connect = real_connect  # type: ignore[method-assign]
        meta["blocked_hosts"] = list(blocked)
