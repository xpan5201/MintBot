"""
异步优化模块 (v2.29.12) - 针对Python 3.12/3.13优化

利用Python 3.12+的新特性提升异步性能：
- TaskGroup (PEP 654) - 结构化并发
- ExceptionGroup - 更好的异常处理
- asyncio性能改进
- 类型提示增强

作者: MintChat Team
日期: 2025-11-13
"""

import asyncio
import sys
import time
from contextlib import asynccontextmanager
from functools import wraps
from typing import Any, Awaitable, Callable, Coroutine, List, Optional, TypeVar

from src.utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

# 检测Python版本
PYTHON_VERSION = sys.version_info
HAS_TASKGROUP = PYTHON_VERSION >= (3, 11)  # TaskGroup在3.11+可用


class AsyncBatchExecutor:
    """异步批量执行器 - 利用Python 3.11+ TaskGroup"""

    def __init__(self, max_concurrent: int = 10):
        """
        初始化异步批量执行器

        Args:
            max_concurrent: 最大并发数
        """
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def execute_batch(
        self, tasks: List[Callable[[], Awaitable[T]]], timeout: Optional[float] = None
    ) -> List[T]:
        """
        批量执行异步任务

        Args:
            tasks: 任务列表
            timeout: 超时时间（秒）

        Returns:
            结果列表
        """
        if not tasks:
            return []

        results = []
        errors = []

        async def _execute_with_semaphore(task_func: Callable[[], Awaitable[T]], index: int):
            """使用信号量限制并发"""
            async with self._semaphore:
                try:
                    result = await asyncio.wait_for(task_func(), timeout=timeout)
                    return index, result, None
                except Exception as e:
                    logger.error(f"任务 {index} 执行失败: {e}")
                    return index, None, e

        # Python 3.11+ 使用 TaskGroup
        if HAS_TASKGROUP:
            try:
                async with asyncio.TaskGroup() as tg:
                    task_futures = [
                        tg.create_task(_execute_with_semaphore(task, i))
                        for i, task in enumerate(tasks)
                    ]

                # 收集结果
                for future in task_futures:
                    index, result, error = future.result()
                    if error:
                        errors.append((index, error))
                    else:
                        results.append((index, result))

            except* Exception as eg:  # ExceptionGroup
                logger.error(f"批量执行出现异常组: {eg}")
                for exc in eg.exceptions:
                    logger.error(f"  - {exc}")

        # Python 3.10及以下使用 gather
        else:
            task_results = await asyncio.gather(
                *[_execute_with_semaphore(task, i) for i, task in enumerate(tasks)],
                return_exceptions=True,
            )

            for task_result in task_results:
                if isinstance(task_result, Exception):
                    errors.append(task_result)
                else:
                    index, result, error = task_result
                    if error:
                        errors.append((index, error))
                    else:
                        results.append((index, result))

        # 按索引排序结果
        results.sort(key=lambda x: x[0])
        return [result for _, result in results]

    async def execute_with_retry(
        self, task: Callable[[], Awaitable[T]], max_retries: int = 3, retry_delay: float = 1.0
    ) -> Optional[T]:
        """
        执行异步任务，支持重试

        Args:
            task: 异步任务
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）

        Returns:
            任务结果，失败返回None
        """
        for attempt in range(max_retries + 1):
            try:
                async with self._semaphore:
                    result = await task()
                    return result
            except Exception as e:
                if attempt < max_retries:
                    logger.warning(
                        f"任务执行失败，{retry_delay}秒后重试 ({attempt + 1}/{max_retries}): {e}"
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(f"任务执行失败，已达最大重试次数: {e}")
                    return None


class AsyncCache:
    """异步缓存 - 支持异步加载和过期"""

    def __init__(self, ttl: float = 300.0, max_size: int = 1000):
        """
        初始化异步缓存

        Args:
            ttl: 缓存过期时间（秒）
            max_size: 最大缓存大小
        """
        self.ttl = ttl
        self.max_size = max_size
        self._cache: dict[str, tuple[Any, float]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._access_count: dict[str, int] = {}

    async def get_or_load(self, key: str, loader: Callable[[], Awaitable[T]]) -> T:
        """
        获取缓存或异步加载

        Args:
            key: 缓存键
            loader: 异步加载函数

        Returns:
            缓存值
        """
        # 检查缓存
        if key in self._cache:
            value, timestamp = self._cache[key]
            if time.time() - timestamp < self.ttl:
                self._access_count[key] = self._access_count.get(key, 0) + 1
                return value

        # 获取或创建锁
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()

        # 加载数据（使用锁避免重复加载）
        async with self._locks[key]:
            # 双重检查
            if key in self._cache:
                value, timestamp = self._cache[key]
                if time.time() - timestamp < self.ttl:
                    return value

            # 加载新数据
            value = await loader()
            self._cache[key] = (value, time.time())
            self._access_count[key] = 1

            # 检查缓存大小
            if len(self._cache) > self.max_size:
                self._evict_lru()

            return value

    def _evict_lru(self):
        """驱逐最少使用的缓存项"""
        if not self._cache:
            return

        # 找到访问次数最少的键
        lru_key = min(self._access_count.items(), key=lambda x: x[1])[0]
        del self._cache[lru_key]
        del self._access_count[lru_key]
        if lru_key in self._locks:
            del self._locks[lru_key]

    def invalidate(self, key: str):
        """使缓存失效"""
        if key in self._cache:
            del self._cache[key]
        if key in self._access_count:
            del self._access_count[key]
        if key in self._locks:
            del self._locks[key]

    def clear(self):
        """清空缓存"""
        self._cache.clear()
        self._access_count.clear()
        self._locks.clear()


def async_timed(
    func: Callable[..., Coroutine[Any, Any, T]],
) -> Callable[..., Coroutine[Any, Any, T]]:
    """
    异步函数计时装饰器

    Args:
        func: 异步函数

    Returns:
        装饰后的函数
    """

    @wraps(func)
    async def wrapper(*args, **kwargs) -> T:
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            return result
        finally:
            duration = time.time() - start_time
            if duration > 1.0:  # 超过1秒记录警告
                logger.warning(f"{func.__name__} 耗时 {duration:.2f}秒")
            else:
                logger.debug(f"{func.__name__} 耗时 {duration:.3f}秒")

    return wrapper


def async_cached(ttl: float = 300.0):
    """
    异步函数缓存装饰器

    Args:
        ttl: 缓存过期时间（秒）

    Returns:
        装饰器函数
    """
    cache = AsyncCache(ttl=ttl)

    def decorator(
        func: Callable[..., Coroutine[Any, Any, T]],
    ) -> Callable[..., Coroutine[Any, Any, T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            # 生成缓存键
            cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"

            # 使用缓存
            async def loader():
                return await func(*args, **kwargs)

            return await cache.get_or_load(cache_key, loader)

        # 添加缓存控制方法
        wrapper.cache = cache  # type: ignore
        return wrapper

    return decorator


@asynccontextmanager
async def async_timeout(seconds: float):
    """
    异步超时上下文管理器

    Args:
        seconds: 超时时间（秒）

    Yields:
        None

    Raises:
        asyncio.TimeoutError: 超时
    """
    try:
        async with asyncio.timeout(seconds):
            yield
    except asyncio.TimeoutError:
        logger.error(f"操作超时 ({seconds}秒)")
        raise


# 全局实例
_batch_executor = AsyncBatchExecutor()
_async_cache = AsyncCache()


def get_batch_executor() -> AsyncBatchExecutor:
    """获取全局批量执行器"""
    return _batch_executor


def get_async_cache() -> AsyncCache:
    """获取全局异步缓存"""
    return _async_cache
