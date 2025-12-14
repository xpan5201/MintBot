"""
工具执行上下文（跨线程传递）。

用途：
- ToolRegistry 在调用线程池执行工具前写入 contextvar
- 工具实现（builtin_tools / MCP）读取 contextvar 来决定内部超时等行为

说明：
- contextvars 默认不跨线程传播；需要由提交线程池的一侧显式 copy_context()
"""

from __future__ import annotations

import contextvars
from typing import Optional

tool_timeout_s_var: contextvars.ContextVar[Optional[float]] = contextvars.ContextVar(
    "mintchat_tool_timeout_s",
    default=None,
)


def get_current_tool_timeout_s() -> Optional[float]:
    value = tool_timeout_s_var.get()
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None

