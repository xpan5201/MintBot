from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator

from src.llm_native.agent_runner import AgentRunnerConfig, NativeToolLoopRunner
from src.llm_native.backend import BackendConfig, ChatBackend, ChatRequest, ChatResponse
from src.llm_native.events import (
    DoneEvent,
    ErrorEvent,
    TextDeltaEvent,
    ToolCallDeltaEvent,
    ToolResultEvent,
)
from src.llm_native.messages import Message, ToolCall
from src.llm_native.pipeline import Pipeline, PipelineRequest, PipelineResponse, PipelineStage
from src.llm_native.pipeline_stages import (
    ContextToolUsesTrimStage,
    PermissionScopedToolsStage,
    ToolCallLimitStage,
    ToolHeuristicPrefilterStage,
    ToolLlmSelectorStage,
    ToolTraceStage,
)
from src.llm_native.tool_runner import ToolRunner
from src.llm_native.tools import ToolSpec


class NoopToolExecutor:
    def execute_tool(self, name: str, timeout: float, **kwargs: Any) -> str:  # pragma: no cover
        raise AssertionError(f"tool should not be called: {name}")


class EchoToolExecutor:
    def execute_tool(self, name: str, timeout: float, **kwargs: Any) -> str:
        return f"ok:{name}"


class LongOutputToolExecutor:
    def execute_tool(self, name: str, timeout: float, **kwargs: Any) -> str:
        return "X" * 500


@dataclass(slots=True)
class MarkerBackend(ChatBackend):
    seen_marker: bool = False

    def complete(self, request: ChatRequest) -> ChatResponse:  # pragma: no cover
        raise NotImplementedError

    def stream(self, request: ChatRequest) -> Iterator[Any]:
        self.seen_marker = any(
            m.role == "system" and str(m.content) == "PIPELINE_MARK" for m in request.messages
        )
        yield TextDeltaEvent(delta="OK")
        yield DoneEvent(finish_reason="stop")


class MarkerStage(PipelineStage):
    def __init__(self) -> None:
        self.calls = 0

    def pre_model(self, request: PipelineRequest) -> PipelineRequest:
        self.calls += 1
        request.messages.append(Message(role="system", content="PIPELINE_MARK"))
        return request


def test_native_pipeline_pre_model_is_applied_to_backend_request():
    backend = MarkerBackend()
    stage = MarkerStage()
    runner = NativeToolLoopRunner(
        backend=backend,
        tools=[],
        tool_runner=ToolRunner(tool_executor=NoopToolExecutor()),
        config=AgentRunnerConfig(max_tool_rounds=0),
        pipeline=Pipeline(stages=[stage]),
    )

    events = list(runner.stream([Message(role="user", content="hi")]))

    assert stage.calls == 1
    assert backend.seen_marker is True
    assert any(isinstance(e, TextDeltaEvent) and e.delta == "OK" for e in events)
    assert isinstance(events[-1], DoneEvent)


class PostModelMarkerStage(PipelineStage):
    def __init__(self) -> None:
        self.calls = 0

    def post_model(self, response: PipelineResponse) -> PipelineResponse:
        self.calls += 1
        return response


def test_native_pipeline_post_model_is_invoked():
    backend = MarkerBackend()
    stage = PostModelMarkerStage()
    runner = NativeToolLoopRunner(
        backend=backend,
        tools=[],
        tool_runner=ToolRunner(tool_executor=NoopToolExecutor()),
        config=AgentRunnerConfig(max_tool_rounds=0),
        pipeline=Pipeline(stages=[stage]),
    )

    list(runner.stream([Message(role="user", content="hi")]))

    assert stage.calls == 1


@dataclass(slots=True)
class ToolFilterBackend(ChatBackend):
    seen_tool_names: list[str] | None = None

    def complete(self, request: ChatRequest) -> ChatResponse:  # pragma: no cover
        raise NotImplementedError

    def stream(self, request: ChatRequest) -> Iterator[Any]:
        self.seen_tool_names = [t.name for t in request.tools]
        yield TextDeltaEvent(delta="OK")
        yield DoneEvent(finish_reason="stop")


def _tool_spec(name: str) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=name,
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
    )


def test_permission_scoped_tools_stage_filters_by_profile_and_fallbacks():
    backend = ToolFilterBackend()
    stage = PermissionScopedToolsStage(
        profile_map={"dev": ["a"], "default": ["b"]},
        default_profile="default",
    )
    runner = NativeToolLoopRunner(
        backend=backend,
        tools=[_tool_spec("a"), _tool_spec("b")],
        tool_runner=ToolRunner(tool_executor=NoopToolExecutor()),
        config=AgentRunnerConfig(max_tool_rounds=0),
        pipeline=Pipeline(stages=[stage]),
    )

    list(
        runner.stream(
            [Message(role="user", content="hi")], pipeline_runtime={"tool_profile": "dev"}
        )
    )
    assert backend.seen_tool_names == ["a"]

    list(
        runner.stream(
            [Message(role="user", content="hi")],
            pipeline_runtime={"tool_profile": "unknown"},
        )
    )
    assert backend.seen_tool_names == ["b"]


def test_permission_scoped_tools_stage_downgrades_on_empty_result():
    backend = ToolFilterBackend()
    stage = PermissionScopedToolsStage(
        profile_map={"default": ["no_such_tool"]},
        default_profile="default",
    )
    runner = NativeToolLoopRunner(
        backend=backend,
        tools=[_tool_spec("a"), _tool_spec("b")],
        tool_runner=ToolRunner(tool_executor=NoopToolExecutor()),
        config=AgentRunnerConfig(max_tool_rounds=0),
        pipeline=Pipeline(stages=[stage]),
    )

    list(runner.stream([Message(role="user", content="hi")]))
    assert backend.seen_tool_names == ["a", "b"]


def test_tool_heuristic_prefilter_stage_filters_on_time_intent():
    backend = ToolFilterBackend()
    stage = ToolHeuristicPrefilterStage(always_include=["web_search"], max_tools=4, min_tools=0)
    runner = NativeToolLoopRunner(
        backend=backend,
        tools=[_tool_spec("get_current_time"), _tool_spec("web_search"), _tool_spec("foo_tool")],
        tool_runner=ToolRunner(tool_executor=NoopToolExecutor()),
        config=AgentRunnerConfig(max_tool_rounds=0),
        pipeline=Pipeline(stages=[stage]),
    )

    list(runner.stream([Message(role="user", content="what time is it now?")]))
    assert backend.seen_tool_names == ["get_current_time", "web_search"]


def test_tool_heuristic_prefilter_stage_no_intent_keeps_all_tools():
    backend = ToolFilterBackend()
    stage = ToolHeuristicPrefilterStage(always_include=["web_search"], max_tools=4, min_tools=0)
    runner = NativeToolLoopRunner(
        backend=backend,
        tools=[_tool_spec("get_current_time"), _tool_spec("web_search"), _tool_spec("foo_tool")],
        tool_runner=ToolRunner(tool_executor=NoopToolExecutor()),
        config=AgentRunnerConfig(max_tool_rounds=0),
        pipeline=Pipeline(stages=[stage]),
    )

    list(runner.stream([Message(role="user", content="hello there")]))
    assert backend.seen_tool_names == ["get_current_time", "web_search", "foo_tool"]


@dataclass(slots=True)
class TwoToolCallBackend(ChatBackend):
    call_count: int = 0

    def complete(self, request: ChatRequest) -> ChatResponse:  # pragma: no cover
        raise NotImplementedError

    def stream(self, request: ChatRequest) -> Iterator[Any]:
        self.call_count += 1
        yield ToolCallDeltaEvent(
            index=0,
            tool_call_id=f"call-{self.call_count}",
            name="foo_tool",
            arguments_delta=None,
        )
        yield DoneEvent(finish_reason="tool_calls")


def test_tool_call_limit_stage_aborts_when_exceeded():
    backend = TwoToolCallBackend()
    stage = ToolCallLimitStage(per_run_limit=1)
    runner = NativeToolLoopRunner(
        backend=backend,
        tools=[_tool_spec("foo_tool")],
        tool_runner=ToolRunner(tool_executor=EchoToolExecutor()),
        config=AgentRunnerConfig(max_tool_rounds=2),
        pipeline=Pipeline(stages=[stage]),
    )

    events = list(runner.stream([Message(role="user", content="hi")]))

    assert any(isinstance(e, ToolResultEvent) for e in events)
    assert any(
        isinstance(e, ErrorEvent) and e.exception_type == "ToolCallLimitError" for e in events
    )
    assert isinstance(events[-1], DoneEvent)
    assert events[-1].finish_reason == "tool_call_limit"


@dataclass(slots=True)
class MessageCaptureBackend(ChatBackend):
    seen_messages: list[Message] | None = None

    def complete(self, request: ChatRequest) -> ChatResponse:  # pragma: no cover
        raise NotImplementedError

    def stream(self, request: ChatRequest) -> Iterator[Any]:
        self.seen_messages = list(request.messages)
        yield TextDeltaEvent(delta="OK")
        yield DoneEvent(finish_reason="stop")


def test_context_tool_uses_trim_stage_drops_old_groups_but_keeps_last():
    backend = MessageCaptureBackend()
    stage = ContextToolUsesTrimStage(max_tool_context_tokens=16)
    runner = NativeToolLoopRunner(
        backend=backend,
        tools=[],
        tool_runner=ToolRunner(tool_executor=NoopToolExecutor()),
        config=AgentRunnerConfig(max_tool_rounds=0),
        pipeline=Pipeline(stages=[stage]),
    )

    messages: list[Message] = [
        Message(role="user", content="hi"),
        Message(
            role="assistant",
            content=None,
            tool_calls=[ToolCall(id="t1", name="foo_tool", arguments_json="{}")],
        ),
        Message(role="tool", content="X" * 400, tool_call_id="t1", name="foo_tool"),
        Message(role="assistant", content="after tool"),
        Message(
            role="assistant",
            content=None,
            tool_calls=[ToolCall(id="t2", name="foo_tool", arguments_json="{}")],
        ),
        Message(role="tool", content="ok", tool_call_id="t2", name="foo_tool"),
        Message(role="user", content="next"),
    ]

    list(runner.stream(messages))

    assert backend.seen_messages is not None
    tool_call_ids = [m.tool_call_id for m in backend.seen_messages if m.role == "tool"]
    assert "t1" not in tool_call_ids
    assert "t2" in tool_call_ids
    assert any(m.role == "user" and m.content == "hi" for m in backend.seen_messages)
    assert any(m.role == "assistant" and m.content == "after tool" for m in backend.seen_messages)
    assert any(m.role == "user" and m.content == "next" for m in backend.seen_messages)


def test_context_tool_uses_trim_stage_truncates_last_group_when_needed():
    backend = MessageCaptureBackend()
    stage = ContextToolUsesTrimStage(max_tool_context_tokens=8)
    runner = NativeToolLoopRunner(
        backend=backend,
        tools=[],
        tool_runner=ToolRunner(tool_executor=NoopToolExecutor()),
        config=AgentRunnerConfig(max_tool_rounds=0),
        pipeline=Pipeline(stages=[stage]),
    )

    messages: list[Message] = [
        Message(role="user", content="hi"),
        Message(
            role="assistant",
            content=None,
            tool_calls=[ToolCall(id="t1", name="foo_tool", arguments_json="{}")],
        ),
        Message(role="tool", content="X" * 200, tool_call_id="t1", name="foo_tool"),
    ]

    list(runner.stream(messages))

    assert backend.seen_messages is not None
    tool_messages = [m for m in backend.seen_messages if m.role == "tool"]
    assert len(tool_messages) == 1
    assert tool_messages[0].tool_call_id == "t1"
    assert tool_messages[0].content != "X" * 200
    assert "[truncated]" in str(tool_messages[0].content)


@dataclass(slots=True)
class SelectorBackend(ChatBackend):
    config: BackendConfig
    response_text: str = ""
    raise_on_complete: bool = False
    call_count: int = 0

    def complete(self, request: ChatRequest) -> ChatResponse:
        self.call_count += 1
        if self.raise_on_complete:
            raise RuntimeError("selector failed")
        return ChatResponse(output_text=self.response_text, finish_reason="stop")

    def stream(self, request: ChatRequest) -> Iterator[Any]:  # pragma: no cover
        raise NotImplementedError


def test_tool_llm_selector_stage_filters_tools_from_json_response():
    selector = SelectorBackend(
        config=BackendConfig(
            base_url="https://example.invalid", api_key="", model="m", timeout_s=1.0
        ),
        response_text='{"tools": ["foo_tool"]}',
    )
    stage = ToolLlmSelectorStage(
        backend=selector,
        max_tools=4,
        min_tools=0,
        always_include=["web_search"],
        disable_cooldown_s=0.0,
    )
    backend = ToolFilterBackend()
    runner = NativeToolLoopRunner(
        backend=backend,
        tools=[_tool_spec("foo_tool"), _tool_spec("bar_tool"), _tool_spec("web_search")],
        tool_runner=ToolRunner(tool_executor=NoopToolExecutor()),
        config=AgentRunnerConfig(max_tool_rounds=0),
        pipeline=Pipeline(stages=[stage]),
    )

    list(runner.stream([Message(role="user", content="selector-test-1")]))
    assert selector.call_count == 1
    assert backend.seen_tool_names == ["foo_tool", "web_search"]


def test_tool_llm_selector_stage_caches_selection_results_for_same_input():
    selector = SelectorBackend(
        config=BackendConfig(
            base_url="https://cache.invalid", api_key="", model="m", timeout_s=1.0
        ),
        response_text='{"tools": ["foo_tool"]}',
    )
    stage = ToolLlmSelectorStage(
        backend=selector,
        max_tools=4,
        min_tools=0,
        always_include=["web_search"],
        disable_cooldown_s=0.0,
    )
    backend = ToolFilterBackend()
    runner = NativeToolLoopRunner(
        backend=backend,
        tools=[_tool_spec("foo_tool"), _tool_spec("bar_tool"), _tool_spec("web_search")],
        tool_runner=ToolRunner(tool_executor=NoopToolExecutor()),
        config=AgentRunnerConfig(max_tool_rounds=0),
        pipeline=Pipeline(stages=[stage]),
    )

    list(runner.stream([Message(role="user", content="cache-test-1")]))
    list(runner.stream([Message(role="user", content="cache-test-1")]))
    assert selector.call_count == 1


def test_tool_llm_selector_stage_trips_circuit_breaker_on_failure_and_skips_next_call():
    selector = SelectorBackend(
        config=BackendConfig(
            base_url="https://breaker.invalid", api_key="", model="m", timeout_s=1.0
        ),
        raise_on_complete=True,
    )
    stage = ToolLlmSelectorStage(
        backend=selector,
        max_tools=4,
        min_tools=0,
        always_include=["web_search"],
        disable_cooldown_s=3600.0,
    )
    backend = ToolFilterBackend()
    runner = NativeToolLoopRunner(
        backend=backend,
        tools=[_tool_spec("foo_tool"), _tool_spec("bar_tool"), _tool_spec("web_search")],
        tool_runner=ToolRunner(tool_executor=NoopToolExecutor()),
        config=AgentRunnerConfig(max_tool_rounds=0),
        pipeline=Pipeline(stages=[stage]),
    )

    list(runner.stream([Message(role="user", content="breaker-test-1")]))
    assert selector.call_count == 1
    assert backend.seen_tool_names == ["foo_tool", "bar_tool", "web_search"]

    selector.raise_on_complete = False
    selector.response_text = '{"tools": ["foo_tool"]}'
    list(runner.stream([Message(role="user", content="breaker-test-1")]))
    assert selector.call_count == 1
    assert backend.seen_tool_names == ["foo_tool", "bar_tool", "web_search"]


@dataclass(slots=True)
class TwoRoundToolCallBackend(ChatBackend):
    call_count: int = 0
    second_seen_messages: list[Message] | None = None

    def complete(self, request: ChatRequest) -> ChatResponse:  # pragma: no cover
        raise NotImplementedError

    def stream(self, request: ChatRequest) -> Iterator[Any]:
        self.call_count += 1
        if self.call_count == 1:
            yield ToolCallDeltaEvent(
                index=0,
                tool_call_id="t1",
                name="foo_tool",
                arguments_delta=None,
            )
            yield DoneEvent(finish_reason="tool_calls")
            return

        self.second_seen_messages = list(request.messages)
        yield TextDeltaEvent(delta="OK")
        yield DoneEvent(finish_reason="stop")


def test_tool_trace_stage_truncates_tool_messages_before_next_round():
    backend = TwoRoundToolCallBackend()
    stage = ToolTraceStage(max_output_chars=120)
    runner = NativeToolLoopRunner(
        backend=backend,
        tools=[_tool_spec("foo_tool")],
        tool_runner=ToolRunner(tool_executor=LongOutputToolExecutor()),
        config=AgentRunnerConfig(max_tool_rounds=2),
        pipeline=Pipeline(stages=[stage]),
    )

    list(runner.stream([Message(role="user", content="hi")]))

    assert backend.second_seen_messages is not None
    tool_messages = [m for m in backend.second_seen_messages if m.role == "tool"]
    assert len(tool_messages) == 1
    assert tool_messages[0].tool_call_id == "t1"
    assert "工具输出已截断" in str(tool_messages[0].content)
