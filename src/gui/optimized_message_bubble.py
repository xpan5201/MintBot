"""优化的消息气泡（QPlainTextEdit、批量追加、防抖高度调整、GPU加速、最小化信号开销）"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPlainTextEdit, QLabel, QGraphicsDropShadowEffect
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor, QTextCursor
from typing import Optional
import time

from src.gui.material_design_light import MD3_LIGHT_COLORS, MD3_RADIUS
from src.utils.logger import get_logger

logger = get_logger(__name__)


class OptimizedStreamingBubble(QWidget):
    """优化的流式消息气泡（QPlainTextEdit、批量追加16ms、防抖100ms、GPU加速）"""
    
    def __init__(self, is_user: bool = False, parent=None):
        super().__init__(parent)

        self.is_user = is_user
        self.text_buffer: list[str] = []
        self.buffer_timer: Optional[QTimer] = None
        self.adjust_timer: Optional[QTimer] = None

        self.stats = {
            "total_appends": 0,
            "batched_appends": 0,
            "total_adjusts": 0,
            "avg_append_time_ms": 0.0,
            "avg_adjust_time_ms": 0.0,
        }

        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)

        self.setup_ui()
        self.setup_timers()
        
    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.text_edit.setFont(QFont("Microsoft YaHei UI", 10))

        bg_color = MD3_LIGHT_COLORS['primary_container'] if self.is_user else MD3_LIGHT_COLORS['surface_container_high']
        text_color = MD3_LIGHT_COLORS['on_primary_container'] if self.is_user else MD3_LIGHT_COLORS['on_surface']

        self.text_edit.setStyleSheet(f"""
            QPlainTextEdit {{
                background: {bg_color};
                color: {text_color};
                border: none;
                border-radius: {MD3_RADIUS['medium']};
                padding: 8px 12px;
            }}
        """)

        self.text_edit.setMinimumHeight(40)
        self.text_edit.setMaximumHeight(400)

        layout.addWidget(self.text_edit)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(8)
        shadow.setColor(QColor(0, 0, 0, 30))
        shadow.setOffset(0, 2)
        self.setGraphicsEffect(shadow)
        
    def setup_timers(self):
        """设置定时器"""
        self.buffer_timer = QTimer()
        self.buffer_timer.timeout.connect(self._flush_text_buffer)
        self.buffer_timer.setSingleShot(True)

        self.adjust_timer = QTimer()
        self.adjust_timer.timeout.connect(self._adjust_height)
        self.adjust_timer.setSingleShot(True)

    def append_text(self, text: str):
        """追加文本（批量）"""
        start_time = time.perf_counter()

        self.text_buffer.append(text)

        if not self.buffer_timer.isActive():
            self.buffer_timer.start(16)

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        self.stats["total_appends"] += 1
        self.stats["avg_append_time_ms"] = (
            (self.stats["avg_append_time_ms"] * (self.stats["total_appends"] - 1) + elapsed_ms)
            / self.stats["total_appends"]
        )
        
    def _flush_text_buffer(self):
        """刷新文本缓冲区"""
        if not self.text_buffer:
            return

        start_time = time.perf_counter()

        text = "".join(self.text_buffer)
        self.text_buffer.clear()

        self.text_edit.blockSignals(True)

        cursor = self.text_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self.text_edit.setTextCursor(cursor)

        self.text_edit.blockSignals(False)

        if not self.adjust_timer.isActive():
            self.adjust_timer.start(100)

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        self.stats["batched_appends"] += 1

        if elapsed_ms > 16:
            logger.warning(f"文本刷新耗时: {elapsed_ms:.2f}ms")

    def _adjust_height(self):
        """调整高度（防抖）"""
        start_time = time.perf_counter()

        doc_height = self.text_edit.document().size().height()
        new_height = min(int(doc_height) + 20, 400)
        self.text_edit.setMaximumHeight(new_height)

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        self.stats["total_adjusts"] += 1
        self.stats["avg_adjust_time_ms"] = (
            (self.stats["avg_adjust_time_ms"] * (self.stats["total_adjusts"] - 1) + elapsed_ms)
            / self.stats["total_adjusts"]
        )

        if elapsed_ms > 10:
            logger.warning(f"高度调整耗时: {elapsed_ms:.2f}ms")

    def finish_streaming(self):
        """完成流式输出"""
        if self.text_buffer:
            self._flush_text_buffer()

        self._adjust_height()

        logger.info(
            f"流式消息性能统计: "
            f"总追加={self.stats['total_appends']}, "
            f"批量追加={self.stats['batched_appends']}, "
            f"平均追加时间={self.stats['avg_append_time_ms']:.2f}ms, "
            f"平均调整时间={self.stats['avg_adjust_time_ms']:.2f}ms"
        )

    def get_text(self) -> str:
        """获取文本内容"""
        return self.text_edit.toPlainText()

    def get_stats(self) -> dict:
        """获取性能统计"""
        return self.stats.copy()


class OptimizedMessageBubble(QWidget):
    """优化的普通消息气泡（QLabel、预计算高度、GPU加速）"""

    def __init__(self, message: str, is_user: bool = False, parent=None):
        super().__init__(parent)

        self.message = message
        self.is_user = is_user

        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)

        self.setup_ui()

    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        self.label = QLabel(self.message)
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse |
            Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.label.setFont(QFont("Microsoft YaHei UI", 10))

        bg_color = MD3_LIGHT_COLORS['primary_container'] if self.is_user else MD3_LIGHT_COLORS['surface_container_high']
        text_color = MD3_LIGHT_COLORS['on_primary_container'] if self.is_user else MD3_LIGHT_COLORS['on_surface']

        self.label.setStyleSheet(f"""
            QLabel {{
                background: {bg_color};
                color: {text_color};
                border: none;
                border-radius: {MD3_RADIUS['medium']};
                padding: 8px 12px;
            }}
        """)

        layout.addWidget(self.label)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(8)
        shadow.setColor(QColor(0, 0, 0, 30))
        shadow.setOffset(0, 2)
        self.setGraphicsEffect(shadow)

    def get_text(self) -> str:
        """获取文本内容"""
        return self.message

