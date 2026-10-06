"""Reject cloud / hosted Ollama routes — local-only only."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from mainframe.eligibility import is_loopback_url

# Hosts that route to Ollama Cloud / hosted inference (OpenClaw docs: ollama.com).
CLOUD_HOSTS = frozenset(
    {
        "ollama.com",
        "www.ollama.com",
        "api.ollama.com",
    }
)


def is_cloud_model_name(name: str) -> bool:
    n = (name or "").strip().lower()
    if not n:
        return False
    # OpenClaw / Ollama cloud models use the :cloud suffix.
    if n.endswith(":cloud") or ":cloud:" in n or n.endswith("/cloud"):
        return True
    if n.startswith("ollama-cloud/") or "/cloud/" in n:
        return True
    return False


def is_cloud_endpoint(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:  # noqa: BLE001
        return True
    if not host:
        return True
    if host in CLOUD_HOSTS:
        return True
    # Non-loopback is already rejected by eligibility; treat as non-local.
    return not is_loopback_url(url)


def assert_local_only(base_url: str, model: str | None = None) -> dict[str, Any]:
    """Return ok=False with reason when cloud would be selected."""
    if is_cloud_endpoint(base_url):
        return {
            "ok": False,
            "refused": True,
            "reason": (
                f"Endpoint {base_url!r} is not local-only "
                "(hosted/cloud Ollama rejected; use loopback + local weights)."
            ),
            "local_only": False,
        }
    if model is not None and is_cloud_model_name(model):
        return {
            "ok": False,
            "refused": True,
            "reason": (
                f"Model {model!r} looks like an Ollama Cloud id (:cloud). "
                "MAINFRAME local-only adapter will not select it."
            ),
            "local_only": False,
            "model": model,
        }
    return {
        "ok": True,
        "refused": False,
        "reason": "Local-only: loopback endpoint and non-cloud model id.",
        "local_only": True,
        "endpoint": base_url,
        "model": model,
    }


def filter_local_models(names: list[str]) -> dict[str, Any]:
    local: list[str] = []
    cloud: list[str] = []
    for n in names:
        if is_cloud_model_name(n):
            cloud.append(n)
        else:
            local.append(n)
    return {
        "local_models": local,
        "cloud_models_excluded": cloud,
        "selected_would_be": local[0] if local else None,
    }
