from __future__ import annotations

from src.agent.core import MintChatAgent, StreamStructuredPrefixStripper


def test_filter_tool_info_strips_structured_prefix_lists() -> None:
    raw = (
        '["general_chat"]}["emotion_analysis","affection_expression","personalized_advice","mindfulness_exercises"]}'
        "当然是真的喵！(认真地点点头)"
    )
    assert MintChatAgent._filter_tool_info(raw).startswith("当然是真的喵！")


def test_filter_tool_info_strips_tools_dict_prefix() -> None:
    raw = '{"tools":["calculator"]}当然是真的喵！'
    assert MintChatAgent._filter_tool_info(raw) == "当然是真的喵！"


def test_stream_prefix_stripper_strips_structured_prefix_across_chunks() -> None:
    stripper = StreamStructuredPrefixStripper()
    chunks = [
        '["general',
        '_chat"]}',
        '["emotion_analysis","affection_expression","personalized_advice","mindfulness_exercises"]}',
        "当然是真的喵！(认真地点点头)",
    ]
    output = "".join(stripper.process(chunk) for chunk in chunks) + stripper.flush()
    assert output.startswith("当然是真的喵！")
    assert "general_chat" not in output


def test_stream_prefix_stripper_allows_legit_json_reply() -> None:
    stripper = StreamStructuredPrefixStripper()
    chunks = ['{"answer": 1}', " 后续解释"]
    output = "".join(stripper.process(chunk) for chunk in chunks) + stripper.flush()
    assert output.startswith('{"answer": 1}')

