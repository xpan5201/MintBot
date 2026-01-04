from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Sequence

Role = Literal["system", "developer", "user", "assistant", "tool"]


@dataclass(frozen=True, slots=True)
class TextPart:
    """Chat content part: plain text."""

    text: str

    def to_openai(self) -> dict[str, Any]:
        return {"type": "text", "text": self.text}


@dataclass(frozen=True, slots=True)
class ImageURLPart:
    """Chat content part: image URL (OpenAI-compatible image_url block)."""

    url: str
    detail: Literal["auto", "low", "high"] | None = None

    def to_openai(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"url": self.url}
        if self.detail:
            payload["detail"] = self.detail
        return {"type": "image_url", "image_url": payload}


ContentPart = TextPart | ImageURLPart | dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolCall:
    """Assistant tool call (OpenAI chat.completions tool_calls item)."""

    id: str
    name: str
    arguments_json: str
    type: Literal["function"] = "function"

    def to_openai(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "function": {"name": self.name, "arguments": self.arguments_json},
        }


@dataclass(frozen=True, slots=True)
class Message:
    """Project-internal message protocol aligned to OpenAI Chat Completions."""

    role: Role
    content: str | list[ContentPart] | None = None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[ToolCall] | None = None

    def __post_init__(self) -> None:
        if self.role == "tool":
            if not self.tool_call_id:
                raise ValueError("tool message requires tool_call_id")
            if self.tool_calls:
                raise ValueError("tool message must not include tool_calls")
        else:
            if self.tool_call_id:
                raise ValueError("tool_call_id is only valid for tool messages")

        if self.role != "assistant" and self.tool_calls:
            raise ValueError("tool_calls is only valid for assistant messages")

        if self.content is None and self.role not in ("assistant",):
            raise ValueError("content cannot be None for non-assistant messages")

    def to_openai(self) -> dict[str, Any]:
        msg: dict[str, Any] = {"role": self.role}

        if self.name:
            msg["name"] = self.name

        if self.role == "tool":
            msg["tool_call_id"] = self.tool_call_id

        if isinstance(self.content, list):
            msg["content"] = [
                part.to_openai() if hasattr(part, "to_openai") else part for part in self.content
            ]
        else:
            msg["content"] = self.content

        if self.tool_calls:
            msg["tool_calls"] = [tc.to_openai() for tc in self.tool_calls]

        return msg


def _tool_call_from_openai(payload: Any) -> ToolCall | None:
    if not isinstance(payload, dict):
        return None
    tool_call_id = payload.get("id")
    function = payload.get("function") or {}
    if not isinstance(function, dict):
        function = {}
    name = function.get("name")
    arguments = function.get("arguments")
    if not tool_call_id or not name:
        return None
    return ToolCall(
        id=str(tool_call_id),
        name=str(name),
        arguments_json=str(arguments or ""),
    )


def message_from_openai(payload: dict[str, Any]) -> Message:
    """Best-effort conversion from OpenAI-shaped message dict to Message."""
    role = str(payload.get("role") or "user").strip()
    if role not in {"system", "developer", "user", "assistant", "tool"}:
        role = "user"

    content: Any = payload.get("content")
    name = payload.get("name")
    tool_call_id = payload.get("tool_call_id")

    tool_calls_payload = payload.get("tool_calls")
    tool_calls: list[ToolCall] | None = None
    if role == "assistant" and tool_calls_payload:
        calls: list[ToolCall] = []
        for item in tool_calls_payload if isinstance(tool_calls_payload, list) else []:
            tc = _tool_call_from_openai(item)
            if tc is not None:
                calls.append(tc)
        tool_calls = calls or None

    if content is None and role != "assistant":
        content = ""

    if role == "tool" and not tool_call_id:
        # Defensive: malformed tool messages may exist in persisted history; do not crash.
        role = "assistant"
        tool_call_id = None

    return Message(
        role=role,  # type: ignore[arg-type]
        content=content,
        name=str(name) if name else None,
        tool_call_id=str(tool_call_id) if tool_call_id else None,
        tool_calls=tool_calls,
    )


def messages_from_openai(payloads: Sequence[dict[str, Any]]) -> list[Message]:
    return [message_from_openai(p) for p in payloads]
