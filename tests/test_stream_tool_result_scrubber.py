from __future__ import annotations

from time import perf_counter

from src.agent.core import MintChatAgent, StreamToolTraceScrubber
from src.utils.tool_context import ToolTraceRecorder


def test_stream_tool_trace_scrubber_strips_tool_result_across_chunks() -> None:
    scrubber = StreamToolTraceScrubber()
    chunks = [
        "TOOL_RE",
        "SULT: get_current_time\n",
        "local_time: 2025-12-26 22:44:00\n",
        "当然是真的喵！",
    ]
    output = "".join(scrubber.process(chunk) for chunk in chunks) + scrubber.flush()
    assert "TOOL_RESULT" not in output
    assert "local_time" not in output
    assert "当然是真的喵" in output


def test_tool_trace_fallback_humanizes_tool_result_time() -> None:
    agent = MintChatAgent.__new__(MintChatAgent)

    recorder = ToolTraceRecorder()
    recorder.mark_start()
    recorder.record_end(
        "get_current_time",
        {},
        started_at=perf_counter(),
        output="TOOL_RESULT: get_current_time\nlocal_time: 2025-12-26 22:44:00",
    )

    text = agent._format_tool_trace_fallback(recorder)
    assert "TOOL_RESULT" not in text
    assert "local_time" not in text
    assert "2025-12-26" in text


def test_stream_tool_trace_scrubber_keeps_user_json_list() -> None:
    scrubber = StreamToolTraceScrubber()
    chunks = ['["a_b","c_d"]\n', "ok"]
    output = "".join(scrubber.process(chunk) for chunk in chunks) + scrubber.flush()
    assert '["a_b","c_d"]' in output
    assert "ok" in output


def test_stream_tool_trace_scrubber_strips_route_tag_list_when_leaked() -> None:
    scrubber = StreamToolTraceScrubber()
    chunks = ['["local_search","map_guide"]}\n', "hello"]
    output = "".join(scrubber.process(chunk) for chunk in chunks) + scrubber.flush()
    assert "local_search" not in output
    assert "map_guide" not in output
    assert "hello" in output
