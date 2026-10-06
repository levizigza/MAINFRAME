"""Structured connector errors."""

from __future__ import annotations

from typing import Any


def structured_error(
    code: str,
    message: str,
    *,
    detail: dict[str, Any] | None = None,
    retryable: bool = False,
    http_status: int | None = None,
) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "retryable": retryable,
            "http_status": http_status,
            "detail": detail or {},
        },
    }


# Stable codes used by fixtures + runtime
SCHEMA_DRIFT = "schema_drift"
QUOTA_EXHAUSTED = "quota_exhausted"
PARTIAL_PAGINATION = "partial_pagination"
MALFORMED_RESPONSE = "malformed_response"
HOST_NOT_ALLOWED = "host_not_allowed"
CREDENTIAL_URL_REFUSED = "credential_url_refused"
REDIRECT_BLOCKED = "redirect_blocked"
AUTH_REQUIRED = "auth_required"
RATE_LIMITED = "rate_limited"
TIMEOUT = "timeout"
NETWORK = "network_error"
UNKNOWN_OPERATION = "unknown_operation"
WRITE_ON_READ_CONNECTOR = "write_on_read_connector"
MODEL_CHOSEN_URL_REFUSED = "model_chosen_url_refused"
