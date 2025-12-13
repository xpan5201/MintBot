"""
异步任务管理器

提供高效的异步任务执行和管理，充分利用Python 3.12的异步特性。
"""

import asyncio
import functools
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Any, Callable, Coroutine, Optional, TypeVar, List
import time

from src.utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class AsyncTaskManager:
    """异步任务管理器"""

    def __init__(self, max_workers: int = 4):
        """
        初始化异步任务管理器

        Args:
            max_workers: 最大工作线程数
        """
        self.max_workers = max_workers
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="MintChat-Worker"
        )
        self._tasks: List[Future] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        logger.info(f"异步任务管理器初始化 (工作线程数: {max_workers})")

    def get_or_create_loop(self) -> asyncio.AbstractEventLoop:
        """获取或创建事件循环"""
        if self._loop is None or self._loop.is_closed():
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        return self._loop

    def run_in_thread(
        self,
        func: Callable[..., T],
        *args,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> Future[T]:
        """
        在线程池中运行同步函数

        Args:
            func: 要执行的函数
            *args: 函数参数
            timeout: 超时时间（秒）
            **kwargs: 函数关键字参数

        Returns:
            Future对象
        """
        future = self._executor.submit(func, *args, **kwargs)
        self._tasks.append(future)

        if timeout:
            # 添加超时检查
            def check_timeout():
                if not future.done():
                    future.cancel()
                    logger.warning(f"任务超时: {func.__name__} ({timeout}秒)")

            timer = threading.Timer(timeout, check_timeout)
            timer.start()

        return future

    async def run_async(
        self,
        coro: Coroutine[Any, Any, T],
        timeout: Optional[float] = None,
    ) -> T:
        """
        运行异步协程

        Args:
            coro: 协程对象
            timeout: 超时时间（秒）

        Returns:
            协程返回值

        Raises:
            TimeoutError: 超时
        """
        try:
            if timeout:
                return await asyncio.wait_for(coro, timeout=timeout)
            else:
                return await coro
        except asyncio.TimeoutError:
            raise TimeoutError(f"异步任务超时 ({timeout}秒): {str(coro)}")

    async def gather(
        self,
        *coros: Coroutine,
        return_exceptions: bool = False,
        timeout: Optional[float] = None,
    ) -> List[Any]:
        """
        并发执行多个协程

        Args:
            *coros: 协程对象列表
            return_exceptions: 是否返回异常
            timeout: 超时时间（秒）

        Returns:
            结果列表
        """
        try:
            if timeout:
                return await asyncio.wait_for(
                    asyncio.gather(*coros, return_exceptions=return_exceptions),
                    timeout=timeout,
                )
            else:
                return await asyncio.gather(*coros, return_exceptions=return_exceptions)
        except asyncio.TimeoutError:
            raise TimeoutError(f"批量异步任务超时 ({timeout}秒): {len(coros)}个任务")

    def run_sync(
        self,
        coro: Coroutine[Any, Any, T],
        timeout: Optional[float] = None,
    ) -> T:
        """
        同步运行异步协程（阻塞）

        Args:
            coro: 协程对象
            timeout: 超时时间（秒）

        Returns:
            协程返回值
        """
        loop = self.get_or_create_loop()
        try:
            if timeout:
                return loop.run_until_complete(
                    asyncio.wait_for(coro, timeout=timeout)
                )
            else:
                return loop.run_until_complete(coro)
        except asyncio.TimeoutError:
            raise TimeoutError(f"同步执行异步任务超时 ({timeout}秒): {str(coro)}")

    def create_task(
        self,
        coro: Coroutine[Any, Any, T],
        name: Optional[str] = None,
    ) -> asyncio.Task[T]:
        """
        创建异步任务（不阻塞）

        Args:
            coro: 协程对象
            name: 任务名称

        Returns:
            Task对象
        """
        loop = self.get_or_create_loop()
        task = loop.create_task(coro, name=name)
        return task

    def wait_for_tasks(self, timeout: Optional[float] = None) -> None:
        """
        等待所有任务完成

        Args:
            timeout: 超时时间（秒）
        """
        start_time = time.time()
        completed = 0
        failed = 0

        for future in self._tasks:
            try:
                remaining_time = None
                if timeout:
                    elapsed = time.time() - start_time
                    remaining_time = max(0, timeout - elapsed)
                    if remaining_time <= 0:
                        logger.warning("等待任务超时")
                        break

                future.result(timeout=remaining_time)
                completed += 1
            except Exception as e:
                failed += 1
                logger.error(f"任务执行失败: {e}")

        self._tasks.clear()
        logger.info(f"任务完成: {completed} 成功, {failed} 失败")

    def shutdown(self, wait: bool = True, timeout: Optional[float] = None) -> None:
        """
        关闭任务管理器

        Args:
            wait: 是否等待任务完成
            timeout: 等待超时时间（秒）
        """
        logger.info("正在关闭异步任务管理器...")

        if wait:
            self.wait_for_tasks(timeout=timeout)

        self._executor.shutdown(wait=wait)

        if self._loop and not self._loop.is_closed():
            self._loop.close()

        logger.info("异步任务管理器已关闭")

    def __enter__(self):
        """支持上下文管理器"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文时关闭管理器"""
        self.shutdown(wait=True, timeout=5.0)

    def __del__(self):
        """析构时确保关闭"""
        try:
            self.shutdown(wait=False)
        except Exception:
            # 析构函数中忽略所有异常
            pass


# 装饰器：将同步函数转换为异步函数


def async_wrap(func: Callable[..., T]) -> Callable[..., Coroutine[Any, Any, T]]:
    """
    将同步函数包装为异步函数

    Args:
        func: 同步函数

    Returns:
        异步函数
    """

    @functools.wraps(func)
    async def wrapper(*args, **kwargs) -> T:
        loop = asyncio.get_running_loop()  # Python 3.7+ 推荐方式
        return await loop.run_in_executor(None, functools.partial(func, *args, **kwargs))

    return wrapper


# 装饰器：为函数添加超时控制


def with_timeout(timeout_seconds: float):
    """
    为异步函数添加超时控制

    Args:
        timeout_seconds: 超时时间（秒）
    """

    def decorator(func: Callable[..., Coroutine[Any, Any, T]]) -> Callable[..., Coroutine[Any, Any, T]]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            try:
                return await asyncio.wait_for(
                    func(*args, **kwargs), timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                raise TimeoutError(f"函数执行超时 ({timeout_seconds}秒): {func.__name__}")

        return wrapper

    return decorator


# 全局任务管理器实例
_global_task_manager: Optional[AsyncTaskManager] = None


def get_task_manager() -> AsyncTaskManager:
    """获取全局任务管理器实例"""
    global _global_task_manager
    if _global_task_manager is None:
        _global_task_manager = AsyncTaskManager()
    return _global_task_manager


# 导入threading用于超时检查
import threading
