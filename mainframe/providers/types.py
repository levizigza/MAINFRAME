"""Canonical provider message types — adapters translate to native shapes only."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Message:
    role: Role
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = [t.to_dict() for t in self.tool_calls]
        if self.tool_call_id is not None:
            d["tool_call_id"] = self.tool_call_id
        if self.name is not None:
            d["name"] = self.name
        return d


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class UsageReport:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StreamEvent:
    kind: Literal["delta", "tool_call_delta", "usage", "done", "error"]
    text: str | None = None
    tool_call: ToolCall | None = None
    usage: UsageReport | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"kind": self.kind}
        if self.text is not None:
            d["text"] = self.text
        if self.tool_call is not None:
            d["tool_call"] = self.tool_call.to_dict()
        if self.usage is not None:
            d["usage"] = self.usage.to_dict()
        if self.error is not None:
            d["error"] = self.error
        return d


@dataclass
class CancelToken:
    """Cooperative cancellation — adapters must check between chunks."""

    cancelled: bool = False

    def cancel(self) -> None:
        self.cancelled = True

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise InterruptedError("provider_request_cancelled")


@dataclass
class ChatResult:
    ok: bool
    provider_id: str
    message: Message | None = None
    usage: UsageReport | None = None
    paused: bool = False
    refused: bool = False
    exhausted_free_access: bool = False
    billing_activated: bool = False
    paid_fallback_used: bool = False
    live_verified: bool = False
    fixture_only: bool = False
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "provider_id": self.provider_id,
            "message": self.message.to_dict() if self.message else None,
            "usage": self.usage.to_dict() if self.usage else None,
            "paused": self.paused,
            "refused": self.refused,
            "exhausted_free_access": self.exhausted_free_access,
            "billing_activated": self.billing_activated,
            "paid_fallback_used": self.paid_fallback_used,
            "live_verified": self.live_verified,
            "fixture_only": self.fixture_only,
            "detail": self.detail,
        }
