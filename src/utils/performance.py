"""
性能监控模块

提供性能监控、统计和优化功能。
"""

import time
from collections import defaultdict
from datetime import datetime
from functools import wraps
from typing import Any, Callable, Dict, List, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)


class PerformanceMonitor:
    """性能监控器"""

    def __init__(self):
        """初始化性能监控器"""
        self.metrics: Dict[str, List[float]] = defaultdict(list)
        self.call_counts: Dict[str, int] = defaultdict(int)
        self.error_counts: Dict[str, int] = defaultdict(int)
        self.start_time = datetime.now()

    def record_metric(self, name: str, value: float) -> None:
        """
        记录性能指标

        Args:
            name: 指标名称
            value: 指标值
        """
        self.metrics[name].append(value)
        self.call_counts[name] += 1

    def record_error(self, name: str) -> None:
        """
        记录错误

        Args:
            name: 操作名称
        """
        self.error_counts[name] += 1

    def get_stats(self, name: str) -> Dict[str, Any]:
        """
        获取指标统计信息

        Args:
            name: 指标名称

        Returns:
            Dict: 统计信息
        """
        if name not in self.metrics or not self.metrics[name]:
            return {
                "name": name,
                "count": 0,
                "avg": 0,
                "min": 0,
                "max": 0,
                "total": 0,
                "errors": self.error_counts.get(name, 0),
            }

        values = self.metrics[name]
        return {
            "name": name,
            "count": len(values),
            "avg": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
            "total": sum(values),
            "errors": self.error_counts.get(name, 0),
        }

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有指标的统计信息

        Returns:
            Dict: 所有统计信息
        """
        stats = {}
        for name in self.metrics.keys():
            stats[name] = self.get_stats(name)

        # 添加总体统计
        uptime = (datetime.now() - self.start_time).total_seconds()
        stats["_summary"] = {
            "uptime_seconds": uptime,
            "total_operations": sum(self.call_counts.values()),
            "total_errors": sum(self.error_counts.values()),
            "error_rate": (
                sum(self.error_counts.values()) / sum(self.call_counts.values())
                if sum(self.call_counts.values()) > 0
                else 0
            ),
        }

        return stats

    def reset(self) -> None:
        """重置所有统计信息"""
        self.metrics.clear()
        self.call_counts.clear()
        self.error_counts.clear()
        self.start_time = datetime.now()
        logger.info("性能监控器已重置")

    def print_stats(self) -> None:
        """打印统计信息"""
        stats = self.get_all_stats()

        logger.info("\n" + "=" * 60)
        logger.info("性能统计报告")
        logger.info("=" * 60)

        # 打印总体统计
        summary = stats.pop("_summary")
        logger.info(f"\n运行时间: {summary['uptime_seconds']:.2f} 秒")
        logger.info(f"总操作数: {summary['total_operations']}")
        logger.error(f"总错误数: {summary['total_errors']}")
        logger.error(f"错误率: {summary['error_rate']:.2%}")

        # 打印各项指标
        if stats:
            logger.info("\n详细指标:")
            logger.info("-" * 60)
            for name, data in sorted(stats.items()):
                logger.info(f"\n{name}:")
                logger.info(f"  调用次数: {data['count']}")
                logger.info(f"  平均耗时: {data['avg']:.4f} 秒")
                logger.info(f"  最小耗时: {data['min']:.4f} 秒")
                logger.info(f"  最大耗时: {data['max']:.4f} 秒")
                logger.info(f"  总耗时: {data['total']:.4f} 秒")
                if data['errors'] > 0:
                    logger.error(f"  错误次数: {data['errors']}")

        logger.info("\n" + "=" * 60)


# 全局性能监控器实例
performance_monitor = PerformanceMonitor()


def monitor_performance(name: Optional[str] = None) -> Callable:
    """
    性能监控装饰器

    Args:
        name: 操作名称（默认使用函数名）

    Returns:
        Callable: 装饰器函数
    """

    def decorator(func: Callable) -> Callable:
        operation_name = name or func.__name__

        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                elapsed = time.time() - start_time
                performance_monitor.record_metric(operation_name, elapsed)
                logger.debug(f"{operation_name} 耗时: {elapsed:.4f} 秒")
                return result
            except Exception as e:
                elapsed = time.time() - start_time
                performance_monitor.record_metric(operation_name, elapsed)
                performance_monitor.record_error(operation_name)
                logger.error(f"{operation_name} 失败 (耗时: {elapsed:.4f} 秒): {e}")
                raise

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                elapsed = time.time() - start_time
                performance_monitor.record_metric(operation_name, elapsed)
                logger.debug(f"{operation_name} 耗时: {elapsed:.4f} 秒")
                return result
            except Exception as e:
                elapsed = time.time() - start_time
                performance_monitor.record_metric(operation_name, elapsed)
                performance_monitor.record_error(operation_name)
                logger.error(f"{operation_name} 失败 (耗时: {elapsed:.4f} 秒): {e}")
                raise

        # 根据函数类型返回对应的包装器
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return wrapper

    return decorator


class BatchProcessor:
    """批处理器 - 提升批量操作性能"""

    @staticmethod
    def batch_process(
        items: List[Any],
        process_func: Callable,
        batch_size: int = 10,
        show_progress: bool = True,
    ) -> List[Any]:
        """
        批量处理数据

        Args:
            items: 待处理的数据列表
            process_func: 处理函数
            batch_size: 批次大小
            show_progress: 是否显示进度

        Returns:
            List: 处理结果列表
        """
        results = []
        total = len(items)

        for i in range(0, total, batch_size):
            batch = items[i:i + batch_size]
            batch_results = [process_func(item) for item in batch]
            results.extend(batch_results)

            if show_progress:
                progress = min(i + batch_size, total)
                logger.info(f"批处理进度: {progress}/{total} ({progress / total:.1%})")

        return results

    @staticmethod
    async def batch_process_async(
        items: List[Any],
        process_func: Callable,
        batch_size: int = 10,
        show_progress: bool = True,
    ) -> List[Any]:
        """
        异步批量处理数据

        Args:
            items: 待处理的数据列表
            process_func: 异步处理函数
            batch_size: 批次大小
            show_progress: 是否显示进度

        Returns:
            List: 处理结果列表
        """
        import asyncio

        results = []
        total = len(items)

        for i in range(0, total, batch_size):
            batch = items[i:i + batch_size]
            batch_results = await asyncio.gather(
                *[process_func(item) for item in batch]
            )
            results.extend(batch_results)

            if show_progress:
                progress = min(i + batch_size, total)
                logger.info(f"批处理进度: {progress}/{total} ({progress / total:.1%})")

        return results
