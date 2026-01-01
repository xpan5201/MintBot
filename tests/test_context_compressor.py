from __future__ import annotations

import copy

from src.agent.context_compressor import ContextCompressor


def test_compress_context_does_not_mutate_input_messages() -> None:
    compressor = ContextCompressor(max_tokens=10)
    messages = [
        {"role": "user", "content": "你好！！！"},
        {"role": "assistant", "content": "喵喵喵喵喵~"},
        {"role": "user", "content": "这里    有  多个   空格"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "必须  记住"},
        {"role": "assistant", "content": "好的"},
        {"role": "user", "content": "再来一条"},
        {"role": "assistant", "content": "收到"},
    ]
    original = copy.deepcopy(messages)

    compressor.compress_context(messages, additional_context="附加上下文~~~")

    assert messages == original


def test_remove_redundancy_preserves_code_fences() -> None:
    text = "你好！！！\n```python\n    print('hi')  \n```\n喵喵喵喵喵~"
    out = ContextCompressor.remove_redundancy(text)
    assert "你好！" in out
    assert "喵~" in out
    assert "```python" in out
    assert "    print('hi')  " in out


def test_extract_key_info_limits_important_messages() -> None:
    compressor = ContextCompressor()
    messages = [{"role": "user", "content": f"重要 {i}"} for i in range(40)]

    extracted = compressor.extract_key_info(messages, keep_recent=6, max_important=12)
    assert [m["content"] for m in extracted] == [f"重要 {i}" for i in range(22, 40)]

    extracted_no_important = compressor.extract_key_info(messages, keep_recent=6, max_important=0)
    assert [m["content"] for m in extracted_no_important] == [f"重要 {i}" for i in range(34, 40)]


def test_aggressive_compress_keeps_last_two_turns() -> None:
    compressor = ContextCompressor(max_tokens=1)
    messages = [{"role": "user", "content": f"消息 {i}"} for i in range(10)]

    compressed_messages, _ = compressor.compress_context(messages)

    assert [m["content"] for m in compressed_messages] == [f"消息 {i}" for i in range(6, 10)]


def test_max_tokens_zero_disables_aggressive_compress() -> None:
    compressor = ContextCompressor(max_tokens=0)
    messages = [{"role": "user", "content": f"消息 {i}"} for i in range(10)]

    compressed_messages, _ = compressor.compress_context(messages)

    assert [m["content"] for m in compressed_messages] == [f"消息 {i}" for i in range(4, 10)]
