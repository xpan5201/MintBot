from __future__ import annotations

from typing import Iterator

from src.agent.core import AgentConversationBundle, MintChatAgent


def test_chat_stream_falls_back_on_connection_error() -> None:
    agent = MintChatAgent.__new__(MintChatAgent)
    agent.enable_streaming = True

    bundle = AgentConversationBundle(
        messages=[{"role": "user", "content": "hi"}],
        save_message="hi",
        original_message="hi",
        processed_message="hi",
    )

    def build_bundle(*_args, **_kwargs) -> AgentConversationBundle:
        return bundle

    def stream_llm(_messages: list, *, tool_recorder=None, cancel_event=None) -> Iterator[str]:
        raise RuntimeError("Connection error.")

    def invoke_failover(_bundle: AgentConversationBundle, *, timeout_s=None):  # noqa: ANN001
        return {"content": "fallback"}

    def extract_reply(_resp: object) -> str:
        return "fallback-reply"

    def filter_tool_info(text: object) -> str:
        return str(text)

    def rescue_empty_reply(*_args, **_kwargs):  # noqa: ANN001
        return None

    saved: dict[str, str] = {}

    def post_actions(
        _save_message: str, reply: str, _save_to_long_term: bool, *, stream: bool
    ) -> None:
        assert stream is True
        saved["reply"] = reply

    agent._build_agent_bundle = build_bundle  # type: ignore[assignment]
    agent._stream_llm_response = stream_llm  # type: ignore[assignment]
    agent._invoke_with_failover = invoke_failover  # type: ignore[assignment]
    agent._extract_reply_from_response = extract_reply  # type: ignore[assignment]
    agent._filter_tool_info = filter_tool_info  # type: ignore[assignment]
    agent._rescue_empty_reply = rescue_empty_reply  # type: ignore[assignment]
    agent._post_reply_actions = post_actions  # type: ignore[assignment]

    chunks = list(agent.chat_stream("hi"))
    assert chunks == ["fallback-reply"]
    assert saved["reply"] == "fallback-reply"


def test_chat_stream_returns_user_friendly_message_when_failover_also_fails() -> None:
    agent = MintChatAgent.__new__(MintChatAgent)
    agent.enable_streaming = True

    bundle = AgentConversationBundle(
        messages=[{"role": "user", "content": "hi"}],
        save_message="hi",
        original_message="hi",
        processed_message="hi",
    )

    def build_bundle(*_args, **_kwargs) -> AgentConversationBundle:
        return bundle

    def stream_llm(_messages: list, *, tool_recorder=None, cancel_event=None) -> Iterator[str]:
        raise RuntimeError("Connection error.")

    def invoke_failover(_bundle: AgentConversationBundle, *, timeout_s=None):  # noqa: ANN001
        raise RuntimeError("Connection error.")

    def filter_tool_info(text: object) -> str:
        return str(text)

    def rescue_empty_reply(*_args, **_kwargs):  # noqa: ANN001
        return None

    saved: dict[str, str] = {}

    def post_actions(
        _save_message: str, reply: str, _save_to_long_term: bool, *, stream: bool
    ) -> None:
        assert stream is True
        saved["reply"] = reply

    agent._build_agent_bundle = build_bundle  # type: ignore[assignment]
    agent._stream_llm_response = stream_llm  # type: ignore[assignment]
    agent._invoke_with_failover = invoke_failover  # type: ignore[assignment]
    agent._filter_tool_info = filter_tool_info  # type: ignore[assignment]
    agent._rescue_empty_reply = rescue_empty_reply  # type: ignore[assignment]
    agent._post_reply_actions = post_actions  # type: ignore[assignment]

    chunks = list(agent.chat_stream("hi"))
    assert len(chunks) == 1
    assert "网络连接" in chunks[0]
    assert saved["reply"] == chunks[0]
