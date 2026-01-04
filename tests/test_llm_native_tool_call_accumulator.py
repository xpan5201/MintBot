from __future__ import annotations

from src.llm_native.events import ToolCallAccumulator, ToolCallDeltaEvent


def test_tool_call_accumulator_merges_argument_deltas():
    acc = ToolCallAccumulator()

    acc.apply(
        ToolCallDeltaEvent(
            index=0,
            tool_call_id="call_1",
            name="get_weather",
            arguments_delta="{",
        )
    )
    acc.apply(
        ToolCallDeltaEvent(
            index=0,
            arguments_delta='"location":"Paris"}',
        )
    )

    calls = acc.list()
    assert len(calls) == 1
    assert calls[0].tool_call_id == "call_1"
    assert calls[0].name == "get_weather"
    assert calls[0].arguments_json == '{"location":"Paris"}'
