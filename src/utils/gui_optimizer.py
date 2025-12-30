"""
GUI性能优化工具 (v2.29.1)

提供GUI性能优化相关的工具函数和装饰器。
"""

import functools
import time
from typing import Callable, Optional
from PyQt6.QtCore import QTimer, QObject, pyqtSignal
from PyQt6.QtWidgets import QWidget

from src.utils.logger import get_logger

logger = get_logger(__name__)


class DebouncedSignal(QObject):
    """
    防抖信号 - 在指定时间内只触发一次

    用于优化频繁触发的信号，如文本输入、窗口调整大小等。
    """

    triggered = pyqtSignal()

    def __init__(self, delay_ms: int = 300, parent: Optional[QObject] = None):
        """
        初始化防抖信号

        Args:
            delay_ms: 延迟时间（毫秒）
            parent: 父对象
        """
        super().__init__(parent)
        self.delay_ms = delay_ms
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.triggered.emit)

    def trigger(self):
        """触发信号（会被防抖）"""
        self._timer.stop()
        self._timer.start(self.delay_ms)

    def trigger_now(self):
        """立即触发信号（不防抖）"""
        self._timer.stop()
        self.triggered.emit()


class ThrottledSignal(QObject):
    """
    节流信号 - 在指定时间内最多触发一次

    用于优化高频事件，如滚动、鼠标移动等。
    """

    triggered = pyqtSignal()

    def __init__(self, interval_ms: int = 100, parent: Optional[QObject] = None):
        """
        初始化节流信号

        Args:
            interval_ms: 时间间隔（毫秒）
            parent: 父对象
        """
        super().__init__(parent)
        self.interval_ms = interval_ms
        self._last_trigger_time = 0
        self._pending = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)

    def trigger(self):
        """触发信号（会被节流）"""
        current_time = time.monotonic() * 1000  # 转换为毫秒（单调时钟，避免系统时间跳变）

        if current_time - self._last_trigger_time >= self.interval_ms:
            # 可以立即触发
            self._last_trigger_time = current_time
            self.triggered.emit()
            self._pending = False
        else:
            # 需要等待，设置pending标志
            if not self._pending:
                self._pending = True
                remaining = self.interval_ms - (current_time - self._last_trigger_time)
                self._timer.start(int(remaining))

    def _on_timeout(self):
        """定时器超时"""
        if self._pending:
            self._last_trigger_time = time.monotonic() * 1000
            self.triggered.emit()
            self._pending = False


def debounce(delay_ms: int = 300):
    """
    防抖装饰器 - 用于GUI方法

    Args:
        delay_ms: 延迟时间（毫秒）

    Example:
        @debounce(500)
        def on_text_changed(self):
            # 只在用户停止输入500ms后执行
            self.update_search_results()
    """

    def decorator(func: Callable) -> Callable:
        timer_attr = f"_debounce_timer_{func.__name__}"
        args_attr = f"_debounce_args_{func.__name__}"
        kwargs_attr = f"_debounce_kwargs_{func.__name__}"

        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            # 保存最新参数；定时器触发时仅执行最后一次调用
            setattr(self, args_attr, args)
            setattr(self, kwargs_attr, kwargs)

            timer = getattr(self, timer_attr, None)
            if timer is None:
                timer = QTimer(self)
                timer.setSingleShot(True)

                def _fire() -> None:
                    stored_args = getattr(self, args_attr, ())
                    stored_kwargs = getattr(self, kwargs_attr, {})
                    func(self, *stored_args, **stored_kwargs)

                # 只连接一次，避免重复 connect 导致回调累积/内存泄漏
                timer.timeout.connect(_fire)
                setattr(self, timer_attr, timer)

            # 停止之前的定时器
            timer.stop()

            timer.start(delay_ms)

        return wrapper

    return decorator


def throttle(interval_ms: int = 100):
    """
    节流装饰器 - 用于GUI方法

    Args:
        interval_ms: 时间间隔（毫秒）

    Example:
        @throttle(100)
        def on_scroll(self):
            # 最多每100ms执行一次
            self.update_visible_items()
    """

    def decorator(func: Callable) -> Callable:
        last_call_attr = f"_throttle_last_call_{func.__name__}"

        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            current_time = time.monotonic() * 1000  # 转换为毫秒（单调时钟）

            # 获取上次调用时间
            last_call_time = getattr(self, last_call_attr, 0)

            # 检查是否可以调用
            if current_time - last_call_time >= interval_ms:
                setattr(self, last_call_attr, current_time)
                return func(self, *args, **kwargs)

        return wrapper

    return decorator


def batch_updates(widget: QWidget):
    """
    批量更新上下文管理器 - 减少重绘次数

    Args:
        widget: 要更新的widget

    Example:
        with batch_updates(self.text_edit):
            self.text_edit.append("Line 1")
            self.text_edit.append("Line 2")
            self.text_edit.append("Line 3")
    """

    class BatchUpdatesContext:
        def __enter__(self):
            widget.setUpdatesEnabled(False)
            return widget

        def __exit__(self, exc_type, exc_val, exc_tb):
            widget.setUpdatesEnabled(True)
            widget.update()

    return BatchUpdatesContext()


def lazy_load(delay_ms: int = 100):
    """
    延迟加载装饰器 - 延迟执行耗时操作

    Args:
        delay_ms: 延迟时间（毫秒）

    Example:
        @lazy_load(200)
        def load_heavy_content(self):
            # 延迟200ms后加载，避免阻塞UI初始化
            self.load_images()
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            QTimer.singleShot(delay_ms, lambda: func(self, *args, **kwargs))

        return wrapper

    return decorator


class PerformanceMonitor:
    """GUI性能监控器"""

    def __init__(self, name: str):
        self.name = name
        self.start_time = 0
        self.end_time = 0

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.perf_counter()
        elapsed_ms = (self.end_time - self.start_time) * 1000

        if elapsed_ms > 16.67:  # 超过一帧时间（60fps）
            logger.warning(f"GUI操作 '{self.name}' 耗时 {elapsed_ms:.2f}ms (>16.67ms)")
        else:
            logger.debug(f"GUI操作 '{self.name}' 耗时 {elapsed_ms:.2f}ms")


def monitor_performance(func: Callable) -> Callable:
    """
    性能监控装饰器 - 监控GUI方法执行时间

    Example:
        @monitor_performance
        def update_ui(self):
            # 自动监控执行时间
            pass
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with PerformanceMonitor(func.__name__):
            return func(*args, **kwargs)

    return wrapper


class MemoryLeakDetector:
    """内存泄漏检测器 - 检测未释放的QObject"""

    def __init__(self):
        self._tracked_objects = {}

    def track(self, obj: QObject, name: str):
        """跟踪对象"""
        obj_id = id(obj)
        self._tracked_objects[obj_id] = {
            "name": name,
            "type": type(obj).__name__,
            "created_at": time.time(),
        }

        # 对象销毁时移除跟踪
        obj.destroyed.connect(lambda: self._on_object_destroyed(obj_id))

    def _on_object_destroyed(self, obj_id: int):
        """对象销毁回调"""
        if obj_id in self._tracked_objects:
            info = self._tracked_objects.pop(obj_id)
            lifetime = time.time() - info["created_at"]
            logger.debug(f"对象 {info['name']} ({info['type']}) 已销毁，生命周期: {lifetime:.2f}秒")

    def check_leaks(self):
        """检查潜在的内存泄漏"""
        current_time = time.time()
        leaks = []

        for obj_id, info in self._tracked_objects.items():
            lifetime = current_time - info["created_at"]
            if lifetime > 300:  # 超过5分钟
                leaks.append({"name": info["name"], "type": info["type"], "lifetime": lifetime})

        if leaks:
            logger.warning(f"检测到 {len(leaks)} 个潜在内存泄漏:")
            for leak in leaks:
                logger.warning(f"  - {leak['name']} ({leak['type']}): {leak['lifetime']:.2f}秒")

        return leaks


# 全局内存泄漏检测器
_memory_leak_detector = MemoryLeakDetector()


def track_object(obj: QObject, name: str):
    """
    跟踪对象生命周期

    Args:
        obj: 要跟踪的对象
        name: 对象名称
    """
    _memory_leak_detector.track(obj, name)


def check_memory_leaks():
    """检查内存泄漏"""
    return _memory_leak_detector.check_leaks()
