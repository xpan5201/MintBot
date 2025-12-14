"""聊天窗口优化器（智能渲染、批量滚动、懒加载、内存管理、GPU加速）"""

from PyQt6.QtWidgets import QWidget, QScrollArea
from typing import Optional, Callable
import time

from src.gui.performance_optimizer import (
    GPUAccelerator,
    BatchRenderer,
    MemoryManager,
    PerformanceMonitor,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ChatWindowOptimizer:
    """聊天窗口优化器（智能渲染、批量滚动、懒加载、内存管理、GPU加速、性能监控）"""

    def __init__(
        self,
        scroll_area: QScrollArea,
        enable_gpu: bool = True,
        enable_memory_management: bool = True,
        max_messages: int = 200,
        auto_scroll_predicate: Optional[Callable[[], bool]] = None,
    ):
        """初始化聊天窗口优化器"""
        self.scroll_area = scroll_area
        self._auto_scroll_predicate = auto_scroll_predicate
        
        # 批量渲染器
        self.batch_renderer = BatchRenderer(interval_ms=16)
        
        # 内存管理器
        self.memory_manager = None
        if enable_memory_management:
            self.memory_manager = MemoryManager(max_messages=max_messages)
        
        # 性能监控器
        self.performance_monitor = PerformanceMonitor()
        
        if enable_gpu:
            GPUAccelerator.enable_for_scroll_area(scroll_area)
            logger.info("已为聊天窗口启用GPU加速")
        
        # 滚动优化
        self.scroll_pending = False
        self._force_scroll_next = False
        
        # 性能统计
        self.stats = {
            "total_messages": 0,
            "optimized_messages": 0,
            "scroll_calls": 0,
            "batched_scrolls": 0,
        }

    def _flush_scheduled_scroll(self) -> None:
        """执行一次批量滚动（由 BatchRenderer 调度）。"""
        try:
            effective_force = bool(self._force_scroll_next)
            self._force_scroll_next = False

            predicate = self._auto_scroll_predicate
            if not effective_force and predicate is not None:
                try:
                    if not bool(predicate()):
                        return
                except Exception:
                    return

            scrollbar = self.scroll_area.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
            self.stats["batched_scrolls"] += 1
        finally:
            self.scroll_pending = False
        
    def add_message_optimized(
        self,
        message: str,
        is_user: bool,
        is_streaming: bool = False,
        callback: Optional[Callable] = None,
    ) -> QWidget:
        """添加优化的消息"""
        start_time = time.perf_counter()

        # 延迟导入：该模块在默认 LightChatWindow 路径下不会用到，避免启动时加载不必要的代码。
        from src.gui.optimized_message_bubble import (  # noqa: WPS433 - 局部导入用于性能
            OptimizedMessageBubble,
            OptimizedStreamingBubble,
        )

        bubble = (
            OptimizedStreamingBubble(is_user=is_user)
            if is_streaming
            else OptimizedMessageBubble(message, is_user=is_user)
        )

        self.performance_monitor.record_frame((time.perf_counter() - start_time) * 1000)

        self.stats["total_messages"] += 1
        self.stats["optimized_messages"] += 1

        if self.memory_manager:
            self.memory_manager.add_message(bubble)

        if callback:
            callback(bubble)

        self.schedule_scroll()

        return bubble
    
    def schedule_scroll(self, force: bool = False) -> None:
        """调度滚动（批量优化）

        Args:
            force: 是否强制滚动（忽略自动滚动锁）。
        """
        if self.scroll_pending:
            if force:
                # 已有批量滚动在路上时，标记为“强制滚动”，避免被自动滚动锁拦截
                self._force_scroll_next = True
            return

        if not force and self._auto_scroll_predicate is not None:
            try:
                if not bool(self._auto_scroll_predicate()):
                    return
            except Exception:
                # 兜底：谓词异常不影响主流程
                return

        self.scroll_pending = True
        self._force_scroll_next = bool(force)
        self.stats["scroll_calls"] += 1

        # 批量滚动（16ms 延迟，60fps）
        self.batch_renderer.schedule_update(self._flush_scheduled_scroll)
    
    def get_stats(self) -> dict:
        """获取性能统计"""
        perf_stats = self.performance_monitor.get_stats()
        
        return {
            **self.stats,
            "fps": perf_stats["fps"],
            "avg_frame_time_ms": perf_stats["avg_frame_time_ms"],
            "scroll_batch_ratio": (
                f"{self.stats['batched_scrolls'] / self.stats['scroll_calls'] * 100:.1f}%"
                if self.stats['scroll_calls'] > 0
                else "0%"
            ),
        }
    
    def optimize_existing_window(self, window):
        """优化现有聊天窗口"""
        logger.info("开始优化现有聊天窗口")

        if hasattr(window, 'scroll_area'):
            GPUAccelerator.enable_for_scroll_area(window.scroll_area)
            logger.info("已启用GPU加速")

        def optimized_scroll():
            self.schedule_scroll(force=False)

        window._scroll_to_bottom = optimized_scroll
        logger.info("已优化滚动方法")

        # 关键：自动滚动锁（用户上滑查看历史时不强制拉回底部）
        self._auto_scroll_predicate = lambda: bool(getattr(window, "_auto_scroll_enabled", True))

        window.performance_optimizer = self
        logger.info("已添加性能监控")

        logger.info("聊天窗口优化完成")
