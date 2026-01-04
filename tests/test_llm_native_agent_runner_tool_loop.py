from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator

from src.llm_native.agent_runner import AgentRunnerConfig, NativeToolLoopRunner
from src.llm_native.backend import ChatBackend, ChatRequest, ChatResponse
from src.llm_native.events import (
    DoneEvent,
    TextDeltaEvent,
    ToolCallDeltaEvent,
    ToolResultEvent,
    ToolCallState,
)
from src.llm_native.messages import Message
from src.llm_native.tool_runner import ToolRunner
from src.llm_native.tools import ToolSpec
from src.utils.tool_context import ToolTraceRecorder, tool_trace_recorder_var


class FakeToolExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, float, dict[str, Any]]] = []

    def execute_tool(self, name: str, timeout: float, **kwargs: Any) -> str:
        self.calls.append((name, float(timeout), dict(kwargs)))
        return f"{name}={kwargs}"


@dataclass(slots=True)
class FakeBackend(ChatBackend):
    calls: int = 0

    def complete(self, request: ChatRequest) -> ChatResponse:  # pragma: no cover
        raise NotImplementedError

    def stream(self, request: ChatRequest) -> Iterator[Any]:
        self.calls += 1

        if self.calls == 1:
            yield ToolCallDeltaEvent(
                index=0,
                tool_call_id="call_1",
                name="calculator",
                arguments_delta='{"expression":"1+1"}',
            )
            yield DoneEvent(finish_reason="tool_calls")
            return

        if self.calls == 2:
            assert len(request.messages) >= 4
            assistant = request.messages[-2]
            tool = request.messages[-1]

            assert assistant.role == "assistant"
            assert assistant.tool_calls and assistant.tool_calls[0].id == "call_1"
            assert tool.role == "tool"
            assert tool.tool_call_id == "call_1"

            yield TextDeltaEvent(delta="OK")
            yield DoneEvent(finish_reason="stop")
            return

        raise AssertionError("unexpected extra backend call")


def test_native_tool_loop_runner_executes_tool_and_continues():
    backend = FakeBackend()
    executor = FakeToolExecutor()
    runner = NativeToolLoopRunner(
        backend=backend,
        tools=[
            ToolSpec(
                name="calculator",
                description="calc",
                parameters={
                    "type": "object",
                    "properties": {"expression": {"type": "string"}},
                    "required": ["expression"],
                    "additionalProperties": False,
                },
            )
        ],
        tool_runner=ToolRunner(tool_executor=executor),
        config=AgentRunnerConfig(max_tool_rounds=3, tool_timeout_s=1.0),
    )

    events = list(
        runner.stream(
            [
                Message(role="system", content="You are a helpful assistant."),
                Message(role="user", content="1+1?"),
            ]
        )
    )

    assert backend.calls == 2
    assert executor.calls == [("calculator", 1.0, {"expression": "1+1"})]

    assert any(isinstance(e, ToolResultEvent) for e in events)
    assert any(isinstance(e, TextDeltaEvent) and e.delta == "OK" for e in events)
    assert isinstance(events[-1], DoneEvent)
    assert events[-1].finish_reason == "stop"


def test_tool_runner_invalid_json_becomes_tool_output():
    executor = FakeToolExecutor()
    tool_runner = ToolRunner(tool_executor=executor)

    msgs = tool_runner.run(
        [
            ToolCallState(
                index=0,
                tool_call_id="call_1",
                name="calculator",
                arguments_json="{not json",
            )
        ],
        timeout_s=1.0,
    )

    assert len(msgs) == 1
    assert msgs[0].role == "tool"
    assert msgs[0].tool_call_id == "call_1"
    assert "工具参数解析失败" in str(msgs[0].content)
    assert executor.calls == []


def test_tool_runner_records_tool_traces_when_recorder_present():
    executor = FakeToolExecutor()
    tool_runner = ToolRunner(tool_executor=executor)
    recorder = ToolTraceRecorder()

    token = tool_trace_recorder_var.set(recorder)
    try:
        msgs = tool_runner.run(
            [
                ToolCallState(
                    index=0,
                    tool_call_id="call_1",
                    name="calculator",
                    arguments_json='{"expression":"1+1"}',
                )
            ],
            timeout_s=1.0,
        )
    finally:
        tool_trace_recorder_var.reset(token)

    assert len(msgs) == 1
    traces = recorder.snapshot()
    assert len(traces) == 1
    assert traces[0].name == "calculator"
    assert traces[0].args == {"expression": "1+1"}
    assert traces[0].error == ""
