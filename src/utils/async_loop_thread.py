"""
通用后台事件循环线程。

用途：
- 在同步/多线程环境中安全复用同一个 asyncio event loop
- 支持在任意线程提交 coroutine 并等待结果（run_coroutine_threadsafe）

注意：
- 该类适合“少量长连接/大量短任务”的场景（aiohttp 连接池、MCP 会话等）
- 退出时应显式调用 close()，以便取消未完成任务并关闭 event loop
"""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import Future, TimeoutError as FuturesTimeoutError
from typing import Any, Coroutine, Optional, TypeVar

from src.utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class AsyncLoopThread:
    """后台 event loop 线程（惰性启动）。"""

    def __init__(
        self,
        *,
        thread_name: str = "mintchat-async-loop",
        start_timeout_s: float = 5.0,
    ) -> None:
        self._thread_name = thread_name
        self._start_timeout_s = max(0.1, float(start_timeout_s))

        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._closing = False

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        with self._lock:
            self._loop = loop
            self._ready.set()

        try:
            loop.run_forever()
        except Exception as exc:  # pragma: no cover - 极少发生
            logger.error("AsyncLoopThread 运行异常退出: %s", exc)
        finally:
            try:
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                pass
            finally:
                try:
                    loop.close()
                except Exception:
                    pass

    def _ensure_started(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._closing:
                raise RuntimeError("AsyncLoopThread 已关闭，无法提交任务")

            loop = self._loop
            thread = self._thread
            if loop is not None and thread is not None and thread.is_alive() and not loop.is_closed():
                return loop

            self._ready.clear()
            self._loop = None
            self._thread = threading.Thread(
                target=self._thread_main,
                name=self._thread_name,
                daemon=True,
            )
            self._thread.start()

        if not self._ready.wait(timeout=self._start_timeout_s):
            raise TimeoutError("AsyncLoopThread 启动超时")

        with self._lock:
            loop = self._loop
            if loop is None:
                raise RuntimeError("AsyncLoopThread 启动失败：loop 未就绪")
            return loop

    def submit(self, coro: Coroutine[Any, Any, T]) -> Future[T]:
        """提交 coroutine 到后台 loop（线程安全）。"""
        loop = self._ensure_started()
        return asyncio.run_coroutine_threadsafe(coro, loop)

    def run(self, coro: Coroutine[Any, Any, T], *, timeout: Optional[float] = None) -> T:
        """提交 coroutine 并等待结果。"""
        future = self.submit(coro)
        try:
            return future.result(timeout=timeout)
        except FuturesTimeoutError:
            future.cancel()
            raise

    def call_soon_threadsafe(self, callback, *args: Any) -> None:
        """在 loop 线程调度一个同步回调。"""
        loop = self._ensure_started()
        loop.call_soon_threadsafe(callback, *args)

    def close(self, *, timeout: float = 3.0) -> None:
        """停止 event loop 并关闭线程（幂等）。"""
        with self._lock:
            if self._closing:
                return
            self._closing = True
            loop = self._loop
            thread = self._thread

        if loop is None or thread is None:
            return

        try:
            if not loop.is_closed():
                loop.call_soon_threadsafe(loop.stop)
        except Exception:
            pass

        try:
            thread.join(timeout=max(0.0, float(timeout)))
        except Exception:
            pass
