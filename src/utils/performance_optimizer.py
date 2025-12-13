"""
性能优化工具模块 - v2.29.9

提供全方位的性能优化工具：
- 对象池管理
- 智能预加载
- 资源回收
- 性能分析
"""

import gc
import time
import weakref
from collections import deque
from functools import wraps
from typing import Any, Callable, Dict, List, TypeVar
from src.utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class ObjectPool:
    """对象池 - 复用对象，减少创建开销

    适用于频繁创建和销毁的对象，如消息气泡、临时容器等
    """

    def __init__(self, factory: Callable[[], T], max_size: int = 50):
        """初始化对象池

        Args:
            factory: 对象工厂函数
            max_size: 池最大容量
        """
        self.factory = factory
        self.max_size = max_size
        self._pool: deque = deque(maxlen=max_size)
        self._stats = {"created": 0, "reused": 0, "returned": 0}
        logger.debug(f"对象池初始化，最大容量: {max_size}")

    def acquire(self) -> T:
        """获取对象"""
        if self._pool:
            obj = self._pool.popleft()
            self._stats["reused"] += 1
            logger.debug(f"从池中复用对象，剩余: {len(self._pool)}")
            return obj
        else:
            obj = self.factory()
            self._stats["created"] += 1
            logger.debug(f"创建新对象，总创建数: {self._stats['created']}")
            return obj

    def release(self, obj: T) -> None:
        """归还对象"""
        if len(self._pool) < self.max_size:
            # 重置对象状态（如果有reset方法）
            if hasattr(obj, "reset"):
                obj.reset()
            self._pool.append(obj)
            self._stats["returned"] += 1
            logger.debug(f"对象归还到池，当前容量: {len(self._pool)}")
        else:
            # 池已满，让对象被垃圾回收
            logger.debug("对象池已满，对象将被回收")

    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        return {
            **self._stats,
            "pool_size": len(self._pool),
            "hit_rate": (
                self._stats["reused"] / (self._stats["created"] + self._stats["reused"])
                if (self._stats["created"] + self._stats["reused"]) > 0
                else 0
            ),
        }

    def clear(self) -> None:
        """清空对象池"""
        self._pool.clear()
        logger.info("对象池已清空")


class ResourceTracker:
    """资源跟踪器 - 跟踪和管理资源生命周期

    使用弱引用跟踪对象，避免内存泄漏
    """

    def __init__(self):
        self._tracked: Dict[str, List[weakref.ref]] = {}
        self._stats = {"tracked": 0, "collected": 0}

    def track(self, obj: Any, category: str = "default") -> None:
        """跟踪对象

        Args:
            obj: 要跟踪的对象
            category: 对象类别
        """
        if category not in self._tracked:
            self._tracked[category] = []

        # 使用弱引用，不阻止垃圾回收
        ref = weakref.ref(obj, lambda r: self._on_collected(category))
        self._tracked[category].append(ref)
        self._stats["tracked"] += 1
        logger.debug(f"跟踪对象: {category}, 总数: {len(self._tracked[category])}")

    def _on_collected(self, category: str) -> None:
        """对象被回收时的回调"""
        self._stats["collected"] += 1
        logger.debug(f"对象已回收: {category}")

    def get_alive_count(self, category: str = None) -> int:
        """获取存活对象数量

        Args:
            category: 对象类别，None表示所有类别

        Returns:
            存活对象数量
        """
        if category:
            if category not in self._tracked:
                return 0
            # 清理已回收的引用
            self._tracked[category] = [ref for ref in self._tracked[category] if ref() is not None]
            return len(self._tracked[category])
        else:
            total = 0
            for cat in self._tracked:
                total += self.get_alive_count(cat)
            return total

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            "categories": {cat: self.get_alive_count(cat) for cat in self._tracked},
            "total_alive": self.get_alive_count(),
        }

    def force_cleanup(self) -> int:
        """强制清理已回收的引用

        Returns:
            清理的引用数量
        """
        cleaned = 0
        for category in self._tracked:
            before = len(self._tracked[category])
            self._tracked[category] = [ref for ref in self._tracked[category] if ref() is not None]
            cleaned += before - len(self._tracked[category])
        logger.info(f"强制清理了 {cleaned} 个已回收的引用")
        return cleaned


class PerformanceAnalyzer:
    """性能分析器 - 分析和优化性能瓶颈"""

    def __init__(self):
        self._metrics: Dict[str, List[float]] = {}
        self._thresholds: Dict[str, float] = {}

    def record(self, operation: str, duration: float, threshold: float = 0.1) -> None:
        """记录操作耗时

        Args:
            operation: 操作名称
            duration: 耗时（秒）
            threshold: 警告阈值（秒）
        """
        if operation not in self._metrics:
            self._metrics[operation] = []
            self._thresholds[operation] = threshold

        self._metrics[operation].append(duration)

        # 超过阈值时警告
        if duration > threshold:
            logger.warning(f"性能警告: {operation} 耗时 {duration:.3f}s (阈值: {threshold:.3f}s)")

    def get_stats(self, operation: str = None) -> Dict[str, Any]:
        """获取统计信息

        Args:
            operation: 操作名称，None表示所有操作

        Returns:
            统计信息
        """
        if operation:
            if operation not in self._metrics:
                return {}
            durations = self._metrics[operation]
            return {
                "operation": operation,
                "count": len(durations),
                "total": sum(durations),
                "avg": sum(durations) / len(durations) if durations else 0,
                "min": min(durations) if durations else 0,
                "max": max(durations) if durations else 0,
                "threshold": self._thresholds.get(operation, 0),
            }
        else:
            return {op: self.get_stats(op) for op in self._metrics}

    def get_slow_operations(self, threshold: float = 0.1) -> List[str]:
        """获取慢操作列表

        Args:
            threshold: 阈值（秒）

        Returns:
            慢操作列表
        """
        slow_ops = []
        for operation in self._metrics:
            stats = self.get_stats(operation)
            if stats["avg"] > threshold:
                slow_ops.append(operation)
        return slow_ops

    def clear(self) -> None:
        """清空统计数据"""
        self._metrics.clear()
        self._thresholds.clear()
        logger.info("性能分析数据已清空")


def measure_performance(threshold: float = 0.1):
    """性能测量装饰器

    Args:
        threshold: 警告阈值（秒）
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                if duration > threshold:
                    logger.warning(
                        f"性能警告: {func.__name__} 耗时 {duration:.3f}s (阈值: {threshold:.3f}s)"
                    )

        return wrapper

    return decorator


def optimize_gc(generation: int = 2):
    """优化垃圾回收装饰器

    在函数执行后触发垃圾回收，释放内存

    Args:
        generation: GC代数 (0, 1, 2)
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                # 触发垃圾回收
                collected = gc.collect(generation)
                if collected > 0:
                    logger.debug(f"GC回收了 {collected} 个对象 (代数: {generation})")

        return wrapper

    return decorator


# 全局实例
resource_tracker = ResourceTracker()
performance_analyzer = PerformanceAnalyzer()


if __name__ == "__main__":
    # 测试对象池
    logger.info("=== 测试对象池 ===")
    pool = ObjectPool(factory=lambda: {"data": []}, max_size=5)

    # 获取对象
    obj1 = pool.acquire()
    obj2 = pool.acquire()
    logger.info(f"获取2个对象，统计: {pool.get_stats()}")

    # 归还对象
    pool.release(obj1)
    pool.release(obj2)
    logger.info(f"归还2个对象，统计: {pool.get_stats()}")

    # 再次获取（应该复用）
    obj3 = pool.acquire()
    logger.info(f"再次获取对象，统计: {pool.get_stats()}")

    # 测试资源跟踪
    logger.info("\n=== 测试资源跟踪 ===")
    tracker = ResourceTracker()

    class TestObject:
        pass

    obj_a = TestObject()
    obj_b = TestObject()
    tracker.track(obj_a, "test")
    tracker.track(obj_b, "test")
    logger.info(f"跟踪2个对象，存活数: {tracker.get_alive_count('test')}")

    del obj_a
    gc.collect()
    logger.info(f"删除1个对象后，存活数: {tracker.get_alive_count('test')}")

    # 测试性能分析
    logger.info("\n=== 测试性能分析 ===")
    analyzer = PerformanceAnalyzer()
    analyzer.record("operation1", 0.05, threshold=0.1)
    analyzer.record("operation1", 0.15, threshold=0.1)  # 应该警告
    analyzer.record("operation2", 0.02, threshold=0.1)
    logger.info(f"性能统计: {analyzer.get_stats()}")
    logger.info(f"慢操作: {analyzer.get_slow_operations(threshold=0.1)}")
