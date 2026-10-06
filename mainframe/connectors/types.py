"""Connector types — verified specs, read/write separation, typed I/O."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

CapabilityKind = Literal["read", "write"]
AuthKind = Literal["none", "api_key_header", "api_key_query", "bearer"]


@dataclass
class AuthSpec:
    kind: AuthKind = "none"
    header_name: str | None = None
    query_param: str | None = None
    # Credentials come only from scoped secret facility — never from model-chosen URLs.
    credential_scope: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RateLimitSpec:
    max_requests_per_minute: int = 30
    retry_after_default_s: float = 1.0
    respect_retry_after_header: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PaginationSpec:
    style: Literal["none", "page", "offset", "cursor"] = "none"
    page_param: str = "page"
    offset_param: str = "offset"
    limit_param: str = "limit"
    cursor_param: str = "cursor"
    next_field: str = "next"
    items_field: str = "items"
    max_pages: int = 5
    default_limit: int = 10

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OperationSpec:
    op_id: str
    capability: CapabilityKind
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: str  # relative to base_url; may contain {param}
    purpose: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    pagination: PaginationSpec = field(default_factory=PaginationSpec)
    cacheable: bool = True
    freshness_s: int = 3600
    attribution: str | None = None
    # Exposed through tool registry only when True
    expose_as_tool: bool = True

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


@dataclass
class ConnectorSpec:
    connector_id: str
    title: str
    base_url: str
    allowed_hosts: list[str]
    docs_url: str
    openapi_or_docs: str  # OpenAPI URL or documented-endpoints note
    source_kind: Literal["openapi", "documented_endpoints"]
    auth: AuthSpec = field(default_factory=AuthSpec)
    rate_limit: RateLimitSpec = field(default_factory=RateLimitSpec)
    operations: list[OperationSpec] = field(default_factory=list)
    default_attribution: str | None = None
    shortlist_id: str | None = None
    read_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "connector_id": self.connector_id,
            "title": self.title,
            "base_url": self.base_url,
            "allowed_hosts": list(self.allowed_hosts),
            "docs_url": self.docs_url,
            "openapi_or_docs": self.openapi_or_docs,
            "source_kind": self.source_kind,
            "auth": self.auth.to_dict(),
            "rate_limit": self.rate_limit.to_dict(),
            "operations": [o.to_dict() for o in self.operations],
            "default_attribution": self.default_attribution,
            "shortlist_id": self.shortlist_id,
            "read_only": self.read_only,
        }

    def operation(self, op_id: str) -> OperationSpec | None:
        for op in self.operations:
            if op.op_id == op_id:
                return op
        return None
