from __future__ import annotations

from src.agent.core import MintChatAgent


def test_filter_tool_info_keeps_standalone_json_list_of_strings() -> None:
    raw = '["a_b","c_d"]'
    assert MintChatAgent._filter_tool_info(raw) == raw
