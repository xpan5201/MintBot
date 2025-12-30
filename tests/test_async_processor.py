from __future__ import annotations

import asyncio
import threading
from concurrent.futures import Future as ConcurrentFuture

from src.agent.performance_optimizer import AsyncProcessor
from src.utils.async_manager import AsyncTaskManager


async def _async_add_one(x: int) -> int:
    await asyncio.sleep(0.01)
    return x + 1


async def _async_thread_name() -> str:
    await asyncio.sleep(0.01)
    return threading.current_thread().name


def test_async_processor_executes_coroutines_in_loop_thread():
    processor = AsyncProcessor(max_workers=1)
    try:
        fut = processor.submit(_async_thread_name)
        thread_name = fut.result(timeout=2.0)
        assert "mintchat-async-processor" in thread_name
    finally:
        processor.close()


def test_async_processor_executes_sync_functions_in_thread_pool():
    processor = AsyncProcessor(max_workers=1)

    def _sync_thread_name() -> str:
        return threading.current_thread().name

    try:
        fut = processor.submit(_sync_thread_name)
        thread_name = fut.result(timeout=2.0)
        assert thread_name.startswith("mintchat-async")
        assert "mintchat-async-processor" not in thread_name
    finally:
        processor.close()


def test_async_task_manager_create_task_runs_without_running_loop():
    manager = AsyncTaskManager(max_workers=1)
    try:
        future = manager.create_task(_async_add_one(1))
        assert isinstance(future, ConcurrentFuture)
        assert future.result(timeout=2.0) == 2
    finally:
        manager.shutdown(wait=False)


def test_async_task_manager_run_sync_works_inside_running_loop():
    manager = AsyncTaskManager(max_workers=1)

    async def _main() -> int:
        return manager.run_sync(_async_add_one(1), timeout=2.0)

    try:
        assert asyncio.run(_main()) == 2
    finally:
        manager.shutdown(wait=False)
