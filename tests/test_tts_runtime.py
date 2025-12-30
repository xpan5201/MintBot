from __future__ import annotations

import asyncio
import threading

from src.multimodal.tts_runtime import (
    get_tts_runtime,
    run_in_tts_runtime,
    shutdown_tts_runtime,
)


def test_run_in_tts_runtime_executes_on_runtime_thread() -> None:
    async def _main() -> str:
        async def _coro() -> str:
            return threading.current_thread().name

        return await run_in_tts_runtime(_coro())

    try:
        assert asyncio.run(_main()) == "mintchat-tts"
    finally:
        shutdown_tts_runtime(timeout_s=1.0)


def test_run_in_tts_runtime_is_safe_when_called_inside_runtime_thread() -> None:
    async def _inner() -> str:
        async def _coro() -> str:
            return threading.current_thread().name

        return await run_in_tts_runtime(_coro())

    runtime = get_tts_runtime()
    try:
        assert runtime.run(_inner(), timeout=2.0) == "mintchat-tts"
    finally:
        shutdown_tts_runtime(timeout_s=1.0)
