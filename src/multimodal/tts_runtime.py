"""
TTS 后台异步运行时。

GUI 场景下经常在同步/线程池环境触发 TTS 合成：
- 如果每次都用 asyncio.run()，会反复创建/销毁 event loop，导致明显开销；
- 还会让 asyncio.Lock/Semaphore 绑定到不同 loop，引发潜在的 “bound to a different event loop” 错误；
- httpx AsyncClient 也无法复用连接池，进一步拖慢合成速度。

因此这里提供一个全局 AsyncLoopThread，用于统一在同一条后台 event loop 上执行 TTS 协程。
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Coroutine, Optional, TypeVar

from src.utils.async_loop_thread import AsyncLoopThread

_tts_runtime: Optional[AsyncLoopThread] = None
_tts_runtime_lock = threading.Lock()

T = TypeVar("T")


def get_tts_runtime() -> AsyncLoopThread:
    """获取（并惰性创建）TTS 后台事件循环线程。"""
    global _tts_runtime
    if _tts_runtime is not None:
        return _tts_runtime
    with _tts_runtime_lock:
        if _tts_runtime is None:
            _tts_runtime = AsyncLoopThread(thread_name="mintchat-tts")
    return _tts_runtime


async def run_in_tts_runtime(coro: Coroutine[Any, Any, T]) -> T:
    """将协程提交到 TTS 后台 loop 执行，并在当前 loop 中 await 结果。

    - 如果当前线程就是 TTS runtime 线程，则直接 await，避免死锁。
    - 否则通过 run_coroutine_threadsafe 提交，并使用 asyncio.wrap_future 等待结果。
    """
    runtime = get_tts_runtime()
    if threading.current_thread().name == "mintchat-tts":
        return await coro
    future = runtime.submit(coro)
    return await asyncio.wrap_future(future)


def shutdown_tts_runtime(timeout_s: float = 2.0) -> None:
    """显式关闭 TTS 后台事件循环线程（幂等）。"""
    global _tts_runtime
    runtime = _tts_runtime
    if runtime is None:
        return
    try:
        runtime.close(timeout=max(0.1, float(timeout_s)))
    except Exception:
        pass
    _tts_runtime = None
