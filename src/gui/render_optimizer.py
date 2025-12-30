"""
MintChat GUI - 渲染性能优化模块

v2.30.27 新增：优化GUI渲染性能，减少不必要的重绘
- 批量文本更新
- 防抖高度调整
- 虚拟滚动支持
"""

from PyQt6.QtCore import QTimer, QCoreApplication
from typing import Callable, Optional
import time

from src.utils.logger import get_logger

logger = get_logger(__name__)


class RenderOptimizer:
    """GUI渲染优化器 - v2.30.27"""

    def __init__(self):
        """初始化渲染优化器"""
        # 文本缓冲区
        self.text_buffer = []
        self.buffer_timer: Optional[QTimer] = None
        self.flush_callback: Optional[Callable] = None

        # 防抖定时器
        self.debounce_timers = {}

        # 性能统计
        self.stats = {
            "total_updates": 0,
            "batched_updates": 0,
            "debounced_calls": 0,
            "avg_batch_size": 0.0,
        }

    def setup_text_batching(
        self,
        flush_callback: Callable[[str], None],
        batch_interval_ms: int = 16,  # ~60fps
    ):
        """
        设置文本批量更新

        Args:
            flush_callback: 刷新回调函数，接收批量文本
            batch_interval_ms: 批量间隔（毫秒），默认16ms（60fps）
        """
        self.flush_callback = flush_callback
        self.buffer_timer = QTimer()
        try:
            parent = QCoreApplication.instance()
            if parent is not None:
                self.buffer_timer.setParent(parent)
        except Exception:
            pass
        self.buffer_timer.timeout.connect(self._flush_text_buffer)
        self.buffer_timer.setInterval(batch_interval_ms)

    def add_text(self, text: str):
        """
        添加文本到缓冲区

        Args:
            text: 要添加的文本
        """
        if not self.flush_callback:
            logger.warning("文本批量更新未设置，直接返回")
            return

        self.text_buffer.append(text)

        # 启动定时器（如果未运行）
        if self.buffer_timer and not self.buffer_timer.isActive():
            self.buffer_timer.start()

    def _flush_text_buffer(self):
        """刷新文本缓冲区"""
        if not self.text_buffer:
            if self.buffer_timer:
                self.buffer_timer.stop()
            return

        # 合并所有文本
        batched_text = "".join(self.text_buffer)
        self.text_buffer.clear()

        # 统计
        self.stats["total_updates"] += 1
        self.stats["batched_updates"] += 1
        batch_size = len(batched_text)
        self.stats["avg_batch_size"] = (
            self.stats["avg_batch_size"] * (self.stats["batched_updates"] - 1) + batch_size
        ) / self.stats["batched_updates"]

        # 调用回调
        if self.flush_callback:
            self.flush_callback(batched_text)

        logger.debug("批量文本更新: %d 字符", batch_size)

    def debounce(
        self,
        key: str,
        callback: Callable,
        delay_ms: int = 100,
    ):
        """
        防抖函数调用

        Args:
            key: 防抖键（用于区分不同的防抖任务）
            callback: 回调函数
            delay_ms: 延迟时间（毫秒）
        """
        # 取消之前的定时器
        if key in self.debounce_timers:
            old_timer = self.debounce_timers[key]
            if old_timer.isActive():
                old_timer.stop()

        # 创建新定时器
        timer = QTimer()
        try:
            parent = QCoreApplication.instance()
            if parent is not None:
                timer.setParent(parent)
        except Exception:
            pass
        timer.setSingleShot(True)
        timer.timeout.connect(callback)
        timer.timeout.connect(lambda: self._on_debounce_executed(key))
        timer.start(delay_ms)

        self.debounce_timers[key] = timer

    def _on_debounce_executed(self, key: str):
        """防抖执行完成"""
        self.stats["debounced_calls"] += 1
        if key in self.debounce_timers:
            del self.debounce_timers[key]

    def throttle(
        self,
        key: str,
        callback: Callable,
        interval_ms: int = 100,
    ) -> bool:
        """
        节流函数调用

        Args:
            key: 节流键
            callback: 回调函数
            interval_ms: 间隔时间（毫秒）

        Returns:
            bool: 是否执行了回调
        """
        current_time = time.time() * 1000  # 转换为毫秒

        # 检查上次执行时间
        last_time_key = f"_throttle_last_{key}"
        if not hasattr(self, last_time_key):
            setattr(self, last_time_key, 0)

        last_time = getattr(self, last_time_key)

        if current_time - last_time >= interval_ms:
            callback()
            setattr(self, last_time_key, current_time)
            return True

        return False

    def get_stats(self) -> dict:
        """获取性能统计"""
        return {
            **self.stats,
            "avg_batch_size": round(self.stats["avg_batch_size"], 2),
        }

    def cleanup(self):
        """清理资源"""
        if self.buffer_timer:
            self.buffer_timer.stop()

        for timer in self.debounce_timers.values():
            if timer.isActive():
                timer.stop()

        self.debounce_timers.clear()
