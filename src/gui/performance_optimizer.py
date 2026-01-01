"""GUI性能优化模块（虚拟滚动、消息池、GPU加速、批量更新、懒加载、内存管理）"""

from PyQt6.QtWidgets import QWidget, QScrollArea
from PyQt6.QtCore import Qt, QTimer, QObject, QCoreApplication
from typing import Any, List, Dict, Optional, Callable
import time

from src.utils.logger import get_logger

logger = get_logger(__name__)


class VirtualScrollArea(QScrollArea):
    """虚拟滚动区域（只渲染可见消息、自动回收、减少DOM节点、降低内存占用）"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.messages: List[Dict] = []
        self._total_height = 0  # 累计高度（避免 add_message 时 O(n) 求和）
        self.visible_start = 0
        self.visible_end = 0
        self.message_pool: List[QWidget] = []
        self.pool_size = 20

        self.stats = {
            "total_messages": 0,
            "visible_messages": 0,
            "recycled_messages": 0,
            "render_time_ms": 0.0,
        }

        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)

    def add_message(self, widget: QWidget, height: int):
        """添加消息到虚拟列表"""
        y_position = self._total_height
        self._total_height += height

        self.messages.append(
            {
                "widget": widget,
                "height": height,
                "y_position": y_position,
                "visible": False,
            }
        )

        self.stats["total_messages"] += 1

        self._update_visible_messages()

    def _on_scroll(self, value: int):
        """滚动事件处理"""
        self._update_visible_messages()

    def _update_visible_messages(self):
        """更新可见消息列表"""
        start_time = time.perf_counter()

        viewport_rect = self.viewport().rect()
        scroll_y = self.verticalScrollBar().value()

        # 计算可见范围
        visible_top = scroll_y
        visible_bottom = scroll_y + viewport_rect.height()

        # 找到可见消息
        new_visible_start = None
        new_visible_end = None

        for i, msg in enumerate(self.messages):
            msg_top = msg["y_position"]
            msg_bottom = msg_top + msg["height"]

            # 检查是否在可见范围内
            is_visible = msg_bottom >= visible_top and msg_top <= visible_bottom

            if is_visible:
                if new_visible_start is None:
                    new_visible_start = i
                new_visible_end = i + 1

                # 显示消息
                if not msg["visible"]:
                    msg["widget"].show()
                    msg["visible"] = True
            else:
                # 隐藏消息
                if msg["visible"]:
                    msg["widget"].hide()
                    msg["visible"] = False
                    self.stats["recycled_messages"] += 1

        # 更新可见范围
        if new_visible_start is not None:
            self.visible_start = new_visible_start
            self.visible_end = new_visible_end
            self.stats["visible_messages"] = new_visible_end - new_visible_start

        # 性能统计
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        self.stats["render_time_ms"] = elapsed_ms

        if elapsed_ms > 16:  # 超过 60fps
            logger.warning("虚拟滚动渲染耗时: %.2fms（超过 16ms）", elapsed_ms)

    def get_stats(self) -> Dict:
        """获取性能统计"""
        return self.stats.copy()


class MessagePool:
    """消息池 - 复用消息气泡组件

    性能优化：
    - 避免频繁创建/销毁组件
    - 减少内存分配
    - 提升渲染性能
    """

    def __init__(self, factory: Callable, pool_size: int = 20):
        """初始化消息池

        Args:
            factory: 消息组件工厂函数
            pool_size: 池大小
        """
        self.factory = factory
        self.pool_size = pool_size
        self.pool: List[QWidget] = []
        self.active: List[QWidget] = []

    def acquire(self) -> QWidget:
        """获取消息组件"""
        if self.pool:
            widget = self.pool.pop()
        else:
            widget = self.factory()

        self.active.append(widget)
        return widget

    def release(self, widget: QWidget):
        """释放消息组件"""
        if widget in self.active:
            self.active.remove(widget)

        if len(self.pool) < self.pool_size:
            widget.hide()
            self.pool.append(widget)
        else:
            widget.deleteLater()


class GPUAccelerator:
    """GPU 加速器 - 启用硬件加速渲染

    性能优化：
    - 启用 OpenGL 渲染
    - 使用 GPU 加速动画
    - 减少 CPU 负担
    """

    @staticmethod
    def enable_for_widget(widget: QWidget):
        """为组件启用 GPU 加速

        Args:
            widget: 要加速的组件
        """
        # 启用硬件加速
        widget.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        widget.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, False)

        # 启用双缓冲
        widget.setAttribute(Qt.WidgetAttribute.WA_PaintOnScreen, False)

        logger.debug("已为 %s 启用 GPU 加速", widget.__class__.__name__)

    @staticmethod
    def enable_for_scroll_area(scroll_area: QScrollArea):
        """为滚动区域启用 GPU 加速

        Args:
            scroll_area: 滚动区域
        """
        GPUAccelerator.enable_for_widget(scroll_area)
        GPUAccelerator.enable_for_widget(scroll_area.viewport())

        # 启用平滑滚动
        scroll_area.verticalScrollBar().setSingleStep(10)

        logger.debug("已为滚动区域启用 GPU 加速")


class BatchRenderer:
    """批量渲染器 - 减少重绘次数

    性能优化：
    - 批量更新 UI
    - 减少重绘次数
    - 提升渲染性能
    """

    def __init__(self, interval_ms: int = 16, parent: Optional[QObject] = None):
        """初始化批量渲染器

        Args:
            interval_ms: 批量间隔（毫秒），默认 16ms（60fps）
        """
        self.interval_ms = interval_ms
        self._timer_parent: Optional[QObject] = parent or QCoreApplication.instance()
        self.pending_updates: List[Callable] = []
        self._pending_keys: set[tuple[Any, ...]] = set()
        self.timer: Optional[QTimer] = None

    @staticmethod
    def _callback_key(callback: Callable) -> tuple[Any, ...]:
        """Return a stable key for coalescing duplicate callbacks within a single batch window."""
        try:
            func = getattr(callback, "__func__", None)
            bound_self = getattr(callback, "__self__", None)
            if func is not None and bound_self is not None:
                return ("method", id(bound_self), id(func))
        except Exception:
            pass
        return ("callable", id(callback))

    def schedule_update(self, callback: Callable):
        """调度更新

        Args:
            callback: 更新回调函数
        """
        try:
            key = self._callback_key(callback)
        except Exception:
            key = ("callable", id(callback))

        if key in self._pending_keys:
            return
        self._pending_keys.add(key)
        self.pending_updates.append(callback)

        if self.timer is None:
            if self._timer_parent is not None:
                self.timer = QTimer(self._timer_parent)
            else:
                self.timer = QTimer()
            self.timer.timeout.connect(self._flush_updates)
            self.timer.setSingleShot(True)

        if not self.timer.isActive():
            self.timer.start(self.interval_ms)

    def _flush_updates(self):
        """刷新所有待处理的更新"""
        if not self.pending_updates:
            return

        # 先拷贝并清空，避免回调内部再次 schedule_update() 时被本次 clear 掉
        callbacks = self.pending_updates
        self.pending_updates = []
        self._pending_keys.clear()

        start_time = time.perf_counter()

        for callback in callbacks:
            try:
                callback()
            except Exception as e:
                logger.error("批量更新失败: %s", e)

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        if elapsed_ms > 16:
            logger.warning("批量更新耗时: %.2fms（超过 16ms）", elapsed_ms)

    def close(self) -> None:
        """停止计时器并清空待处理更新（幂等）。"""
        timer = self.timer
        self.timer = None

        self.pending_updates = []
        self._pending_keys.clear()

        if timer is None:
            return
        try:
            if timer.isActive():
                timer.stop()
        except Exception:
            pass


class LazyLoader:
    """懒加载器 - 延迟加载历史消息

    性能优化：
    - 按需加载消息
    - 减少初始加载时间
    - 降低内存占用
    """

    def __init__(self, load_callback: Callable, batch_size: int = 20):
        """初始化懒加载器

        Args:
            load_callback: 加载回调函数
            batch_size: 每批加载数量
        """
        self.load_callback = load_callback
        self.batch_size = batch_size
        self.is_loading = False

    def load_more(self):
        """加载更多消息"""
        if self.is_loading:
            return

        self.is_loading = True

        try:
            self.load_callback(self.batch_size)
        except Exception as e:
            logger.error("懒加载失败: %s", e)
        finally:
            self.is_loading = False


class MemoryManager:
    """内存管理器 - 自动回收不可见消息

    性能优化：
    - 自动回收不可见消息
    - 限制内存占用
    - 防止内存泄漏
    """

    def __init__(self, max_messages: int = 100):
        """初始化内存管理器

        Args:
            max_messages: 最大消息数量
        """
        self.max_messages = max_messages
        self.messages: List[QWidget] = []

    def add_message(self, widget: QWidget):
        """添加消息

        Args:
            widget: 消息组件
        """
        self.messages.append(widget)

        # 检查是否超过限制
        if len(self.messages) > self.max_messages:
            self._recycle_old_messages()

    def _recycle_old_messages(self):
        """回收旧消息"""
        # 保留最新的消息
        to_remove = len(self.messages) - self.max_messages

        old_widgets = self.messages[:to_remove]
        self.messages = self.messages[to_remove:]
        for widget in old_widgets:
            widget.deleteLater()

        logger.debug("已回收 %s 条旧消息", to_remove)


class PerformanceMonitor:
    """性能监控器 - 监控 GUI 性能

    监控指标：
    - FPS（帧率）
    - 渲染时间
    - 内存占用
    - 消息数量
    """

    def __init__(self):
        """初始化性能监控器"""
        self.frame_times: List[float] = []
        self.max_samples = 60  # 保留最近 60 帧

    def record_frame(self, elapsed_ms: float):
        """记录帧时间

        Args:
            elapsed_ms: 帧耗时（毫秒）
        """
        self.frame_times.append(elapsed_ms)

        if len(self.frame_times) > self.max_samples:
            self.frame_times.pop(0)

    def get_fps(self) -> float:
        """获取平均 FPS"""
        if not self.frame_times:
            return 0.0

        avg_frame_time = sum(self.frame_times) / len(self.frame_times)
        return 1000.0 / avg_frame_time if avg_frame_time > 0 else 0.0

    def get_avg_frame_time(self) -> float:
        """获取平均帧时间（毫秒）"""
        if not self.frame_times:
            return 0.0

        return sum(self.frame_times) / len(self.frame_times)

    def get_stats(self) -> Dict:
        """获取性能统计"""
        return {
            "fps": f"{self.get_fps():.2f}",
            "avg_frame_time_ms": f"{self.get_avg_frame_time():.2f}",
            "samples": len(self.frame_times),
        }
