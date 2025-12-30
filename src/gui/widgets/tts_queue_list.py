"""
TTS队列列表组件 - v2.39.0

显示TTS队列中的所有句子，支持拖拽排序和删除。

核心功能:
- 队列列表显示
- 拖拽排序 (v2.39.0 增强)
- 删除句子
- 状态显示
- Material Design 3样式
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData, QPoint
from PyQt6.QtGui import QFont, QDrag, QCursor, QMouseEvent
from typing import List, Dict, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)


class TTSQueueItem(QWidget):
    """TTS队列项 (v2.39.0)"""

    # 信号
    delete_clicked = pyqtSignal(int)  # 删除按钮点击 (索引)
    drag_started = pyqtSignal(int)  # 拖拽开始 (索引) - v2.39.0

    def __init__(self, index: int, text: str, status: str = "pending", parent=None):
        super().__init__(parent)
        self.index = index
        self.text = text
        self.status = status

        # v2.39.0: 拖拽相关
        self._drag_start_position: Optional[QPoint] = None
        self._is_dragging = False

        self.setup_ui()

    def setup_ui(self):
        """设置UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        # 状态图标
        status_icon = self._get_status_icon()
        status_label = QLabel(status_icon)
        status_label.setFixedWidth(20)
        layout.addWidget(status_label)

        # 文本
        text_label = QLabel(self.text[:50] + "..." if len(self.text) > 50 else self.text)
        text_label.setWordWrap(False)
        text_label.setStyleSheet("color: white; font-size: 9pt;")
        layout.addWidget(text_label, 1)

        # 删除按钮
        delete_btn = QPushButton("🗑")
        delete_btn.setFixedSize(24, 24)
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.clicked.connect(lambda: self.delete_clicked.emit(self.index))
        delete_btn.setStyleSheet(
            """
            QPushButton {
                background: rgba(255, 107, 157, 0.2);
                border: 1px solid rgba(255, 107, 157, 0.3);
                border-radius: 12px;
                color: white;
                font-size: 10pt;
            }
            QPushButton:hover {
                background: rgba(255, 107, 157, 0.3);
            }
        """
        )
        layout.addWidget(delete_btn)

        # 设置样式
        self.setStyleSheet(
            """
            TTSQueueItem {
                background: rgba(0, 0, 0, 0.2);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
            }
            TTSQueueItem:hover {
                background: rgba(0, 0, 0, 0.3);
                border: 1px solid rgba(255, 255, 255, 0.2);
            }
        """
        )

    def _get_status_icon(self) -> str:
        """获取状态图标"""
        icons = {
            "pending": "⏳",  # 等待中
            "processing": "🔄",  # 处理中
            "completed": "✅",  # 已完成
            "error": "❌",  # 错误
        }
        return icons.get(self.status, "⏳")

    def update_status(self, status: str):
        """更新状态"""
        self.status = status
        # 更新状态图标
        status_label = self.layout().itemAt(0).widget()
        if status_label:
            status_label.setText(self._get_status_icon())

    def mousePressEvent(self, event: QMouseEvent):
        """鼠标按下事件 - 开始拖拽 (v2.39.0)"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_position = event.pos()
            self._is_dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        """鼠标移动事件 - 执行拖拽 (v2.39.0)"""
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return

        if self._drag_start_position is None:
            return

        # 检查是否移动了足够的距离
        if (event.pos() - self._drag_start_position).manhattanLength() < 10:
            return

        # 开始拖拽
        if not self._is_dragging:
            self._is_dragging = True
            self.drag_started.emit(self.index)

            # 创建拖拽对象
            drag = QDrag(self)
            mime_data = QMimeData()
            mime_data.setText(str(self.index))
            drag.setMimeData(mime_data)

            # 设置鼠标样式
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))

            # 执行拖拽
            drag.exec(Qt.DropAction.MoveAction)

            # 恢复鼠标样式
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

            logger.debug(f"拖拽队列项: index={self.index}")

    def mouseReleaseEvent(self, event: QMouseEvent):
        """鼠标释放事件 - 结束拖拽 (v2.39.0)"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_position = None
            self._is_dragging = False
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        super().mouseReleaseEvent(event)


class TTSQueueList(QWidget):
    """TTS队列列表 (v2.39.0)"""

    # 信号
    item_deleted = pyqtSignal(int)  # 项目删除 (索引)
    item_moved = pyqtSignal(int, int)  # 项目移动 (from_index, to_index)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items: List[TTSQueueItem] = []

        # v2.39.0: 拖拽相关
        self._drag_source_index: Optional[int] = None
        self.setAcceptDrops(True)

        self.setup_ui()

    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        # 标题
        title_label = QLabel("📋 TTS队列")
        title_font = QFont()
        title_font.setPointSize(10)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)

        # 分隔线
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet("background: rgba(255, 255, 255, 0.1);")
        layout.addWidget(separator)

        # 列表容器
        self.list_layout = QVBoxLayout()
        self.list_layout.setSpacing(4)
        layout.addLayout(self.list_layout)

        # 空状态提示
        self.empty_label = QLabel("队列为空")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: rgba(255, 255, 255, 0.5); font-size: 9pt;")
        layout.addWidget(self.empty_label)

        layout.addStretch()

        # 设置面板样式
        self.setStyleSheet(
            """
            TTSQueueList {
                background: rgba(0, 0, 0, 0.3);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
            }
        """
        )

    def add_item(self, text: str, status: str = "pending"):
        """
        添加队列项 (v2.39.0)

        Args:
            text: 文本内容
            status: 状态 (pending/processing/completed/error)
        """
        index = len(self.items)
        item = TTSQueueItem(index, text, status)
        item.delete_clicked.connect(self._on_item_deleted)
        item.drag_started.connect(self._on_drag_started)  # v2.39.0

        self.items.append(item)
        self.list_layout.addWidget(item)

        # 隐藏空状态提示
        self.empty_label.setVisible(False)

        logger.debug(f"添加队列项: {text[:30]}...")

    def remove_item(self, index: int):
        """
        删除队列项 (v2.38.0)

        Args:
            index: 项目索引
        """
        if 0 <= index < len(self.items):
            item = self.items.pop(index)
            self.list_layout.removeWidget(item)
            item.deleteLater()

            # 更新索引
            for i, item in enumerate(self.items):
                item.index = i

            # 显示空状态提示
            if len(self.items) == 0:
                self.empty_label.setVisible(True)

            logger.debug(f"删除队列项: index={index}")

    def clear(self):
        """清空队列 (v2.38.0)"""
        for item in self.items:
            self.list_layout.removeWidget(item)
            item.deleteLater()

        self.items.clear()
        self.empty_label.setVisible(True)

        logger.debug("清空队列")

    def update_item_status(self, index: int, status: str):
        """
        更新项目状态 (v2.38.0)

        Args:
            index: 项目索引
            status: 新状态
        """
        if 0 <= index < len(self.items):
            self.items[index].update_status(status)
            logger.debug(f"更新队列项状态: index={index}, status={status}")

    def get_items(self) -> List[Dict]:
        """
        获取所有队列项 (v2.38.0)

        Returns:
            队列项列表
        """
        return [
            {
                "index": item.index,
                "text": item.text,
                "status": item.status,
            }
            for item in self.items
        ]

    def _on_item_deleted(self, index: int):
        """项目删除处理 (v2.38.0)"""
        self.remove_item(index)
        self.item_deleted.emit(index)

    def _on_drag_started(self, index: int):
        """拖拽开始处理 (v2.39.0)"""
        self._drag_source_index = index
        logger.debug(f"拖拽开始: index={index}")

    def dragEnterEvent(self, event):
        """拖拽进入事件 (v2.39.0)"""
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        """拖拽移动事件 (v2.39.0)"""
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        """拖放事件 (v2.39.0)"""
        if not event.mimeData().hasText():
            return

        # 获取源索引
        source_index = self._drag_source_index
        if source_index is None:
            return

        # 计算目标索引
        drop_pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        target_index = self._get_drop_index(drop_pos)

        if target_index is None or source_index == target_index:
            return

        # 移动项目
        self.move_item(source_index, target_index)

        # 发送信号
        self.item_moved.emit(source_index, target_index)

        # 清除拖拽状态
        self._drag_source_index = None

        event.acceptProposedAction()
        logger.debug(f"拖放完成: {source_index} -> {target_index}")

    def _get_drop_index(self, pos: QPoint) -> Optional[int]:
        """
        获取拖放目标索引 (v2.39.0)

        Args:
            pos: 拖放位置

        Returns:
            目标索引，如果无效则返回None
        """
        for i, item in enumerate(self.items):
            item_rect = item.geometry()
            if item_rect.contains(pos):
                # 判断是插入到上方还是下方
                if pos.y() < item_rect.center().y():
                    return i
                else:
                    return i + 1

        # 如果在所有项目下方，插入到末尾
        if len(self.items) > 0:
            last_item = self.items[-1]
            if pos.y() > last_item.geometry().bottom():
                return len(self.items)

        return None

    def move_item(self, from_index: int, to_index: int):
        """
        移动队列项 (v2.39.0)

        Args:
            from_index: 源索引
            to_index: 目标索引
        """
        if from_index < 0 or from_index >= len(self.items):
            return

        if to_index < 0 or to_index > len(self.items):
            return

        if from_index == to_index:
            return

        # 移除项目
        item = self.items.pop(from_index)
        self.list_layout.removeWidget(item)

        # 调整目标索引
        if to_index > from_index:
            to_index -= 1

        # 插入到新位置
        self.items.insert(to_index, item)
        self.list_layout.insertWidget(to_index, item)

        # 更新所有项目的索引
        for i, item in enumerate(self.items):
            item.index = i

        logger.debug(f"移动队列项: {from_index} -> {to_index}")
