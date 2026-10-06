"""Groq adapter — OpenAI-shaped surface, not assumed full OpenAI parity.

Live dispatch disabled until investigation + entitlement verify recurring free access.
"""

from __future__ import annotations

from typing import Any, Iterator

from mainframe.providers.exhaust import fixture_result, pause_on_exhaustion, refuse_disabled
from mainframe.providers.investigation import INVESTIGATIONS
from mainframe.providers.types import (
    CancelToken,
    ChatResult,
    Message,
    StreamEvent,
    ToolCall,
    ToolSpec,
    UsageReport,
)

PROVIDER_ID = "groq_cloud"
META = INVESTIGATIONS[PROVIDER_ID]


def features() -> dict[str, Any]:
    return {
        "provider_id": PROVIDER_ID,
        "openai_compatible_assumed": False,
        "roles": ["system", "user", "assistant", "tool"],
        "tools": True,
        "streaming": True,
        "cancellation": True,
        "usage_reporting": True,
        "live_dispatch": META["live_dispatch"],
        "live_verified": False,
        "label": META["label"],
    }


def to_native_messages(messages: list[Message]) -> list[dict[str, Any]]:
    """Map canonical → Groq chat message objects (subset only)."""
    out: list[dict[str, Any]] = []
    for m in messages:
        item: dict[str, Any] = {"role": m.role}
        if m.content is not None:
            item["content"] = m.content
        if m.tool_calls:
            item["tool_calls"] = [
                {
                    "id": t.id,
                    "type": "function",
                    "function": {"name": t.name, "arguments": _args_json(t.arguments)},
                }
                for t in m.tool_calls
            ]
        if m.tool_call_id:
            item["tool_call_id"] = m.tool_call_id
        out.append(item)
    return out


def to_native_tools(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in tools
    ]


def from_native_message(data: dict[str, Any]) -> Message:
    tool_calls: list[ToolCall] = []
    for tc in data.get("tool_calls") or []:
        fn = tc.get("function") or {}
        args = fn.get("arguments")
        if isinstance(args, str):
            import json

            try:
                args = json.loads(args)
            except Exception:  # noqa: BLE001
                args = {"raw": args}
        tool_calls.append(
            ToolCall(id=str(tc.get("id") or ""), name=str(fn.get("name") or ""), arguments=args or {})
        )
    return Message(
        role=data.get("role") or "assistant",  # type: ignore[arg-type]
        content=data.get("content"),
        tool_calls=tool_calls,
    )


def _args_json(args: dict[str, Any]) -> str:
    import json

    return json.dumps(args)


def run_fixture(
    messages: list[Message],
    tools: list[ToolSpec] | None = None,
    *,
    stream: bool = False,
    cancel: CancelToken | None = None,
) -> ChatResult | Iterator[StreamEvent]:
    """Protocol fixture — no network. Labeled unverified live."""
    cancel = cancel or CancelToken()
    native_in = to_native_messages(messages)
    native_tools = to_native_tools(tools or [])
    # Simulate assistant tool call then text when tools present
    if tools:
        cancel.raise_if_cancelled()
        msg = Message(
            role="assistant",
            content=None,
            tool_calls=[ToolCall(id="call_fix_1", name=tools[0].name, arguments={"query": "demo"})],
        )
        if stream:
            return iter(
                [
                    StreamEvent(kind="tool_call_delta", tool_call=msg.tool_calls[0]),
                    StreamEvent(kind="usage", usage=UsageReport(input_tokens=12, output_tokens=4, total_tokens=16)),
                    StreamEvent(kind="done"),
                ]
            )
        return fixture_result(
            PROVIDER_ID,
            msg,
            {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16, "native_in": native_in, "tools": native_tools},
        )
    cancel.raise_if_cancelled()
    msg = Message(role="assistant", content="fixture-ok")
    if stream:
        return iter(
            [
                StreamEvent(kind="delta", text="fixture-"),
                StreamEvent(kind="delta", text="ok"),
                StreamEvent(kind="usage", usage=UsageReport(input_tokens=5, output_tokens=2, total_tokens=7)),
                StreamEvent(kind="done"),
            ]
        )
    return fixture_result(PROVIDER_ID, msg, {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7})


def live_chat(messages: list[Message], **_: Any) -> ChatResult:
    """Live path — refused while unverified / disabled."""
    return refuse_disabled(
        PROVIDER_ID,
        META["verdict_reason"] + " Credentials stay in broker; no paid fallback.",
    )


def handle_http_error(status: int, body: str) -> ChatResult:
    if status == 429 or "rate" in body.lower():
        return pause_on_exhaustion(PROVIDER_ID, status=status, body=body)
    return refuse_disabled(PROVIDER_ID, f"HTTP {status}; no paid fallback.")
