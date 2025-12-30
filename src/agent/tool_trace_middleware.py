"""
Tool-call tracing + output truncation middleware.

Why this exists:
- MintChat needs a reliable tool-call trace for empty-reply/timeout rescue paths.
- LangGraph ToolNode expects tools to return `ToolMessage`/`Command`.
  Do NOT monkey-patch tool.invoke to return `str`, otherwise ToolNode will error.
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Optional

try:
    from langchain.agents.middleware import AgentMiddleware
except Exception:  # pragma: no cover - older langchain
    AgentMiddleware = object  # type: ignore[misc,assignment]

from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from src.utils.tool_context import tool_trace_recorder_var


class ToolTraceMiddleware(AgentMiddleware):
    """Record tool calls into `ToolTraceRecorder` and truncate verbose tool outputs."""

    name = "mintchat-tool-trace"

    def __init__(self, *, max_output_chars: int = 12_000):
        self._max_output_chars = int(max_output_chars)

    @staticmethod
    def _content_to_text(content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text") or item.get("content")
                    if isinstance(text, str) and text:
                        parts.append(text)
                    else:
                        try:
                            parts.append(json.dumps(item, ensure_ascii=False))
                        except Exception:
                            parts.append(str(item))
                else:
                    parts.append(str(item))
            return "".join(parts)
        return str(content)

    def _truncate_text(self, text: str) -> str:
        max_chars = int(self._max_output_chars)
        if max_chars <= 0:
            return text
        text = str(text or "")
        if len(text) <= max_chars:
            return text
        suffix = f"\n\n[...工具输出已截断：原始 {len(text)} 字符，阈值 {max_chars} 字符]"
        keep = max(0, max_chars - len(suffix))
        if keep <= 0:
            return suffix.strip()
        return text[:keep] + suffix

    def _truncate_tool_message(self, msg: ToolMessage) -> None:
        try:
            content_text = self._content_to_text(getattr(msg, "content", ""))
            truncated = self._truncate_text(content_text)
            if truncated != content_text:
                msg.content = truncated
        except Exception:
            # Tool messages are best-effort; never block execution.
            return

    def _record_result(
        self,
        *,
        recorder: Any,
        request: ToolCallRequest,
        started_at: float,
        response: ToolMessage | Command | None,
        exc: Optional[BaseException] = None,
    ) -> None:
        if recorder is None:
            return
        tool_call = getattr(request, "tool_call", None) or {}
        name = str(tool_call.get("name") or "")
        args = tool_call.get("args") if isinstance(tool_call, dict) else {}
        if not isinstance(args, dict):
            args = {}

        try:
            if exc is not None or response is None:
                recorder.record_end(
                    name,
                    args,
                    started_at=started_at,
                    error=str(exc) or repr(exc),
                )
                return

            if isinstance(response, ToolMessage):
                status = getattr(response, "status", None)
                text = self._content_to_text(getattr(response, "content", ""))
                if status == "error":
                    recorder.record_end(name, args, started_at=started_at, error=text)
                else:
                    recorder.record_end(name, args, started_at=started_at, output=text)
                return

            recorder.record_end(name, args, started_at=started_at, output=str(response))
        except Exception:
            # Recorder is optional telemetry; never fail tool execution due to tracing.
            return

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        recorder = tool_trace_recorder_var.get(None)
        started_at = time.perf_counter()
        if recorder is not None:
            try:
                recorder.mark_start()
            except Exception:
                recorder = None
        try:
            response = handler(request)
        except Exception as exc:
            self._record_result(
                recorder=recorder, request=request, started_at=started_at, response=None, exc=exc
            )
            raise

        if isinstance(response, ToolMessage):
            self._truncate_tool_message(response)
        self._record_result(
            recorder=recorder, request=request, started_at=started_at, response=response
        )
        return response

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Any],
    ) -> ToolMessage | Command:
        recorder = tool_trace_recorder_var.get(None)
        started_at = time.perf_counter()
        if recorder is not None:
            try:
                recorder.mark_start()
            except Exception:
                recorder = None
        try:
            response = await handler(request)
        except Exception as exc:
            self._record_result(
                recorder=recorder, request=request, started_at=started_at, response=None, exc=exc
            )
            raise

        if isinstance(response, ToolMessage):
            self._truncate_tool_message(response)
        self._record_result(
            recorder=recorder, request=request, started_at=started_at, response=response
        )
        return response
