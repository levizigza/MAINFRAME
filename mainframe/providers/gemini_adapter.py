"""Gemini adapter — native generateContent shapes (not OpenAI messages).

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

PROVIDER_ID = "google_gemini_api"
META = INVESTIGATIONS[PROVIDER_ID]


def features() -> dict[str, Any]:
    return {
        "provider_id": PROVIDER_ID,
        "openai_compatible_assumed": False,
        "roles_native": ["user", "model"],
        "system_via": "systemInstruction",
        "tools": True,
        "streaming": True,
        "cancellation": True,
        "usage_reporting": True,
        "live_dispatch": META["live_dispatch"],
        "live_verified": False,
        "label": META["label"],
    }


def to_native_contents(messages: list[Message]) -> dict[str, Any]:
    """Translate canonical messages → Gemini contents + systemInstruction."""
    system_parts: list[str] = []
    contents: list[dict[str, Any]] = []
    for m in messages:
        if m.role == "system":
            if m.content:
                system_parts.append(m.content)
            continue
        if m.role == "tool":
            # Gemini function response part
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": m.name or "tool",
                                "response": {"content": m.content},
                            }
                        }
                    ],
                }
            )
            continue
        role = "model" if m.role == "assistant" else "user"
        parts: list[dict[str, Any]] = []
        if m.content:
            parts.append({"text": m.content})
        for tc in m.tool_calls:
            parts.append({"functionCall": {"name": tc.name, "args": tc.arguments}})
        contents.append({"role": role, "parts": parts or [{"text": ""}]})
    payload: dict[str, Any] = {"contents": contents}
    if system_parts:
        payload["systemInstruction"] = {"parts": [{"text": "\n".join(system_parts)}]}
    return payload


def to_native_tools(tools: list[ToolSpec]) -> dict[str, Any]:
    return {
        "tools": [
            {
                "functionDeclarations": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    }
                    for t in tools
                ]
            }
        ]
    }


def from_native_candidate(candidate: dict[str, Any]) -> Message:
    parts = ((candidate.get("content") or {}).get("parts")) or []
    texts: list[str] = []
    tool_calls: list[ToolCall] = []
    for i, p in enumerate(parts):
        if "text" in p:
            texts.append(str(p["text"]))
        if "functionCall" in p:
            fc = p["functionCall"]
            tool_calls.append(
                ToolCall(
                    id=f"gemini_fc_{i}",
                    name=str(fc.get("name") or ""),
                    arguments=dict(fc.get("args") or {}),
                )
            )
    return Message(
        role="assistant",
        content="".join(texts) if texts else None,
        tool_calls=tool_calls,
    )


def run_fixture(
    messages: list[Message],
    tools: list[ToolSpec] | None = None,
    *,
    stream: bool = False,
    cancel: CancelToken | None = None,
) -> ChatResult | Iterator[StreamEvent]:
    cancel = cancel or CancelToken()
    native = to_native_contents(messages)
    if tools:
        native.update(to_native_tools(tools))
    cancel.raise_if_cancelled()
    if tools:
        msg = Message(
            role="assistant",
            content=None,
            tool_calls=[ToolCall(id="gemini_fc_0", name=tools[0].name, arguments={"q": "x"})],
        )
        if stream:
            return iter(
                [
                    StreamEvent(kind="tool_call_delta", tool_call=msg.tool_calls[0]),
                    StreamEvent(kind="usage", usage=UsageReport(input_tokens=9, output_tokens=3, total_tokens=12)),
                    StreamEvent(kind="done"),
                ]
            )
        return fixture_result(PROVIDER_ID, msg, {"native": native, "usageMetadata": {"promptTokenCount": 9}})
    msg = Message(role="assistant", content="fixture-ok-gemini")
    if stream:
        return iter(
            [
                StreamEvent(kind="delta", text="fixture-ok-gemini"),
                StreamEvent(kind="usage", usage=UsageReport(total_tokens=6)),
                StreamEvent(kind="done"),
            ]
        )
    return fixture_result(PROVIDER_ID, msg, {"native": native})


def live_chat(messages: list[Message], **_: Any) -> ChatResult:
    return refuse_disabled(
        PROVIDER_ID,
        META["verdict_reason"] + " Credentials stay in broker; no paid fallback.",
    )


def handle_http_error(status: int, body: str) -> ChatResult:
    if status in {429, 403} or "RESOURCE_EXHAUSTED" in body:
        return pause_on_exhaustion(PROVIDER_ID, status=status, body=body)
    return refuse_disabled(PROVIDER_ID, f"HTTP {status}; no paid fallback.")
