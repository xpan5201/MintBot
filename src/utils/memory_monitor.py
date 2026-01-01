"""
MintChat - 内存监控和管理

提供内存监控、自动清理和泄漏检测功能

v2.30.6 新增
"""

import psutil
import threading
import time
from typing import List, Callable, Optional
from dataclasses import dataclass, field
from datetime import datetime

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class MemoryStats:
    """内存统计信息"""

    timestamp: datetime = field(default_factory=datetime.now)
    total_mb: float = 0.0
    available_mb: float = 0.0
    used_mb: float = 0.0
    percent: float = 0.0
    process_mb: float = 0.0  # 当前进程占用

    @property
    def is_high(self) -> bool:
        """是否内存占用过高（>80%）"""
        return self.percent > 80.0

    @property
    def is_critical(self) -> bool:
        """是否内存占用严重（>90%）"""
        return self.percent > 90.0


class MemoryMonitor:
    """内存监控器 - 单例模式"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return

        self._initialized = True
        self._cleanup_callbacks: List[Callable[[], None]] = []
        self._monitoring = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._check_interval = 30.0  # 检查间隔（秒）
        self._high_memory_threshold = 80.0  # 高内存阈值（%）
        self._critical_memory_threshold = 90.0  # 严重内存阈值（%）
        self._stats_history: List[MemoryStats] = []
        self._max_history = 100  # 最多保留100条历史记录

        logger.info("内存监控器初始化完成")

    def get_current_stats(self) -> MemoryStats:
        """获取当前内存统计"""
        try:
            # 系统内存
            mem = psutil.virtual_memory()

            # 当前进程内存
            process = psutil.Process()
            process_mem = process.memory_info().rss / 1024 / 1024  # MB

            stats = MemoryStats(
                total_mb=mem.total / 1024 / 1024,
                available_mb=mem.available / 1024 / 1024,
                used_mb=mem.used / 1024 / 1024,
                percent=mem.percent,
                process_mb=process_mem,
            )

            return stats
        except Exception as e:
            logger.error(f"获取内存统计失败: {e}")
            return MemoryStats()

    def register_cleanup_callback(self, callback: Callable[[], None]) -> None:
        """
        注册清理回调

        当内存占用过高时，会调用所有注册的清理回调

        Args:
            callback: 清理回调函数
        """
        with self._lock:
            self._cleanup_callbacks.append(callback)
            logger.info(f"已注册内存清理回调（共 {len(self._cleanup_callbacks)} 个）")

    def trigger_cleanup(self, reason: str = "手动触发") -> int:
        """
        触发内存清理

        Args:
            reason: 触发原因

        Returns:
            执行的清理回调数量
        """
        logger.info(f"触发内存清理: {reason}")

        with self._lock:
            callbacks = self._cleanup_callbacks.copy()

        count = 0
        for callback in callbacks:
            try:
                callback()
                count += 1
            except Exception as e:
                logger.error(f"执行清理回调失败: {e}")

        logger.info(f"内存清理完成，执行了 {count}/{len(callbacks)} 个回调")
        return count

    def start_monitoring(
        self,
        check_interval: float = 30.0,
        high_threshold: float = 80.0,
        critical_threshold: float = 90.0,
    ) -> None:
        """
        启动内存监控

        Args:
            check_interval: 检查间隔（秒）
            high_threshold: 高内存阈值（%）
            critical_threshold: 严重内存阈值（%）
        """
        if self._monitoring:
            logger.warning("内存监控已在运行")
            return

        self._check_interval = check_interval
        self._high_memory_threshold = high_threshold
        self._critical_memory_threshold = critical_threshold
        self._monitoring = True

        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="MemoryMonitor"
        )
        self._monitor_thread.start()

        logger.info(
            f"内存监控已启动 "
            f"(间隔={check_interval}s, 高阈值={high_threshold}%, 严重阈值={critical_threshold}%)"
        )

    def stop_monitoring(self) -> None:
        """停止内存监控"""
        if not self._monitoring:
            return

        self._monitoring = False

        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=5.0)

        logger.info("内存监控已停止")

    def _monitor_loop(self) -> None:
        """监控循环"""
        while self._monitoring:
            try:
                # 获取当前内存统计
                stats = self.get_current_stats()

                # 保存到历史记录
                with self._lock:
                    self._stats_history.append(stats)
                    if len(self._stats_history) > self._max_history:
                        self._stats_history.pop(0)

                # 检查是否需要清理
                if stats.percent >= self._critical_memory_threshold:
                    logger.warning(
                        f"内存占用严重 ({stats.percent:.1f}%)，"
                        f"进程占用 {stats.process_mb:.1f}MB，"
                        f"触发清理"
                    )
                    self.trigger_cleanup(f"内存占用严重 ({stats.percent:.1f}%)")
                elif stats.percent >= self._high_memory_threshold:
                    logger.warning(
                        f"内存占用过高 ({stats.percent:.1f}%)，"
                        f"进程占用 {stats.process_mb:.1f}MB"
                    )

                # 等待下次检查
                time.sleep(self._check_interval)
            except Exception as e:
                logger.error(f"内存监控循环出错: {e}")
                time.sleep(self._check_interval)

    def get_stats_history(self, count: int = 10) -> List[MemoryStats]:
        """
        获取历史统计记录

        Args:
            count: 获取最近的记录数

        Returns:
            历史统计记录列表
        """
        with self._lock:
            return self._stats_history[-count:]

    def print_stats(self) -> None:
        """打印当前内存统计"""
        stats = self.get_current_stats()

        logger.info("\n" + "=" * 60)
        logger.info("内存统计信息")
        logger.info("=" * 60)
        logger.info(f"系统总内存:     {stats.total_mb:>10.1f} MB")
        logger.info(f"系统可用内存:   {stats.available_mb:>10.1f} MB")
        logger.info(f"系统已用内存:   {stats.used_mb:>10.1f} MB")
        logger.info(f"系统内存占用:   {stats.percent:>10.1f} %")
        logger.info(f"进程内存占用:   {stats.process_mb:>10.1f} MB")
        logger.info("-" * 60)

        if stats.is_critical:
            logger.warning("⚠️  警告: 内存占用严重！")
        elif stats.is_high:
            logger.warning("⚠️  警告: 内存占用过高！")
        else:
            logger.success("✅ 内存占用正常")

        logger.info("=" * 60 + "\n")


# 全局实例
_memory_monitor = None


def get_memory_monitor() -> MemoryMonitor:
    """获取全局内存监控器"""
    global _memory_monitor
    if _memory_monitor is None:
        _memory_monitor = MemoryMonitor()
    return _memory_monitor


def setup_memory_monitoring(
    check_interval: float = 30.0,
    high_threshold: float = 80.0,
    critical_threshold: float = 90.0,
    auto_cleanup: bool = True,
) -> MemoryMonitor:
    """
    设置内存监控

    Args:
        check_interval: 检查间隔（秒）
        high_threshold: 高内存阈值（%）
        critical_threshold: 严重内存阈值（%）
        auto_cleanup: 是否自动注册清理回调

    Returns:
        内存监控器实例
    """
    monitor = get_memory_monitor()

    if auto_cleanup:
        # 注册缓存清理回调
        from src.utils.enhanced_cache import get_cache_manager
        from src.utils.logger import logger

        def cleanup_caches():
            """清理所有缓存的过期条目"""
            manager = get_cache_manager()
            results = manager.cleanup_all()
            try:
                from src.utils.cache_manager import cache_manager

                results["smart_cache_manager"] = cache_manager.cleanup_all()
            except Exception:
                pass
            cleaned_total = 0
            if results:
                try:
                    cleaned_total = int(sum(results.values()))
                except Exception:
                    cleaned_total = 0
            if cleaned_total > 0:
                logger.info(f"清理了 {cleaned_total} 个过期缓存条目")

        monitor.register_cleanup_callback(cleanup_caches)

    # 启动监控
    monitor.start_monitoring(
        check_interval=check_interval,
        high_threshold=high_threshold,
        critical_threshold=critical_threshold,
    )

    return monitor
