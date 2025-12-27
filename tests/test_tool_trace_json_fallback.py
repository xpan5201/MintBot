from __future__ import annotations

from time import perf_counter

from src.agent.core import MintChatAgent
from src.utils.tool_context import ToolTraceRecorder


def test_format_tool_trace_fallback_summarizes_json_time() -> None:
    agent = MintChatAgent.__new__(MintChatAgent)

    recorder = ToolTraceRecorder()
    recorder.mark_start()
    recorder.record_end(
        "get_time_in_timezone",
        {"timezone_name": "Asia/Shanghai"},
        started_at=perf_counter(),
        output=(
            '{\n'
            '  "timezone": "Asia/Shanghai",\n'
            '  "date": "2025-12-27",\n'
            '  "time": "22:44:00",\n'
            '  "day_of_week": "Saturday",\n'
            '  "is_dst": false\n'
            "}"
        ),
    )

    reply = agent._format_tool_trace_fallback(recorder)
    assert reply
    assert "现在是" in reply
    assert "2025-12-27" in reply
    assert "22:44" in reply
    assert "喵" in reply
    assert "{" not in reply
    assert "}" not in reply


def test_looks_like_tool_echo_reply_triggers_on_short_json() -> None:
    recorder = ToolTraceRecorder()
    assert MintChatAgent._looks_like_tool_echo_reply('{"a": 1}', recorder) is True


def test_format_tool_trace_fallback_returns_raw_when_user_requests_json() -> None:
    agent = MintChatAgent.__new__(MintChatAgent)

    recorder = ToolTraceRecorder()
    recorder.mark_start()
    recorder.record_end(
        "get_time_in_timezone",
        {"timezone_name": "Asia/Shanghai"},
        started_at=perf_counter(),
        output='{"timezone": "Asia/Shanghai", "date": "2025-12-27", "time": "22:44:00"}',
    )

    reply = agent._format_tool_trace_fallback(recorder, user_message="请以 JSON 格式原样返回")
    assert reply.strip().startswith("{")
    assert "timezone" in reply
    assert "现在是" not in reply


def test_user_prefers_raw_tool_output_detects_json_directive_and_negation() -> None:
    assert MintChatAgent._user_prefers_raw_tool_output("请以 JSON 格式返回") is True
    assert MintChatAgent._user_prefers_raw_tool_output("不要 JSON，用自然语言回答") is False
    assert MintChatAgent._user_prefers_raw_tool_output("json 是什么？") is False
    assert MintChatAgent._user_prefers_raw_tool_output("解释一下 JSON 格式是什么") is False
