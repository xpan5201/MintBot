from __future__ import annotations

import pytest

pytest.importorskip("langchain_core")

from langchain_core.messages import AIMessageChunk, ToolMessage  # noqa: E402

from src.agent.core import MintChatAgent  # noqa: E402


def test_extract_stream_text_allows_ai_message_chunk() -> None:
    agent = MintChatAgent.__new__(MintChatAgent)
    assert agent._extract_stream_text(AIMessageChunk(content="hi")) == "hi"


def test_extract_stream_text_skips_tool_message() -> None:
    agent = MintChatAgent.__new__(MintChatAgent)
    tool_msg = ToolMessage(content="tool output", tool_call_id="call_1")
    assert agent._extract_stream_text(tool_msg) == ""


def test_extract_reply_from_response_handles_dict_messages() -> None:
    agent = MintChatAgent.__new__(MintChatAgent)
    response = {
        "messages": [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
    }
    assert agent._extract_reply_from_response(response) == "hello"
