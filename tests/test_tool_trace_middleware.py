from __future__ import annotations

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.prebuilt.tool_node import ToolNode
from langgraph.runtime import Runtime

from src.agent.tool_trace_middleware import ToolTraceMiddleware
from src.utils.tool_context import ToolTraceRecorder, tool_trace_recorder_var


def test_tool_trace_middleware_preserves_toolmessage_and_records_trace() -> None:
    recorder = ToolTraceRecorder(max_traces=5, max_text_chars=500)
    token = tool_trace_recorder_var.set(recorder)
    try:

        @tool
        def echo(text: str) -> str:
            """Echo text with padding (test helper)."""
            return ("x" * 200) + text

        middleware = ToolTraceMiddleware(max_output_chars=64)
        node = ToolNode([echo], wrap_tool_call=middleware.wrap_tool_call)

        result = node.invoke(
            [
                {
                    "name": echo.name,
                    "args": {"text": "hi"},
                    "id": "call-1",
                    "type": "tool_call",
                }
            ],
            runtime=Runtime(),
        )

        if isinstance(result, dict):
            messages = result.get("messages")
        else:
            messages = result

        assert isinstance(messages, list)
        assert messages and isinstance(messages[0], ToolMessage)
        assert isinstance(messages[0].content, str)
        assert len(messages[0].content) <= 64 + 80  # allow suffix text

        traces = recorder.snapshot()
        assert traces
        last = traces[-1]
        assert last.name == echo.name
        assert last.args.get("text") == "hi"
        assert last.output
    finally:
        tool_trace_recorder_var.reset(token)
