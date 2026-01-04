from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class TextDeltaEvent:
    delta: str
    type: Literal["text.delta"] = "text.delta"


@dataclass(frozen=True, slots=True)
class ToolCallDeltaEvent:
    index: int
    tool_call_id: str | None = None
    name: str | None = None
    arguments_delta: str | None = None
    type: Literal["tool_call.delta"] = "tool_call.delta"


@dataclass(frozen=True, slots=True)
class ToolResultEvent:
    tool_call_id: str
    content: str
    type: Literal["tool.result"] = "tool.result"


@dataclass(frozen=True, slots=True)
class ErrorEvent:
    message: str
    exception_type: str | None = None
    type: Literal["error"] = "error"


@dataclass(frozen=True, slots=True)
class DoneEvent:
    finish_reason: str | None = None
    type: Literal["done"] = "done"


StreamEvent = TextDeltaEvent | ToolCallDeltaEvent | ToolResultEvent | ErrorEvent | DoneEvent


@dataclass(slots=True)
class ToolCallState:
    index: int
    tool_call_id: str | None = None
    name: str | None = None
    arguments_json: str = ""

    def is_complete(self) -> bool:
        return bool(self.tool_call_id and self.name)


class ToolCallAccumulator:
    """Accumulate streaming tool_call deltas (Chat Completions style)."""

    def __init__(self) -> None:
        self._calls: dict[int, ToolCallState] = {}

    def apply(self, event: ToolCallDeltaEvent) -> None:
        state = self._calls.get(event.index)
        if state is None:
            state = ToolCallState(index=event.index)
            self._calls[event.index] = state

        if event.tool_call_id:
            state.tool_call_id = event.tool_call_id
        if event.name:
            state.name = event.name
        if event.arguments_delta:
            state.arguments_json += event.arguments_delta

    def list(self) -> list[ToolCallState]:
        return [self._calls[i] for i in sorted(self._calls)]
