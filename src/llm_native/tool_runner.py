from __future__ import annotations

import json
import time
from dataclasses import dataclass
from threading import Event
from typing import Any, Protocol, Sequence

from src.utils.tool_context import tool_trace_recorder_var

from .events import ToolCallState
from .messages import Message


class ToolExecutor(Protocol):
    def execute_tool(self, name: str, timeout: float, **kwargs: Any) -> str:
        raise NotImplementedError


def _parse_tool_arguments(arguments_json: str) -> dict[str, Any]:
    raw = str(arguments_json or "").strip()
    if not raw:
        return {}

    parsed = json.loads(raw)
    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        raise ValueError("tool arguments must be a JSON object")
    return parsed


@dataclass(slots=True)
class ToolRunner:
    """
    Execute OpenAI-compatible tool calls using the project's existing tool registry.

    Scope:
    - Best-effort JSON argument parsing (invalid args become tool error outputs).
    - Cancellation between tool calls.
    - Per-tool timeout passed through to the executor.
    """

    tool_executor: ToolExecutor
    default_timeout_s: float = 30.0

    def run(
        self,
        calls: Sequence[ToolCallState],
        *,
        cancel_event: Event | None = None,
        timeout_s: float | None = None,
    ) -> list[Message]:
        results: list[Message] = []
        effective_timeout = (
            float(timeout_s) if timeout_s is not None else float(self.default_timeout_s)
        )

        for call in calls:
            if cancel_event and cancel_event.is_set():
                break

            if not call.tool_call_id or not call.name:
                # Without tool_call_id we cannot construct a tool message. Fail fast.
                raise ValueError(
                    "incomplete tool call: "
                    f"index={call.index} id={call.tool_call_id} name={call.name}"
                )

            recorder = tool_trace_recorder_var.get(None)
            started_at = None
            if recorder is not None:
                try:
                    started_at = float(time.perf_counter())
                    recorder.mark_start()
                except Exception:
                    recorder = None
                    started_at = None

            trace_args: dict[str, Any] = {}
            tool_error = ""
            output = ""
            try:
                try:
                    kwargs = _parse_tool_arguments(call.arguments_json)
                    trace_args = dict(kwargs or {})
                except Exception as exc:
                    tool_error = f"工具参数解析失败: {type(exc).__name__}: {exc}"
                    output = tool_error
                else:
                    output = self.tool_executor.execute_tool(
                        call.name, timeout=effective_timeout, **kwargs
                    )
            except Exception as exc:
                tool_error = f"工具执行失败: {type(exc).__name__}: {exc}"
                output = tool_error
            finally:
                if recorder is not None and started_at is not None:
                    try:
                        recorder.record_end(
                            str(call.name),
                            trace_args,
                            started_at=float(started_at),
                            output=str(output) if not tool_error else "",
                            error=str(tool_error),
                        )
                    except Exception:
                        pass

            results.append(
                Message(
                    role="tool",
                    content=str(output),
                    tool_call_id=str(call.tool_call_id),
                    name=str(call.name),
                )
            )

        return results
