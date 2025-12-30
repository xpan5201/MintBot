from __future__ import annotations

from threading import Event
from typing import Iterator

from src.agent.core import AgentConversationBundle, MintChatAgent


def test_chat_stream_drains_iterator_on_cancel_event() -> None:
    agent = MintChatAgent.__new__(MintChatAgent)
    agent.enable_streaming = True  # type: ignore[attr-defined]

    bundle = AgentConversationBundle(
        messages=[{"role": "user", "content": "hi"}],
        save_message="hi",
        original_message="hi",
        processed_message="hi",
    )

    agent._build_agent_bundle = lambda *_a, **_k: bundle  # type: ignore[assignment]

    cleaned: dict[str, bool] = {"done": False}

    def stream_llm(_messages: list, *, tool_recorder=None, cancel_event=None) -> Iterator[str]:
        yield "A"
        if cancel_event is not None:
            cancel_event.set()
        try:
            yield "B"
            yield "C"
        finally:
            cleaned["done"] = True

    agent._stream_llm_response = stream_llm  # type: ignore[assignment]
    agent._filter_tool_info = lambda text: str(text)  # type: ignore[assignment]
    agent._post_reply_actions = (  # type: ignore[assignment]
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("should not persist on cancel"))
    )

    cancel_event = Event()
    chunks = list(agent.chat_stream("hi", cancel_event=cancel_event))

    assert chunks == ["A"]
    assert cleaned["done"] is True
