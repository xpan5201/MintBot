from __future__ import annotations

from src.agent.core import (
    MintChatAgent,
    StreamStructuredPrefixStripper,
    _metadata_looks_like_internal_routing,
)


def test_filter_tool_info_strips_structured_prefix_lists() -> None:
    raw = (
        '["general_chat"]}'
        '["emotion_analysis","affection_expression","personalized_advice",'
        '"mindfulness_exercises"]}'
        "当然是真的喵！(认真地点点头)"
    )
    assert MintChatAgent._filter_tool_info(raw).startswith("当然是真的喵！")


def test_filter_tool_info_strips_tools_dict_prefix() -> None:
    raw = '{"tools":["calculator"]}当然是真的喵！'
    assert MintChatAgent._filter_tool_info(raw) == "当然是真的喵！"


def test_filter_tool_info_strips_openai_tool_calls_prefix() -> None:
    raw = (
        '[{"id":"call_1","type":"function","function":{"name":"web_search","arguments":'
        '"{\\"query\\":\\"abc\\"}"}}]'
        "当然是真的喵！"
    )
    assert MintChatAgent._filter_tool_info(raw) == "当然是真的喵！"


def test_filter_tool_info_strips_embedded_route_tag_list() -> None:
    raw = '好的主人喵！\n["local_search","map_guide"]}\n我来帮您找附近的日式料理店喵！'
    assert MintChatAgent._filter_tool_info(raw) == "好的主人喵！\n我来帮您找附近的日式料理店喵！"


def test_filter_tool_info_strips_multiline_tools_json_block() -> None:
    raw = (
        "好的主人喵！\n{\n"
        '  "tools": ["search_restaurants",\n'
        '    "search_nearby"\n'
        "  ]\n"
        "}\n"
        "我找到了 3 家店喵！"
    )
    assert MintChatAgent._filter_tool_info(raw) == "好的主人喵！\n我找到了 3 家店喵！"


def test_filter_tool_info_does_not_drop_all_when_tools_json_is_invalid() -> None:
    # Some gateways might inject "\\n" literals inside JSON-like blocks, making it invalid JSON.
    raw = (
        "好的主人喵！\\n{\\n"
        '  "tools": ["search_restaurants",\\n'
        '    "search_nearby"\\n'
        "  ]\\n"
        "}\\n"
        "我找到了 3 家店喵！"
    )
    out = MintChatAgent._filter_tool_info(raw)
    assert "好的主人喵" in out
    assert "我找到了 3 家店喵" in out
    assert '"tools"' not in out


def test_stream_prefix_stripper_strips_structured_prefix_across_chunks() -> None:
    stripper = StreamStructuredPrefixStripper()
    chunks = [
        '["general',
        '_chat"]}',
        (
            '["emotion_analysis","affection_expression","personalized_advice",'
            '"mindfulness_exercises"]}'
        ),
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


def test_stream_prefix_stripper_strips_tool_prefix_after_whitespace() -> None:
    stripper = StreamStructuredPrefixStripper()
    chunks = ["\n  ", '{"tools":["calculator"]}', "当然是真的喵！"]
    output = "".join(stripper.process(chunk) for chunk in chunks) + stripper.flush()
    assert output.startswith("当然是真的喵！")
    assert "calculator" not in output


def test_stream_prefix_stripper_keeps_legit_json_after_whitespace() -> None:
    stripper = StreamStructuredPrefixStripper()
    chunks = ["\n  ", '{"answer": 1}', " 后续解释"]
    output = "".join(stripper.process(chunk) for chunk in chunks) + stripper.flush()
    assert '{"answer": 1}' in output


def test_stream_prefix_stripper_strips_toolselectionresponse_across_chunks() -> None:
    stripper = StreamStructuredPrefixStripper()
    chunks = [
        "ToolSelec",
        "tionResponse\n",
        '{"tools":["calculator"]}',
        "当然是真的喵！",
    ]
    output = "".join(stripper.process(chunk) for chunk in chunks) + stripper.flush()
    assert output.startswith("当然是真的喵！")
    assert "ToolSelectionResponse" not in output


def test_stream_prefix_stripper_drops_partial_toolselectionresponse_on_flush() -> None:
    stripper = StreamStructuredPrefixStripper()
    chunks = ["ToolSelec"]
    output = "".join(stripper.process(chunk) for chunk in chunks) + stripper.flush()
    assert output == ""


def test_stream_prefix_stripper_keeps_short_tools_prefix_on_flush() -> None:
    stripper = StreamStructuredPrefixStripper()
    chunks = ["tools"]
    output = "".join(stripper.process(chunk) for chunk in chunks) + stripper.flush()
    assert output == "tools"


def test_stream_prefix_stripper_drops_incomplete_tool_payload_on_flush() -> None:
    stripper = StreamStructuredPrefixStripper()
    chunks = ['{"tools":["calculator"']
    output = "".join(stripper.process(chunk) for chunk in chunks) + stripper.flush()
    assert output == ""


def test_stream_prefix_stripper_does_not_strip_normal_json_list() -> None:
    stripper = StreamStructuredPrefixStripper()
    chunks = ['[{"title":"a","link":"b","description":"c"}]']
    output = "".join(stripper.process(chunk) for chunk in chunks) + stripper.flush()
    assert output.startswith('[{"title":"a"')


def test_metadata_filter_detects_tool_selector_node() -> None:
    meta = {"langgraph_node": "tool_selector", "tags": ["internal", "ToolSelectionResponse"]}
    assert _metadata_looks_like_internal_routing(meta) is True


def test_metadata_filter_detects_routing_tags() -> None:
    meta = {"tags": ["routing", "some-other-tag"], "metadata": {"node": "Router"}}
    assert _metadata_looks_like_internal_routing(meta) is True


def test_metadata_filter_ignores_normal_metadata() -> None:
    meta = {"langgraph_node": "agent", "tags": ["assistant"], "metadata": {"run_name": "chat"}}
    assert _metadata_looks_like_internal_routing(meta) is False


def test_filter_tool_info_keeps_regular_code_block() -> None:
    raw = "看这里：\n```python\nprint('hello')\n```\n结束"
    out = MintChatAgent._filter_tool_info(raw)
    assert "```python" in out
    assert "print('hello')" in out
    assert out.endswith("结束")


def test_filter_tool_info_strips_tool_trace_code_block() -> None:
    raw = '好的主人喵！\n```json\n{"tools":["calculator"]}\n```\n我来继续回答~'
    out = MintChatAgent._filter_tool_info(raw)
    assert '"tools"' not in out
    assert "```" not in out
    assert out.startswith("好的主人喵！")
    assert out.endswith("我来继续回答~")


def test_filter_tool_info_keeps_legit_json_code_block() -> None:
    raw = '输出 JSON：\n```json\n{"answer": 1}\n```\n解释结束'
    out = MintChatAgent._filter_tool_info(raw)
    assert "```json" in out
    assert '{"answer": 1}' in out
