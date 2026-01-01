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

import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass
from typing import Any, Callable, Deque, Dict, List, Optional, TypeVar, Set

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
        self._last_flush = time.monotonic()
        self._avg_process_time = 0.0
        self._metrics = PerformanceMetrics(operation="batch_processing")
        self._lock = threading.Lock()

    def add(self, item: Any) -> Optional[List[Any]]:
        """
        添加项目到批处理缓冲区

        Args:
            item: 要添加的项目

        Returns:
            如果触发批处理，返回批次；否则返回None
        """
        should_flush = False
        with self._lock:
            self._buffer.append(item)

            # 检查是否需要刷新
            should_flush = (
                len(self._buffer) >= self.current_batch_size
                or (time.monotonic() - self._last_flush) >= self.max_wait_time
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
        with self._lock:
            if not self._buffer:
                return []

            batch = list(self._buffer)
            self._buffer.clear()
            self._last_flush = time.monotonic()

        # 自适应调整批大小
        self._adjust_batch_size(len(batch))

        return batch

    def _adjust_batch_size(self, processed_count: int) -> None:
        """
        根据处理情况自适应调整批大小

        Args:
            processed_count: 本次处理的项目数量
        """
        with self._lock:
            # 如果处理速度快，增加批大小
            if self._avg_process_time < 0.05 and self.current_batch_size < self.max_batch_size:
                self.current_batch_size = min(self.current_batch_size + 5, self.max_batch_size)
                logger.debug(f"增加批大小到 {self.current_batch_size}")

            # 如果处理速度慢，减小批大小
            elif self._avg_process_time > 0.2 and self.current_batch_size > self.min_batch_size:
                self.current_batch_size = max(self.current_batch_size - 5, self.min_batch_size)
                logger.debug(f"减小批大小到 {self.current_batch_size}")

    def record_process_time(self, elapsed_s: float, processed_count: int) -> None:
        """记录批处理耗时，用于自适应调整（EMA）。"""
        elapsed_s = max(0.0, float(elapsed_s))
        with self._lock:
            alpha = 0.2
            self._avg_process_time = (
                elapsed_s
                if self._avg_process_time <= 0
                else (alpha * elapsed_s + (1 - alpha) * self._avg_process_time)
            )
            self._metrics.count += int(processed_count)
            self._metrics.total_time += elapsed_s
            self._metrics.last_execution = time.monotonic()
            self._metrics.min_time = min(self._metrics.min_time, elapsed_s)
            self._metrics.max_time = max(self._metrics.max_time, elapsed_s)


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
        self._inflight: Set[str] = set()
        self._lock = threading.Lock()
        self._closed = False
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="preloader")

    def preload(self, key: str, loader: Callable[[], T]) -> None:
        """
        异步预加载资源

        Args:
            key: 资源键
            loader: 加载函数
        """
        with self._lock:
            if self._closed:
                return
            if key in self._cache or key in self._inflight:
                return
            self._inflight.add(key)

        def _load():
            try:
                result = loader()
            except Exception as e:
                logger.error(f"预加载失败 {key}: {e}")
                result = None

            with self._lock:
                self._inflight.discard(key)
                if self._closed:
                    return
                # 失败时不写入缓存，允许后续重试
                if result is None:
                    return
                self._cache[key] = result
                self._access_count[key] = 0
                self._last_access[key] = time.monotonic()
                self._evict_if_needed_locked()

            logger.debug("预加载完成: %s", key)

        with self._lock:
            executor = self._executor
        try:
            executor.submit(_load)
        except Exception:
            with self._lock:
                self._inflight.discard(key)

    def get(self, key: str, loader: Optional[Callable[[], T]] = None) -> Optional[T]:
        """
        获取资源，如果不存在则加载

        Args:
            key: 资源键
            loader: 加载函数（可选）

        Returns:
            资源对象，如果不存在且没有loader则返回None
        """
        with self._lock:
            if key in self._cache:
                self._access_count[key] = self._access_count.get(key, 0) + 1
                self._last_access[key] = time.monotonic()
                return self._cache[key]
            if self._closed:
                return None

        # 如果提供了loader，同步加载
        if loader:
            try:
                result = loader()
                with self._lock:
                    if self._closed:
                        return result
                    self._cache[key] = result
                    self._access_count[key] = 1
                    self._last_access[key] = time.monotonic()
                    self._evict_if_needed_locked()
                return result
            except Exception as e:
                logger.error(f"加载资源失败 {key}: {e}")
                return None

        return None

    def _evict_if_needed_locked(self) -> None:
        """如果缓存超过限制，驱逐最少使用的项"""
        # 必须在持有 self._lock 的情况下调用
        if len(self._cache) <= self.max_cache_size:
            return

        # 计算每个项的分数（访问次数 * 时间衰减）
        scores = {}
        current_time = time.monotonic()
        for key in self._cache:
            access_count = self._access_count.get(key, 0)
            last_access = self._last_access.get(key, 0)
            time_decay = 1.0 / (1.0 + (current_time - last_access) / 3600)  # 1小时衰减
            scores[key] = access_count * time_decay

        # 移除分数最低的项
        to_remove = sorted(scores.items(), key=lambda x: x[1])[
            : len(self._cache) - self.max_cache_size
        ]
        for key, _ in to_remove:
            del self._cache[key]
            del self._access_count[key]
            del self._last_access[key]
            logger.debug(f"驱逐缓存项: {key}")

    def cleanup(self) -> None:
        """清理资源"""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            executor = self._executor
            self._cache.clear()
            self._access_count.clear()
            self._last_access.clear()
            self._inflight.clear()

        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            executor.shutdown(wait=False)
        except Exception:
            pass

    def close(self) -> None:
        """cleanup 的别名。"""
        self.cleanup()

    def get_stats(self) -> Dict[str, Any]:
        """获取预加载器统计信息。"""
        with self._lock:
            return {
                "cache_size": len(self._cache),
                "inflight": len(self._inflight),
                "max_cache_size": self.max_cache_size,
                "closed": self._closed,
            }

    def __del__(self) -> None:
        try:
            self.cleanup()
        except Exception:
            pass


class AsyncTaskQueue:
    """异步任务队列 - 管理后台任务执行"""

    def __init__(self, max_workers: int = 4):
        """
        初始化异步任务队列

        Args:
            max_workers: 最大工作线程数
        """
        self.max_workers = max_workers
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="async_task"
        )
        self._pending_tasks: Set[Future[Any]] = set()
        self._lock = threading.Lock()
        self._metrics = PerformanceMetrics(operation="async_tasks")

    def submit(self, func: Callable, *args, **kwargs) -> Future[Any]:
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
        with self._lock:
            self._pending_tasks.add(future)
        self._metrics.count += 1

        def _cleanup(_f: Future[Any]) -> None:
            with self._lock:
                self._pending_tasks.discard(_f)

        future.add_done_callback(_cleanup)
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
        with self._lock:
            pending = list(self._pending_tasks)

        for future in pending:
            try:
                result = future.result(timeout=timeout)
                results.append(result)
            except Exception as e:
                logger.error(f"任务执行失败: {e}")
                self._metrics.errors += 1

        with self._lock:
            self._pending_tasks.clear()
        return results

    def cleanup(self) -> None:
        """清理资源"""
        try:
            self._executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            self._executor.shutdown(wait=False)
        except Exception:
            pass
        with self._lock:
            self._pending_tasks.clear()

    def close(self) -> None:
        """cleanup 的别名。"""
        self.cleanup()

    def get_stats(self) -> Dict[str, Any]:
        """获取任务队列统计信息。"""
        with self._lock:
            pending = len(self._pending_tasks)
        return {
            "pending_tasks": pending,
            "max_workers": self.max_workers,
            "metrics": {
                "count": self._metrics.count,
                "errors": self._metrics.errors,
                "total_time": self._metrics.total_time,
                "min_time": self._metrics.min_time,
                "max_time": self._metrics.max_time,
                "last_execution": self._metrics.last_execution,
            },
        }

    def __del__(self) -> None:
        try:
            self.cleanup()
        except Exception:
            pass


# 全局实例（懒加载，避免导入即创建线程池/后台资源）
_global_lock = threading.Lock()
_batch_processor: AdaptiveBatchProcessor | None = None
_preloader: SmartPreloader | None = None
_task_queue: AsyncTaskQueue | None = None


def get_batch_processor() -> AdaptiveBatchProcessor:
    """获取全局批处理器"""
    global _batch_processor
    if _batch_processor is not None:
        return _batch_processor
    with _global_lock:
        if _batch_processor is None:
            _batch_processor = AdaptiveBatchProcessor()
        return _batch_processor


def get_preloader() -> SmartPreloader:
    """获取全局预加载器"""
    global _preloader
    if _preloader is not None:
        return _preloader
    with _global_lock:
        if _preloader is None:
            _preloader = SmartPreloader()
        return _preloader


def get_task_queue() -> AsyncTaskQueue:
    """获取全局任务队列"""
    global _task_queue
    if _task_queue is not None:
        return _task_queue
    with _global_lock:
        if _task_queue is None:
            _task_queue = AsyncTaskQueue()
        return _task_queue


def shutdown_global_performance_tools() -> None:
    """关闭全局性能工具（用于程序退出/测试收尾）。"""
    global _batch_processor, _preloader, _task_queue
    with _global_lock:
        preloader = _preloader
        task_queue = _task_queue
        _preloader = None
        _task_queue = None
        _batch_processor = None

    if preloader is not None:
        try:
            preloader.close()
        except Exception:
            pass

    if task_queue is not None:
        try:
            task_queue.close()
        except Exception:
            pass
