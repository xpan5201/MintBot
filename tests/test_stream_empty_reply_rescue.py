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

    def stream_llm(_messages: list, *, cancel_event=None) -> Iterator[str]:
        if False:  # pragma: no cover
            yield ""
        return iter(())

    def filter_tool_info(_text: object) -> str:
        return ""

    def rescue_empty_reply(*_args, **_kwargs) -> str:
        return "rescued"

    saved: dict[str, str] = {}

    def post_actions(_save_message: str, reply: str, _save_to_long_term: bool, *, stream: bool) -> None:
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

    def stream_llm(_messages: list, *, cancel_event=None) -> Iterator[str]:
        yield "X"

    def filter_tool_info(_text: object) -> str:
        return ""

    def rescue_empty_reply(*_args, **_kwargs) -> None:
        return None

    saved: dict[str, str] = {}

    def post_actions(_save_message: str, reply: str, _save_to_long_term: bool, *, stream: bool) -> None:
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
