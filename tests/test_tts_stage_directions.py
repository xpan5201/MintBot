from __future__ import annotations

from src.agent.core import MintChatAgent
from src.multimodal.tts_text import strip_stage_directions


def test_strip_stage_directions_removes_fullwidth_parentheses() -> None:
    assert strip_stage_directions("你好（微笑）主人！") == "你好主人！"


def test_strip_stage_directions_removes_ascii_parentheses() -> None:
    assert strip_stage_directions("Hello (smile) world") == "Hello  world"


def test_strip_stage_directions_keeps_unmatched_parentheses() -> None:
    assert strip_stage_directions("你好（微笑") == "你好（微笑"


def test_extract_tool_stream_text_reads_tool_dict() -> None:
    agent = MintChatAgent.__new__(MintChatAgent)
    assert agent._extract_tool_stream_text({"role": "tool", "content": "RESULT"}) == "RESULT"

