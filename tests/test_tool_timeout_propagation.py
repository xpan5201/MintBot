from __future__ import annotations

import asyncio
import threading

from src.agent import builtin_tools
from src.agent.tools import ToolRegistry


def test_execute_tool_propagates_timeout_to_async_runtime_and_cancels():
    registry = ToolRegistry()
    cancelled = threading.Event()

    @builtin_tools.async_to_sync
    async def slow_tool() -> str:
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return "done"

    registry.register_tool("slow_async", slow_tool)
    try:
        result = registry.execute_tool("slow_async", timeout=0.2)
        assert "超时" in result
        assert cancelled.wait(timeout=1.0)
    finally:
        registry.close()
