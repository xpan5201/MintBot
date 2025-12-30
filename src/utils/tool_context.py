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
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Dict, List, Optional

tool_timeout_s_var: contextvars.ContextVar[Optional[float]] = contextvars.ContextVar(
    "mintchat_tool_timeout_s",
    default=None,
)

tool_trace_recorder_var: contextvars.ContextVar[Optional["ToolTraceRecorder"]] = (
    contextvars.ContextVar("mintchat_tool_trace_recorder", default=None)
)


@dataclass(slots=True)
class ToolCallTrace:
    name: str
    args: Dict[str, Any]
    output: str
    error: str
    started_at: float
    ended_at: float

    @property
    def duration_s(self) -> float:
        return max(0.0, float(self.ended_at) - float(self.started_at))


@dataclass(slots=True)
class ToolTraceRecorder:
    """
    记录本轮对话中的工具调用轨迹，用于：
    - 流式“无输出超时/空回复”时作为兜底文本
    - 看门狗在工具执行期间保持活跃，避免误判超时

    注意：
    - recorder 会通过 contextvar 传递给工具调用线程/协程
    - 内部使用锁，支持跨线程安全读写
    """

    max_traces: int = 20
    max_text_chars: int = 4000
    _lock: Lock = field(default_factory=Lock, repr=False)
    traces: List[ToolCallTrace] = field(default_factory=list)
    in_flight: int = 0
    first_completed_at: Optional[float] = None
    last_activity_at: float = field(default_factory=time.perf_counter)

    def _clip(self, text: str) -> str:
        text = str(text or "")
        max_chars = int(self.max_text_chars)
        if max_chars <= 0 or len(text) <= max_chars:
            return text
        suffix = f"…[截断 {len(text)}→{max_chars}]"
        keep = max(0, max_chars - len(suffix))
        if keep <= 0:
            return suffix
        return text[:keep].rstrip() + suffix

    def mark_start(self) -> None:
        now = time.perf_counter()
        with self._lock:
            self.in_flight += 1
            self.last_activity_at = now

    def record_end(
        self,
        name: str,
        args: Dict[str, Any],
        *,
        started_at: float,
        output: str = "",
        error: str = "",
    ) -> None:
        ended_at = time.perf_counter()
        trace = ToolCallTrace(
            name=str(name or ""),
            args=dict(args or {}),
            output=self._clip(output),
            error=self._clip(error),
            started_at=float(started_at or ended_at),
            ended_at=float(ended_at),
        )
        with self._lock:
            if self.in_flight > 0:
                self.in_flight -= 1
            self.last_activity_at = ended_at
            if self.first_completed_at is None:
                self.first_completed_at = ended_at
            self.traces.append(trace)
            if self.max_traces > 0 and len(self.traces) > self.max_traces:
                self.traces = self.traces[-self.max_traces :]

    def snapshot(self) -> List[ToolCallTrace]:
        with self._lock:
            return list(self.traces)

    def state(self) -> tuple[int, Optional[float], float]:
        with self._lock:
            return int(self.in_flight), self.first_completed_at, float(self.last_activity_at)


def get_current_tool_timeout_s() -> Optional[float]:
    value = tool_timeout_s_var.get()
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None
