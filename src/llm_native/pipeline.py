from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from src.utils.logger import logger

from .events import StreamEvent, ToolCallState
from .messages import Message
from .tools import ToolSpec


@dataclass(slots=True)
class PipelineRequest:
    """Mutable request payload passed through pipeline stages."""

    messages: list[Message]
    tools: list[ToolSpec]
    runtime: dict[str, Any] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PipelineResponse:
    """Model output payload passed through pipeline stages."""

    events: list[StreamEvent] = field(default_factory=list)
    tool_calls: list[ToolCallState] = field(default_factory=list)
    finish_reason: str | None = None
    final_text: str | None = None


class PipelineAbort(RuntimeError):
    """Intentional abort signal for Pipeline stages (must not be swallowed)."""

    def __init__(
        self,
        message: str,
        *,
        exception_type: str = "PipelineAbort",
        finish_reason: str = "pipeline_abort",
    ) -> None:
        super().__init__(message)
        self.exception_type = exception_type
        self.finish_reason = finish_reason


class PipelineStage:
    """Base class for Pipeline stages (override what you need)."""

    def name(self) -> str:
        return type(self).__name__

    def pre_model(self, request: PipelineRequest) -> PipelineRequest:  # noqa: D401
        """Transform model request (messages/tools/runtime)."""
        return request

    def post_model(self, response: PipelineResponse) -> PipelineResponse:
        """Transform model output (buffered text/tool calls)."""
        return response

    def pre_tool_calls(self, tool_calls: list[ToolCallState]) -> list[ToolCallState]:
        """Transform tool calls before execution."""
        return tool_calls

    def post_tool_messages(self, tool_messages: list[Message]) -> list[Message]:
        """Transform tool result messages after execution."""
        return tool_messages

    def stream_filter(self, delta: str) -> str:
        """Filter streaming text delta (optional)."""
        return delta


@dataclass(slots=True)
class Pipeline:
    """Stage runner with defensive error handling (stable-first)."""

    stages: Sequence[PipelineStage] = ()

    def apply_pre_model(self, request: PipelineRequest) -> PipelineRequest:
        current = request
        for stage in self.stages:
            try:
                current = stage.pre_model(current)
            except PipelineAbort:
                raise
            except Exception:
                logger.warning("Pipeline stage failed (pre_model): %s", stage.name(), exc_info=True)
        return current

    def apply_post_model(self, response: PipelineResponse) -> PipelineResponse:
        current = response
        for stage in self.stages:
            try:
                current = stage.post_model(current)
            except PipelineAbort:
                raise
            except Exception:
                logger.warning(
                    "Pipeline stage failed (post_model): %s", stage.name(), exc_info=True
                )
        return current

    def apply_pre_tool_calls(self, tool_calls: list[ToolCallState]) -> list[ToolCallState]:
        current = tool_calls
        for stage in self.stages:
            try:
                current = stage.pre_tool_calls(current)
            except PipelineAbort:
                raise
            except Exception:
                logger.warning(
                    "Pipeline stage failed (pre_tool_calls): %s", stage.name(), exc_info=True
                )
        return current

    def apply_post_tool_messages(self, tool_messages: list[Message]) -> list[Message]:
        current = tool_messages
        for stage in self.stages:
            try:
                current = stage.post_tool_messages(current)
            except PipelineAbort:
                raise
            except Exception:
                logger.warning(
                    "Pipeline stage failed (post_tool_messages): %s", stage.name(), exc_info=True
                )
        return current

    def apply_stream_filter(self, delta: str) -> str:
        current = delta
        for stage in self.stages:
            try:
                current = stage.stream_filter(current)
            except PipelineAbort:
                raise
            except Exception:
                logger.warning(
                    "Pipeline stage failed (stream_filter): %s", stage.name(), exc_info=True
                )
        return current


def ensure_list(items: Iterable[ToolSpec] | Sequence[ToolSpec]) -> list[ToolSpec]:
    """Best-effort conversion to a plain list without copying when already a list."""
    if isinstance(items, list):
        return items
    return list(items)
