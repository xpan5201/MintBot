from __future__ import annotations

from threading import Event

import pytest

from src.agent.core import AgentConversationBundle, AgentTimeoutError, MintChatAgent


@pytest.mark.anyio
async def test_chat_stream_async_uses_non_streaming_path_when_streaming_disabled() -> None:
    agent = MintChatAgent.__new__(MintChatAgent)
    agent.enable_streaming = False  # type: ignore[attr-defined]

    bundle = AgentConversationBundle(
        messages=[{"role": "user", "content": "hi"}],
        save_message="hi",
        original_message="hi",
        processed_message="hi",
    )

    async def build_bundle(*_args, **_kwargs) -> AgentConversationBundle:
        return bundle

    async def invoke(_bundle: AgentConversationBundle, *, timeout_s=None):  # noqa: ANN001
        return object()

    calls: list[bool] = []

    def post_actions(_msg: str, _reply: str, _save: bool, *, stream: bool) -> None:
        calls.append(stream)

    agent._build_agent_bundle_async = build_bundle  # type: ignore[assignment]
    agent._ainvoke_with_failover = invoke  # type: ignore[assignment]
    agent._extract_reply_from_response = lambda _resp: "OK"  # type: ignore[assignment]
    agent._filter_tool_info = lambda text: str(text)  # type: ignore[assignment]
    agent._post_reply_actions = post_actions  # type: ignore[assignment]

    out: list[str] = []
    async for chunk in agent.chat_stream_async("hi", cancel_event=Event()):
        out.append(chunk)

    assert out == ["OK"]
    assert calls == [False]


@pytest.mark.anyio
async def test_chat_stream_async_timeout_triggers_failover_when_no_output() -> None:
    agent = MintChatAgent.__new__(MintChatAgent)
    agent.enable_streaming = True  # type: ignore[attr-defined]
    agent._stream_failure_count = 0  # type: ignore[attr-defined]

    bundle = AgentConversationBundle(
        messages=[{"role": "user", "content": "hi"}],
        save_message="hi",
        original_message="hi",
        processed_message="hi",
    )

    async def build_bundle(*_args, **_kwargs) -> AgentConversationBundle:
        return bundle

    async def stream_llm(_messages: list, *, tool_recorder=None, cancel_event=None):
        raise AgentTimeoutError("timeout")
        if False:  # pragma: no cover
            yield ""  # type: ignore[misc]

    async def invoke(_bundle: AgentConversationBundle, *, timeout_s=None):  # noqa: ANN001
        return object()

    calls: list[bool] = []

    def post_actions(_msg: str, _reply: str, _save: bool, *, stream: bool) -> None:
        calls.append(stream)

    agent._build_agent_bundle_async = build_bundle  # type: ignore[assignment]
    agent._astream_llm_response = stream_llm  # type: ignore[assignment]
    agent._ainvoke_with_failover = invoke  # type: ignore[assignment]
    agent._extract_reply_from_response = lambda _resp: "OK"  # type: ignore[assignment]
    agent._filter_tool_info = lambda text: str(text)  # type: ignore[assignment]
    agent._post_reply_actions = post_actions  # type: ignore[assignment]

    out: list[str] = []
    async for chunk in agent.chat_stream_async("hi", cancel_event=Event()):
        out.append(chunk)

    assert out == ["OK"]
    assert calls == [True]
