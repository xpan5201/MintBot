from __future__ import annotations

from dataclasses import dataclass
from threading import Event
from typing import Iterator, Sequence

from .backend import ChatBackend, ChatRequest
from .events import (
    DoneEvent,
    ErrorEvent,
    StreamEvent,
    TextDeltaEvent,
    ToolCallAccumulator,
    ToolResultEvent,
)
from .messages import Message, ToolCall
from .pipeline import Pipeline, PipelineAbort, PipelineRequest, PipelineResponse
from .tool_runner import ToolRunner
from .tools import ToolSpec


@dataclass(frozen=True, slots=True)
class AgentRunnerConfig:
    max_tool_rounds: int = 6
    tool_timeout_s: float = 30.0
    temperature: float | None = None
    max_tokens: int | None = None


@dataclass(slots=True)
class NativeToolLoopRunner:
    """
    Self-hosted tool-loop runner (Chat Completions style).

    This runner is intentionally minimal and kept separate from MintChatAgent to enable staged
    rollout and focused testing. The default product path remains the legacy agent runtime unless
    explicitly enabled via settings.
    """

    backend: ChatBackend
    tools: Sequence[ToolSpec]
    tool_runner: ToolRunner
    config: AgentRunnerConfig = AgentRunnerConfig()
    pipeline: Pipeline | None = None

    def stream(
        self,
        messages: Sequence[Message],
        *,
        cancel_event: Event | None = None,
        pipeline_runtime: dict[str, object] | None = None,
    ) -> Iterator[StreamEvent]:
        convo: list[Message] = list(messages)

        for round_idx in range(max(0, int(self.config.max_tool_rounds)) + 1):
            if cancel_event and cancel_event.is_set():
                return

            accumulator = ToolCallAccumulator()
            buffered_text: list[TextDeltaEvent] = []
            finish_reason: str | None = None

            request_messages: Sequence[Message] = convo
            request_tools: Sequence[ToolSpec] = self.tools
            if self.pipeline is not None:
                pipeline_request = PipelineRequest(
                    messages=list(convo),
                    tools=list(self.tools),
                    runtime=dict(pipeline_runtime or {}),
                )
                try:
                    pipeline_request = self.pipeline.apply_pre_model(pipeline_request)
                except PipelineAbort as exc:
                    yield ErrorEvent(
                        message=str(exc) or repr(exc),
                        exception_type=str(getattr(exc, "exception_type", type(exc).__name__)),
                    )
                    yield DoneEvent(
                        finish_reason=str(getattr(exc, "finish_reason", "pipeline_abort"))
                    )
                    return
                request_messages = pipeline_request.messages
                request_tools = pipeline_request.tools

            request = ChatRequest(
                messages=request_messages,
                tools=request_tools,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )

            try:
                for event in self.backend.stream(request):
                    if cancel_event and cancel_event.is_set():
                        return

                    event_type = getattr(event, "type", "")
                    if event_type == "text.delta":
                        delta = str(getattr(event, "delta", "") or "")
                        if self.pipeline is not None:
                            try:
                                delta = self.pipeline.apply_stream_filter(delta)
                            except PipelineAbort as exc:
                                yield ErrorEvent(
                                    message=str(exc) or repr(exc),
                                    exception_type=str(
                                        getattr(exc, "exception_type", type(exc).__name__)
                                    ),
                                )
                                yield DoneEvent(
                                    finish_reason=str(
                                        getattr(exc, "finish_reason", "pipeline_abort")
                                    )
                                )
                                return
                        if delta:
                            buffered_text.append(TextDeltaEvent(delta=delta))
                    elif event_type == "tool_call.delta":
                        accumulator.apply(event)  # type: ignore[arg-type]
                    elif event_type == "done":
                        finish_reason = getattr(event, "finish_reason", None)
                    else:
                        # Ignore unknown event types for robustness.
                        pass
            except Exception as exc:
                yield ErrorEvent(message=str(exc) or repr(exc), exception_type=type(exc).__name__)
                yield DoneEvent(finish_reason="error")
                return

            tool_calls = [c for c in accumulator.list() if c.is_complete()]
            if self.pipeline is not None:
                pipeline_response = PipelineResponse(
                    events=list(buffered_text),
                    tool_calls=list(tool_calls),
                    finish_reason=finish_reason,
                )
                try:
                    pipeline_response = self.pipeline.apply_post_model(pipeline_response)
                except PipelineAbort as exc:
                    yield ErrorEvent(
                        message=str(exc) or repr(exc),
                        exception_type=str(getattr(exc, "exception_type", type(exc).__name__)),
                    )
                    yield DoneEvent(
                        finish_reason=str(getattr(exc, "finish_reason", "pipeline_abort"))
                    )
                    return

                finish_reason = pipeline_response.finish_reason
                tool_calls = list(pipeline_response.tool_calls)
                buffered_text = [
                    e
                    for e in pipeline_response.events
                    if isinstance(e, TextDeltaEvent) and bool(getattr(e, "delta", ""))
                ]
            if tool_calls:
                if self.pipeline is not None:
                    try:
                        tool_calls = self.pipeline.apply_pre_tool_calls(tool_calls)
                    except PipelineAbort as exc:
                        yield ErrorEvent(
                            message=str(exc) or repr(exc),
                            exception_type=str(getattr(exc, "exception_type", type(exc).__name__)),
                        )
                        yield DoneEvent(
                            finish_reason=str(getattr(exc, "finish_reason", "pipeline_abort"))
                        )
                        return

                if round_idx >= int(self.config.max_tool_rounds):
                    yield ErrorEvent(
                        message="tool loop exceeded max_tool_rounds",
                        exception_type="ToolLoopLimitError",
                    )
                    yield DoneEvent(finish_reason="tool_loop_limit")
                    return

                assistant_tool_calls = [
                    ToolCall(
                        id=str(c.tool_call_id),
                        name=str(c.name),
                        arguments_json=str(c.arguments_json or ""),
                    )
                    for c in tool_calls
                ]
                convo.append(
                    Message(role="assistant", content=None, tool_calls=assistant_tool_calls)
                )

                tool_messages = self.tool_runner.run(
                    tool_calls,
                    cancel_event=cancel_event,
                    timeout_s=float(self.config.tool_timeout_s),
                )
                if self.pipeline is not None:
                    try:
                        tool_messages = self.pipeline.apply_post_tool_messages(tool_messages)
                    except PipelineAbort as exc:
                        yield ErrorEvent(
                            message=str(exc) or repr(exc),
                            exception_type=str(getattr(exc, "exception_type", type(exc).__name__)),
                        )
                        yield DoneEvent(
                            finish_reason=str(getattr(exc, "finish_reason", "pipeline_abort"))
                        )
                        return
                for msg in tool_messages:
                    convo.append(msg)
                    yield ToolResultEvent(
                        tool_call_id=str(msg.tool_call_id), content=str(msg.content)
                    )
                continue

            # No tool calls: emit buffered text and finish.
            for t in buffered_text:
                yield t
            yield DoneEvent(finish_reason=finish_reason)
            return
