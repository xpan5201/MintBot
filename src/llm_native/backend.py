from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator, Protocol, Sequence

from .events import StreamEvent
from .messages import Message
from .tools import ToolSpec


@dataclass(frozen=True, slots=True)
class BackendConfig:
    """Runtime config for an OpenAI-compatible backend."""

    base_url: str
    api_key: str
    model: str
    timeout_s: float = 60.0
    max_retries: int = 2


@dataclass(frozen=True, slots=True)
class ChatRequest:
    messages: Sequence[Message]
    tools: Sequence[ToolSpec] | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    extra: dict[str, Any] | None = None

    def to_openai_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "messages": [m.to_openai() for m in self.messages],
        }
        if self.tools:
            kwargs["tools"] = [t.to_openai() for t in self.tools]
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        if self.max_tokens is not None:
            kwargs["max_tokens"] = self.max_tokens
        if self.extra:
            kwargs.update(self.extra)
        return kwargs


@dataclass(frozen=True, slots=True)
class ChatResponse:
    output_text: str
    finish_reason: str | None = None


class ChatBackend(Protocol):
    """Backend interface used by the future native implementation."""

    def complete(self, request: ChatRequest) -> ChatResponse:
        raise NotImplementedError

    def stream(self, request: ChatRequest) -> Iterator[StreamEvent]:
        raise NotImplementedError
