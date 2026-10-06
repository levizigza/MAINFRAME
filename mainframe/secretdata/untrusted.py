"""Untrusted data envelopes — provenance preserved; never trust as authorization."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Literal

UntrustedKind = Literal[
    "repository_text",
    "web_page",
    "api_response",
    "mcp_description",
    "imported_workflow",
]

UNTRUSTED_KINDS: tuple[str, ...] = (
    "repository_text",
    "web_page",
    "api_response",
    "mcp_description",
    "imported_workflow",
)

# Actions that untrusted content must never authorize
FORBIDDEN_FROM_UNTRUSTED = frozenset(
    {
        "authorize_new_tool",
        "authorize_destination",
        "authorize_purchase",
        "authorize_disclosure",
        "change_policy",
        "reveal_secret",
        "install_package",
        "enable_paid",
        "expand_credential_scope",
    }
)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def wrap_untrusted(
    text: str,
    *,
    kind: str,
    source: str,
    content_type: str | None = None,
    url: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if kind not in UNTRUSTED_KINDS:
        kind = "repository_text"
    digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
    return {
        "untrusted": True,
        "kind": kind,
        "source": source,
        "url": url,
        "content_type": content_type,
        "text": text,
        "content_sha256": digest,
        "captured_at": _utc(),
        "provenance": {
            "kind": kind,
            "source": source,
            "url": url,
            "content_sha256": digest,
            "may_authorize_tools": False,
            "may_authorize_destinations": False,
            "may_authorize_purchases": False,
            "may_authorize_disclosure": False,
            "may_change_policy": False,
            "usable_as_data": True,
        },
        "extra": extra or {},
    }


def preserve_provenance(envelope: dict[str, Any], *, summary: str | None = None) -> dict[str, Any]:
    """Carry provenance through retrieval/summaries — summary stays untrusted."""
    prov = dict(envelope.get("provenance") or {})
    out = {
        "untrusted": True,
        "kind": envelope.get("kind"),
        "source": envelope.get("source"),
        "url": envelope.get("url"),
        "content_sha256": envelope.get("content_sha256"),
        "provenance": {
            **prov,
            "summarized": summary is not None,
            "summary_untrusted": True if summary is not None else prov.get("summary_untrusted"),
            "parent_sha256": envelope.get("content_sha256"),
        },
        "text": summary if summary is not None else envelope.get("text"),
        "original_kind": envelope.get("kind"),
    }
    if summary is not None:
        out["content_sha256"] = hashlib.sha256(summary.encode()).hexdigest()
        out["provenance"]["content_sha256"] = out["content_sha256"]
    return out
