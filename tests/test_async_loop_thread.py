from __future__ import annotations

import asyncio
import threading
from concurrent.futures import TimeoutError as FuturesTimeoutError

import pytest

from src.utils.async_loop_thread import AsyncLoopThread


async def _async_echo(value: int) -> int:
    await asyncio.sleep(0.01)
    return value


def test_async_loop_thread_runs_coroutines():
    runner = AsyncLoopThread(thread_name="pytest-async-loop")
    try:
        assert runner.run(_async_echo(42), timeout=2.0) == 42
    finally:
        runner.close()


def test_async_loop_thread_is_threadsafe_for_submit():
    runner = AsyncLoopThread(thread_name="pytest-async-loop-threadsafe")
    results: list[int] = []
    results_lock = threading.Lock()

    def worker(i: int) -> None:
        value = runner.run(_async_echo(i), timeout=2.0)
        with results_lock:
            results.append(value)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=2.0)
        assert sorted(results) == list(range(10))
    finally:
        runner.close()


def test_async_loop_thread_run_timeout_requests_cancellation():
    runner = AsyncLoopThread(thread_name="pytest-async-loop-timeout")
    cancelled = threading.Event()

    async def sleeper() -> None:
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    try:
        with pytest.raises(FuturesTimeoutError):
            runner.run(sleeper(), timeout=0.01)
        assert cancelled.wait(timeout=1.0)
    finally:
        runner.close()


def test_builtin_tools_async_to_sync_is_threadsafe():
    from src.agent import builtin_tools

    @builtin_tools.async_to_sync
    async def _async_add_one(x: int) -> int:
        await asyncio.sleep(0.01)
        return x + 1

    results: list[int] = []
    results_lock = threading.Lock()

    def worker(i: int) -> None:
        value = _async_add_one(i)
        with results_lock:
            results.append(value)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=2.0)
        assert sorted(results) == [i + 1 for i in range(10)]
    finally:
        builtin_tools.shutdown_builtin_tools_runtime()
