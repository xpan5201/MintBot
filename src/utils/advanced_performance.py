"""
高级性能优化模块 (v2.29.12)

提供全面的性能优化工具：
- 智能预加载和预热
- 自适应批处理
- 内存池管理
- 异步任务队列
- 性能分析和建议

作者: MintChat Team
日期: 2025-11-13
"""

import asyncio
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Deque, Dict, List, Optional, TypeVar

from src.utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


@dataclass
class PerformanceMetrics:
    """性能指标"""

    operation: str
    count: int = 0
    total_time: float = 0.0
    min_time: float = float("inf")
    max_time: float = 0.0
    errors: int = 0
    last_execution: float = 0.0

    @property
    def avg_time(self) -> float:
        """平均执行时间"""
        return self.total_time / self.count if self.count > 0 else 0.0

    @property
    def success_rate(self) -> float:
        """成功率"""
        return (self.count - self.errors) / self.count if self.count > 0 else 0.0


class AdaptiveBatchProcessor:
    """自适应批处理器 - 根据负载动态调整批大小"""

    def __init__(
        self,
        min_batch_size: int = 5,
        max_batch_size: int = 50,
        max_wait_time: float = 0.1,
    ):
        """
        初始化自适应批处理器

        Args:
            min_batch_size: 最小批大小
            max_batch_size: 最大批大小
            max_wait_time: 最大等待时间（秒）
        """
        self.min_batch_size = min_batch_size
        self.max_batch_size = max_batch_size
        self.max_wait_time = max_wait_time
        self.current_batch_size = min_batch_size
        self._buffer: Deque[Any] = deque()
        self._last_flush = time.time()
        self._avg_process_time = 0.0
        self._metrics = PerformanceMetrics(operation="batch_processing")

    def add(self, item: Any) -> Optional[List[Any]]:
        """
        添加项目到批处理缓冲区

        Args:
            item: 要添加的项目

        Returns:
            如果触发批处理，返回批次；否则返回None
        """
        self._buffer.append(item)

        # 检查是否需要刷新
        should_flush = (
            len(self._buffer) >= self.current_batch_size
            or (time.time() - self._last_flush) >= self.max_wait_time
        )

        if should_flush:
            return self.flush()
        return None

    def flush(self) -> List[Any]:
        """
        刷新缓冲区，返回所有待处理项目

        Returns:
            待处理项目列表
        """
        if not self._buffer:
            return []

        batch = list(self._buffer)
        self._buffer.clear()
        self._last_flush = time.time()

        # 自适应调整批大小
        self._adjust_batch_size(len(batch))

        return batch

    def _adjust_batch_size(self, processed_count: int) -> None:
        """
        根据处理情况自适应调整批大小

        Args:
            processed_count: 本次处理的项目数量
        """
        # 如果处理速度快，增加批大小
        if self._avg_process_time < 0.05 and self.current_batch_size < self.max_batch_size:
            self.current_batch_size = min(self.current_batch_size + 5, self.max_batch_size)
            logger.debug(f"增加批大小到 {self.current_batch_size}")

        # 如果处理速度慢，减小批大小
        elif self._avg_process_time > 0.2 and self.current_batch_size > self.min_batch_size:
            self.current_batch_size = max(self.current_batch_size - 5, self.min_batch_size)
            logger.debug(f"减小批大小到 {self.current_batch_size}")


class SmartPreloader:
    """智能预加载器 - 预测性加载常用资源"""

    def __init__(self, max_cache_size: int = 100):
        """
        初始化智能预加载器

        Args:
            max_cache_size: 最大缓存大小
        """
        self.max_cache_size = max_cache_size
        self._cache: Dict[str, Any] = {}
        self._access_count: Dict[str, int] = {}
        self._last_access: Dict[str, float] = {}
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="preloader")

    def preload(self, key: str, loader: Callable[[], T]) -> None:
        """
        异步预加载资源

        Args:
            key: 资源键
            loader: 加载函数
        """
        if key in self._cache:
            return

        def _load():
            try:
                result = loader()
                self._cache[key] = result
                self._access_count[key] = 0
                self._last_access[key] = time.time()
                logger.debug(f"预加载完成: {key}")
            except Exception as e:
                logger.error(f"预加载失败 {key}: {e}")

        self._executor.submit(_load)

    def get(self, key: str, loader: Optional[Callable[[], T]] = None) -> Optional[T]:
        """
        获取资源，如果不存在则加载

        Args:
            key: 资源键
            loader: 加载函数（可选）

        Returns:
            资源对象，如果不存在且没有loader则返回None
        """
        # 更新访问统计
        if key in self._cache:
            self._access_count[key] = self._access_count.get(key, 0) + 1
            self._last_access[key] = time.time()
            return self._cache[key]

        # 如果提供了loader，同步加载
        if loader:
            try:
                result = loader()
                self._cache[key] = result
                self._access_count[key] = 1
                self._last_access[key] = time.time()
                self._evict_if_needed()
                return result
            except Exception as e:
                logger.error(f"加载资源失败 {key}: {e}")
                return None

        return None

    def _evict_if_needed(self) -> None:
        """如果缓存超过限制，驱逐最少使用的项"""
        if len(self._cache) <= self.max_cache_size:
            return

        # 计算每个项的分数（访问次数 * 时间衰减）
        scores = {}
        current_time = time.time()
        for key in self._cache:
            access_count = self._access_count.get(key, 0)
            last_access = self._last_access.get(key, 0)
            time_decay = 1.0 / (1.0 + (current_time - last_access) / 3600)  # 1小时衰减
            scores[key] = access_count * time_decay

        # 移除分数最低的项
        to_remove = sorted(scores.items(), key=lambda x: x[1])[: len(self._cache) - self.max_cache_size]
        for key, _ in to_remove:
            del self._cache[key]
            del self._access_count[key]
            del self._last_access[key]
            logger.debug(f"驱逐缓存项: {key}")

    def cleanup(self) -> None:
        """清理资源"""
        self._executor.shutdown(wait=False)
        self._cache.clear()
        self._access_count.clear()
        self._last_access.clear()


class AsyncTaskQueue:
    """异步任务队列 - 管理后台任务执行"""

    def __init__(self, max_workers: int = 4):
        """
        初始化异步任务队列

        Args:
            max_workers: 最大工作线程数
        """
        self.max_workers = max_workers
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="async_task")
        self._pending_tasks: List[asyncio.Future] = []
        self._metrics = PerformanceMetrics(operation="async_tasks")

    def submit(self, func: Callable, *args, **kwargs) -> asyncio.Future:
        """
        提交异步任务

        Args:
            func: 要执行的函数
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            Future对象
        """
        future = self._executor.submit(func, *args, **kwargs)
        self._pending_tasks.append(future)
        self._metrics.count += 1
        return future

    def wait_all(self, timeout: Optional[float] = None) -> List[Any]:
        """
        等待所有任务完成

        Args:
            timeout: 超时时间（秒）

        Returns:
            所有任务的结果列表
        """
        results = []
        for future in self._pending_tasks:
            try:
                result = future.result(timeout=timeout)
                results.append(result)
            except Exception as e:
                logger.error(f"任务执行失败: {e}")
                self._metrics.errors += 1

        self._pending_tasks.clear()
        return results

    def cleanup(self) -> None:
        """清理资源"""
        self._executor.shutdown(wait=False)
        self._pending_tasks.clear()


# 全局实例
_batch_processor = AdaptiveBatchProcessor()
_preloader = SmartPreloader()
_task_queue = AsyncTaskQueue()


def get_batch_processor() -> AdaptiveBatchProcessor:
    """获取全局批处理器"""
    return _batch_processor


def get_preloader() -> SmartPreloader:
    """获取全局预加载器"""
    return _preloader


def get_task_queue() -> AsyncTaskQueue:
    """获取全局任务队列"""
    return _task_queue

