"""
TTS 文本清洗工具。

目标：只影响“朗读内容”，不影响 UI 中显示的原始文本。
"""

from __future__ import annotations

import re

_FULLWIDTH_PAREN_RE = re.compile(r"（[^）]{0,4000}）")
_ASCII_PAREN_RE = re.compile(r"\([^)]{0,4000}\)")


def strip_stage_directions(text: str) -> str:
    """移除括号内的动作/神态描写，避免推送给 TTS。

    说明：
    - 仅移除成对括号包裹的片段，避免流式/不完整片段导致大面积丢字；
    - 支持中文全角括号与半角括号；
    - 不做语义改写，仅做删除 + 轻微收尾清理。
    """
    if not text:
        return ""

    cleaned = str(text)
    # 多次迭代以覆盖类似 “（（...））” 的双层括号残留
    for _ in range(6):
        before = cleaned
        cleaned = _FULLWIDTH_PAREN_RE.sub("", cleaned)
        cleaned = _ASCII_PAREN_RE.sub("", cleaned)
        if cleaned == before:
            break

    # 去掉移除后遗留的空括号
    cleaned = cleaned.replace("（）", "").replace("()", "")
    return cleaned


__all__ = ["strip_stage_directions"]
