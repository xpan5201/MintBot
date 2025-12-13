"""
MintChat - 统一线程池管理器

提供全局线程池管理，避免资源泄漏，优化线程使用。
支持监控、统计、自动清理。

v2.30.6 新增
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ThreadPoolStats:
    """线程池统计信息"""
    name: str
    max_workers: int
    active_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    total_execution_time: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)


class ManagedThreadPool:
    """托管线程池 - 带监控和统计"""
    
    def __init__(
        self,
        name: str,
        max_workers: int,
        thread_name_prefix: Optional[str] = None,
    ):
        """
        初始化托管线程池
        
        Args:
            name: 线程池名称
            max_workers: 最大工作线程数
            thread_name_prefix: 线程名称前缀
        """
        self.name = name
        self.max_workers = max_workers
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=thread_name_prefix or f"MintChat-{name}"
        )
        self._futures: List[Future] = []
        self._lock = threading.Lock()
        self._stats = ThreadPoolStats(name=name, max_workers=max_workers)
        self._shutdown = False
        
        logger.info(f"线程池 '{name}' 初始化完成 (max_workers={max_workers})")
    
    def submit(
        self,
        func: Callable,
        *args,
        timeout: Optional[float] = None,
        **kwargs
    ) -> Future:
        """
        提交任务到线程池
        
        Args:
            func: 要执行的函数
            *args: 位置参数
            timeout: 超时时间（秒）
            **kwargs: 关键字参数
            
        Returns:
            Future对象
        """
        if self._shutdown:
            raise RuntimeError(f"线程池 '{self.name}' 已关闭")
        
        start_time = time.time()
        
        def wrapped_func():
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                
                with self._lock:
                    self._stats.completed_tasks += 1
                    self._stats.total_execution_time += execution_time
                    self._stats.last_activity = datetime.now()
                
                return result
            except Exception as e:
                with self._lock:
                    self._stats.failed_tasks += 1
                    self._stats.last_activity = datetime.now()
                logger.error(f"线程池 '{self.name}' 任务执行失败: {e}")
                raise
        
        future = self._executor.submit(wrapped_func)
        
        with self._lock:
            self._futures.append(future)
            self._stats.active_tasks += 1
        
        # 添加完成回调
        def on_done(f):
            with self._lock:
                self._stats.active_tasks -= 1
                if f in self._futures:
                    self._futures.remove(f)
        
        future.add_done_callback(on_done)
        
        return future
    
    def get_stats(self) -> ThreadPoolStats:
        """获取统计信息"""
        with self._lock:
            return ThreadPoolStats(
                name=self._stats.name,
                max_workers=self._stats.max_workers,
                active_tasks=self._stats.active_tasks,
                completed_tasks=self._stats.completed_tasks,
                failed_tasks=self._stats.failed_tasks,
                total_execution_time=self._stats.total_execution_time,
                created_at=self._stats.created_at,
                last_activity=self._stats.last_activity,
            )
    
    def wait_for_completion(self, timeout: Optional[float] = None) -> bool:
        """
        等待所有任务完成
        
        Args:
            timeout: 超时时间（秒）
            
        Returns:
            是否所有任务都完成
        """
        from concurrent.futures import wait, FIRST_COMPLETED
        
        with self._lock:
            futures = list(self._futures)
        
        if not futures:
            return True
        
        done, not_done = wait(futures, timeout=timeout)
        return len(not_done) == 0
    
    def shutdown(self, wait: bool = True, timeout: Optional[float] = None) -> None:
        """
        关闭线程池
        
        Args:
            wait: 是否等待任务完成
            timeout: 等待超时时间（秒）
        """
        if self._shutdown:
            return
        
        self._shutdown = True
        logger.info(f"正在关闭线程池 '{self.name}'...")
        
        if wait and timeout:
            self.wait_for_completion(timeout=timeout)
        
        self._executor.shutdown(wait=wait)
        
        with self._lock:
            self._futures.clear()
        
        logger.info(f"线程池 '{self.name}' 已关闭")


class ThreadPoolManager:
    """全局线程池管理器 - 单例模式"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return

        self._initialized = True
        self._pools: Dict[str, ManagedThreadPool] = {}
        self._global_lock = threading.Lock()

        # 创建默认线程池
        self._create_default_pools()

        logger.info("全局线程池管理器初始化完成")

    def _create_default_pools(self):
        """创建默认线程池"""
        # GUI相关任务（低延迟）
        self.register_pool("gui", max_workers=2)

        # I/O密集型任务（网络请求、文件读写）
        self.register_pool("io", max_workers=8)

        # CPU密集型任务（图片处理、向量计算）
        self.register_pool("cpu", max_workers=4)

        # 后台任务（低优先级）
        self.register_pool("background", max_workers=2)

    def register_pool(
        self,
        name: str,
        max_workers: int,
        thread_name_prefix: Optional[str] = None,
    ) -> ManagedThreadPool:
        """
        注册新的线程池

        Args:
            name: 线程池名称
            max_workers: 最大工作线程数
            thread_name_prefix: 线程名称前缀

        Returns:
            托管线程池对象
        """
        with self._global_lock:
            if name in self._pools:
                logger.warning(f"线程池 '{name}' 已存在，返回现有实例")
                return self._pools[name]

            pool = ManagedThreadPool(
                name=name,
                max_workers=max_workers,
                thread_name_prefix=thread_name_prefix
            )
            self._pools[name] = pool

            logger.info(f"注册线程池 '{name}' (max_workers={max_workers})")
            return pool

    def get_pool(self, name: str) -> Optional[ManagedThreadPool]:
        """获取线程池"""
        with self._global_lock:
            return self._pools.get(name)

    def submit_to_pool(
        self,
        pool_name: str,
        func: Callable,
        *args,
        timeout: Optional[float] = None,
        **kwargs
    ) -> Future:
        """
        提交任务到指定线程池

        Args:
            pool_name: 线程池名称
            func: 要执行的函数
            *args: 位置参数
            timeout: 超时时间（秒）
            **kwargs: 关键字参数

        Returns:
            Future对象
        """
        pool = self.get_pool(pool_name)
        if pool is None:
            raise ValueError(f"线程池 '{pool_name}' 不存在")

        return pool.submit(func, *args, timeout=timeout, **kwargs)

    def get_all_stats(self) -> Dict[str, ThreadPoolStats]:
        """获取所有线程池的统计信息"""
        with self._global_lock:
            return {
                name: pool.get_stats()
                for name, pool in self._pools.items()
            }

    def print_stats(self):
        """打印所有线程池的统计信息"""
        stats = self.get_all_stats()

        logger.info("=" * 60)
        logger.info("线程池统计信息")
        logger.info("=" * 60)

        for name, stat in stats.items():
            avg_time = (
                stat.total_execution_time / stat.completed_tasks
                if stat.completed_tasks > 0
                else 0
            )

            logger.info(f"\n线程池: {name}")
            logger.info(f"  最大线程数: {stat.max_workers}")
            logger.info(f"  活跃任务: {stat.active_tasks}")
            logger.info(f"  已完成: {stat.completed_tasks}")
            logger.info(f"  失败: {stat.failed_tasks}")
            logger.info(f"  平均执行时间: {avg_time:.3f}秒")
            logger.info(f"  最后活动: {stat.last_activity.strftime('%Y-%m-%d %H:%M:%S')}")

        logger.info("=" * 60)

    def shutdown_all(self, wait: bool = True, timeout: Optional[float] = 5.0):
        """
        关闭所有线程池

        Args:
            wait: 是否等待任务完成
            timeout: 等待超时时间（秒）
        """
        logger.info("正在关闭所有线程池...")

        with self._global_lock:
            pools = list(self._pools.values())

        for pool in pools:
            try:
                pool.shutdown(wait=wait, timeout=timeout)
            except Exception as e:
                logger.error(f"关闭线程池 '{pool.name}' 失败: {e}")

        with self._global_lock:
            self._pools.clear()

        logger.info("所有线程池已关闭")

    def __del__(self):
        """析构时确保关闭所有线程池"""
        try:
            self.shutdown_all(wait=False)
        except Exception:
            pass


# 全局实例
_thread_pool_manager = None


def get_thread_pool_manager() -> ThreadPoolManager:
    """获取全局线程池管理器"""
    global _thread_pool_manager
    if _thread_pool_manager is None:
        _thread_pool_manager = ThreadPoolManager()
    return _thread_pool_manager


def submit_gui_task(func: Callable, *args, **kwargs) -> Future:
    """提交GUI任务（低延迟）"""
    return get_thread_pool_manager().submit_to_pool("gui", func, *args, **kwargs)


def submit_io_task(func: Callable, *args, **kwargs) -> Future:
    """提交I/O任务（网络、文件）"""
    return get_thread_pool_manager().submit_to_pool("io", func, *args, **kwargs)


def submit_cpu_task(func: Callable, *args, **kwargs) -> Future:
    """提交CPU任务（计算密集）"""
    return get_thread_pool_manager().submit_to_pool("cpu", func, *args, **kwargs)


def submit_background_task(func: Callable, *args, **kwargs) -> Future:
    """提交后台任务（低优先级）"""
    return get_thread_pool_manager().submit_to_pool("background", func, *args, **kwargs)


