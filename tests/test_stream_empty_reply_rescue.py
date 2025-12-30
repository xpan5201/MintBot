from __future__ import annotations

from typing import Iterator

from src.agent.core import AgentConversationBundle, MintChatAgent


def test_chat_stream_uses_rescue_on_empty_reply() -> None:
    agent = MintChatAgent.__new__(MintChatAgent)

    bundle = AgentConversationBundle(
        messages=[{"role": "user", "content": "hi"}],
        save_message="hi",
        original_message="hi",
        processed_message="hi",
    )

    def build_bundle(*_args, **_kwargs) -> AgentConversationBundle:
        return bundle

    def stream_llm(_messages: list, *, tool_recorder=None, cancel_event=None) -> Iterator[str]:
        if False:  # pragma: no cover
            yield ""
        return iter(())

    def filter_tool_info(_text: object) -> str:
        return ""

    def rescue_empty_reply(*_args, **_kwargs) -> str:
        return "rescued"

    saved: dict[str, str] = {}

    def post_actions(
        _save_message: str, reply: str, _save_to_long_term: bool, *, stream: bool
    ) -> None:
        assert stream is True
        saved["reply"] = reply

    agent._build_agent_bundle = build_bundle  # type: ignore[assignment]
    agent._stream_llm_response = stream_llm  # type: ignore[assignment]
    agent._filter_tool_info = filter_tool_info  # type: ignore[assignment]
    agent._rescue_empty_reply = rescue_empty_reply  # type: ignore[assignment]
    agent._post_reply_actions = post_actions  # type: ignore[assignment]

    chunks = list(agent.chat_stream("hi"))
    assert chunks == ["rescued"]
    assert saved["reply"] == "rescued"


def test_chat_stream_does_not_append_default_when_filtered_empty_but_streamed() -> None:
    agent = MintChatAgent.__new__(MintChatAgent)

    bundle = AgentConversationBundle(
        messages=[{"role": "user", "content": "hi"}],
        save_message="hi",
        original_message="hi",
        processed_message="hi",
    )

    def build_bundle(*_args, **_kwargs) -> AgentConversationBundle:
        return bundle

    def stream_llm(_messages: list, *, tool_recorder=None, cancel_event=None) -> Iterator[str]:
        yield "X"

    def filter_tool_info(_text: object) -> str:
        return ""

    def rescue_empty_reply(*_args, **_kwargs) -> None:
        return None

    saved: dict[str, str] = {}

    def post_actions(
        _save_message: str, reply: str, _save_to_long_term: bool, *, stream: bool
    ) -> None:
        assert stream is True
        saved["reply"] = reply

    agent._build_agent_bundle = build_bundle  # type: ignore[assignment]
    agent._stream_llm_response = stream_llm  # type: ignore[assignment]
    agent._filter_tool_info = filter_tool_info  # type: ignore[assignment]
    agent._rescue_empty_reply = rescue_empty_reply  # type: ignore[assignment]
    agent._post_reply_actions = post_actions  # type: ignore[assignment]

    chunks = list(agent.chat_stream("hi"))
    assert chunks == ["X"]
    assert saved["reply"] == "X"


def test_rescue_empty_reply_prefers_image_analysis_without_retry() -> None:
    agent = MintChatAgent.__new__(MintChatAgent)
    agent._fast_retry_enabled = False  # should still return deterministic fallback

    def invoke_with_timeout(*_args, **_kwargs):  # pragma: no cover
        raise AssertionError("should not invoke LLM when image_analysis is available")

    agent._invoke_agent_with_timeout = invoke_with_timeout  # type: ignore[assignment]

    bundle = AgentConversationBundle(
        messages=[{"role": "user", "content": "hi"}],
        save_message="请帮我分析这张图片。",
        original_message="请帮我分析这张图片。",
        processed_message="请帮我分析这张图片。",
        image_analysis={"description": "A" * 2000, "text": "Hello"},
        image_path="C:/tmp/pic.png",
    )

    reply = agent._rescue_empty_reply(bundle, raw_reply="", source="stream")
    assert reply is not None
    assert "我看到的画面大概是" in reply
    assert "图片里识别到的文字" in reply
    assert "pic.png" in reply


def test_rescue_empty_reply_uses_tool_trace_fallback_without_retry() -> None:
    from time import perf_counter

    from src.utils.tool_context import ToolTraceRecorder

    agent = MintChatAgent.__new__(MintChatAgent)
    agent._fast_retry_enabled = False

    recorder = ToolTraceRecorder()
    recorder.mark_start()
    recorder.record_end("web_search", {"query": "x"}, started_at=perf_counter(), output="TOOL_OK")

    bundle = AgentConversationBundle(
        messages=[{"role": "user", "content": "hi"}],
        save_message="hi",
        original_message="hi",
        processed_message="hi",
        tool_recorder=recorder,
    )

    reply = agent._rescue_empty_reply(bundle, raw_reply="", source="stream")
    assert reply == "TOOL_OK"


def test_rescue_empty_reply_prefers_tool_trace_fallback_after_tool_call_parse() -> None:
    from src.utils.tool_context import ToolTraceRecorder

    agent = MintChatAgent.__new__(MintChatAgent)
    agent._fast_retry_enabled = True

    class DummyToolRegistry:
        def get_tool_names(self) -> list[str]:
            return ["get_current_time"]

        def execute_tool(self, name: str, **kwargs: object) -> str:
            assert name == "get_current_time"
            assert kwargs == {}
            return "RAW_TOOL_OUTPUT"

    agent.tool_registry = DummyToolRegistry()  # type: ignore[assignment]

    bundle = AgentConversationBundle(
        messages=[{"role": "user", "content": "hi"}],
        save_message="hi",
        original_message="hi",
        processed_message="hi",
        tool_recorder=ToolTraceRecorder(),
    )

    raw_reply = '{"tool_calls":[{"name":"get_current_time","arguments":{}}]}'
    reply = agent._rescue_empty_reply(bundle, raw_reply=raw_reply, source="stream")
    assert reply == "RAW_TOOL_OUTPUT"
    assert bundle.tool_recorder is not None
    assert bundle.tool_recorder.snapshot()


def test_chat_formats_when_reply_echoes_tool_output() -> None:
    from time import perf_counter

    from src.utils.tool_context import ToolTraceRecorder

    agent = MintChatAgent.__new__(MintChatAgent)

    recorder = ToolTraceRecorder()
    recorder.mark_start()
    recorder.record_end(
        "web_search",
        {"query": "x"},
        started_at=perf_counter(),
        output="TOOL_RESULT: web_search\nquery: x\nresults:\n1. a | https://example.com",
    )

    bundle = AgentConversationBundle(
        messages=[{"role": "user", "content": "hi"}],
        save_message="hi",
        original_message="hi",
        processed_message="hi",
        tool_recorder=recorder,
    )

    agent._build_agent_bundle = lambda *_a, **_k: bundle  # type: ignore[assignment]
    agent._invoke_with_failover = lambda *_a, **_k: object()  # type: ignore[assignment]
    agent._extract_reply_from_response = (
        lambda *_a, **_k: "TOOL_RESULT: web_search\nquery: x\nresults:\n1. a | https://example.com"
    )  # type: ignore[assignment]
    agent._rescue_empty_reply = lambda *_a, **_k: None  # type: ignore[assignment]
    agent._post_reply_actions = lambda *_a, **_k: None  # type: ignore[assignment]

    reply = agent.chat("hi")
    assert "example.com" in reply
    assert "搜到" in reply


def test_chat_stream_appends_fallback_when_reply_echoes_tool_output() -> None:
    from time import perf_counter

    from src.utils.tool_context import ToolTraceRecorder

    agent = MintChatAgent.__new__(MintChatAgent)

    recorder = ToolTraceRecorder()
    recorder.mark_start()
    recorder.record_end(
        "web_search",
        {"query": "x"},
        started_at=perf_counter(),
        output="TOOL_RESULT: web_search\nquery: x\nresults:\n1. a | https://example.com",
    )

    bundle = AgentConversationBundle(
        messages=[{"role": "user", "content": "hi"}],
        save_message="hi",
        original_message="hi",
        processed_message="hi",
        tool_recorder=recorder,
    )

    agent._build_agent_bundle = lambda *_a, **_k: bundle  # type: ignore[assignment]

    def stream_llm(*_args, **_kwargs) -> Iterator[str]:
        yield "TOOL_RESULT: web_search\nquery: x\nresults:\n1. a | https://example.com"

    agent._stream_llm_response = stream_llm  # type: ignore[assignment]
    agent._filter_tool_info = lambda text: str(text)  # type: ignore[assignment]
    agent._rescue_empty_reply = lambda *_a, **_k: None  # type: ignore[assignment]
    agent._post_reply_actions = lambda *_a, **_k: None  # type: ignore[assignment]

    chunks = list(agent.chat_stream("hi"))
    assert chunks[0] == "TOOL_RESULT: web_search\nquery: x\nresults:\n1. a | https://example.com"
    assert len(chunks) == 2
    assert chunks[1].startswith("\n\n")
    assert "example.com" in chunks[1]


def test_chat_stream_runs_rescue_when_reply_not_meaningful() -> None:
    agent = MintChatAgent.__new__(MintChatAgent)

    bundle = AgentConversationBundle(
        messages=[{"role": "user", "content": "hi"}],
        save_message="hi",
        original_message="hi",
        processed_message="hi",
    )

    def build_bundle(*_args, **_kwargs) -> AgentConversationBundle:
        return bundle

    def stream_llm(_messages: list, *, tool_recorder=None, cancel_event=None) -> Iterator[str]:
        yield "{"

    def filter_tool_info(_text: object) -> str:
        return "{"

    def rescue_empty_reply(*_args, **_kwargs) -> str:
        return "rescued"

    agent._build_agent_bundle = build_bundle  # type: ignore[assignment]
    agent._stream_llm_response = stream_llm  # type: ignore[assignment]
    agent._filter_tool_info = filter_tool_info  # type: ignore[assignment]
    agent._rescue_empty_reply = rescue_empty_reply  # type: ignore[assignment]
    agent._post_reply_actions = lambda *_args, **_kwargs: None  # type: ignore[assignment]

    chunks = list(agent.chat_stream("hi"))
    assert chunks == ["{", "rescued"]
