from __future__ import annotations

import pytest

from src.llm_native.messages import ImageURLPart, Message, TextPart, ToolCall, messages_from_openai


def test_message_to_openai_plain_text():
    msg = Message(role="user", content="hi")
    assert msg.to_openai() == {"role": "user", "content": "hi"}


def test_message_to_openai_content_parts():
    msg = Message(
        role="user",
        content=[
            TextPart("hello"),
            ImageURLPart(url="https://example.com/a.png", detail="low"),
        ],
    )
    payload = msg.to_openai()
    assert payload["role"] == "user"
    assert isinstance(payload["content"], list)
    assert payload["content"][0] == {"type": "text", "text": "hello"}
    assert payload["content"][1]["type"] == "image_url"
    assert payload["content"][1]["image_url"]["url"] == "https://example.com/a.png"
    assert payload["content"][1]["image_url"]["detail"] == "low"


def test_assistant_message_tool_calls():
    tc = ToolCall(id="call_1", name="get_weather", arguments_json='{"location":"Paris"}')
    msg = Message(role="assistant", content=None, tool_calls=[tc])
    payload = msg.to_openai()
    assert payload["role"] == "assistant"
    assert payload["content"] is None
    assert payload["tool_calls"][0]["id"] == "call_1"
    assert payload["tool_calls"][0]["function"]["name"] == "get_weather"


def test_tool_message_requires_tool_call_id():
    with pytest.raises(ValueError, match="requires tool_call_id"):
        Message(role="tool", content="ok")


def test_non_tool_message_rejects_tool_call_id():
    with pytest.raises(ValueError, match="only valid for tool messages"):
        Message(role="user", content="x", tool_call_id="call_1")


def test_messages_from_openai_roundtrip():
    payloads = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "hi"},
    ]
    msgs = messages_from_openai(payloads)
    assert [m.to_openai() for m in msgs] == payloads


def test_messages_from_openai_parses_tool_calls():
    payloads = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "calculator", "arguments": '{"expression":"1+1"}'},
                }
            ],
        }
    ]
    msgs = messages_from_openai(payloads)
    assert msgs[0].role == "assistant"
    assert msgs[0].tool_calls and msgs[0].tool_calls[0].id == "call_1"
