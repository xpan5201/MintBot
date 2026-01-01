from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Iterator

from src.agent.core import LLMTimeouts, MintChatAgent


def test_stream_llm_response_skips_non_messages_stream_modes() -> None:
    agent = MintChatAgent.__new__(MintChatAgent)
    agent._llm_timeouts = LLMTimeouts(  # type: ignore[attr-defined]
        first_chunk=1.0,
        idle_chunk=1.0,
        total=5.0,
    )
    agent._stream_min_chars = 1  # type: ignore[attr-defined]

    class DummyAgent:
        def stream(self, _inputs: Any, *, stream_mode: str = "messages") -> Iterator[Any]:
            assert stream_mode == "messages"
            # Simulate LangGraph multi-mode payloads that might show up on some gateways.
            yield ("updates", {"foo": 1})
            yield ("messages", ({"role": "assistant", "content": "hi"}, {"langgraph_node": "llm"}))

    agent.agent = DummyAgent()  # type: ignore[attr-defined]

    executor = ThreadPoolExecutor(max_workers=1)
    agent._stream_executor = executor  # type: ignore[attr-defined]
    try:
        out = list(agent._stream_llm_response([{"role": "user", "content": "x"}]))
    finally:
        executor.shutdown(wait=True, cancel_futures=True)

    assert out == ["hi"]
