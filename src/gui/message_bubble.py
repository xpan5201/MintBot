"""
MintChat 消息气泡组件

提供类似 QQ 的消息气泡显示
"""

from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QTextEdit, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QTextCursor
from datetime import datetime
from .styles import THEME_COLORS


class MessageBubble(QWidget):
    """消息气泡组件"""

    def __init__(self, message: str, is_user: bool = False, timestamp: str = None, parent=None):
        """
        初始化消息气泡

        Args:
            message: 消息内容
            is_user: 是否为用户消息
            timestamp: 时间戳
            parent: 父组件
        """
        super().__init__(parent)
        self.message = message
        self.is_user = is_user
        self.timestamp = timestamp or datetime.now().strftime("%H:%M:%S")

        self._init_ui()

    def _init_ui(self):
        """初始化 UI"""
        # 主布局
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 5, 10, 5)

        # 根据是否为用户消息调整对齐方式
        if self.is_user:
            main_layout.addStretch()

        # 消息容器
        message_container = QWidget()
        message_layout = QVBoxLayout(message_container)
        message_layout.setContentsMargins(0, 0, 0, 0)
        message_layout.setSpacing(4)

        # 消息内容
        self.message_label = QLabel(self.message)
        self.message_label.setWordWrap(True)
        self.message_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.message_label.setMaximumWidth(500)

        # 设置样式
        bg_color = THEME_COLORS["bubble_user"] if self.is_user else THEME_COLORS["bubble_ai"]
        self.message_label.setStyleSheet(
            f"""
            QLabel {{
                background-color: {bg_color};
                color: {THEME_COLORS['text_primary']};
                border-radius: 8px;
                padding: 10px 14px;
            }}
        """
        )

        # 时间戳
        self.time_label = QLabel(self.timestamp)
        self.time_label.setStyleSheet(
            f"""
            QLabel {{
                color: {THEME_COLORS['text_secondary']};
                font-size: 11px;
            }}
        """
        )

        # 根据是否为用户消息调整时间戳位置
        if self.is_user:
            self.time_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        else:
            self.time_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        # 添加到布局
        message_layout.addWidget(self.message_label)
        message_layout.addWidget(self.time_label)

        main_layout.addWidget(message_container)

        if not self.is_user:
            main_layout.addStretch()

    def update_message(self, message: str):
        """
        更新消息内容（用于流式输出）

        Args:
            message: 新的消息内容
        """
        self.message = message
        self.message_label.setText(message)


class StreamingMessageBubble(QWidget):
    """流式消息气泡组件（支持实时更新）"""

    finished = pyqtSignal()  # 流式输出完成信号

    def __init__(self, is_user: bool = False, timestamp: str = None, parent=None):
        """
        初始化流式消息气泡

        Args:
            is_user: 是否为用户消息
            timestamp: 时间戳
            parent: 父组件
        """
        super().__init__(parent)
        self.is_user = is_user
        self.timestamp = timestamp or datetime.now().strftime("%H:%M:%S")
        self.message = ""

        self._init_ui()

    def _init_ui(self):
        """初始化 UI"""
        # 主布局
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 5, 10, 5)

        # 根据是否为用户消息调整对齐方式
        if self.is_user:
            main_layout.addStretch()

        # 消息容器
        message_container = QWidget()
        message_layout = QVBoxLayout(message_container)
        message_layout.setContentsMargins(0, 0, 0, 0)
        message_layout.setSpacing(4)

        # 消息内容（使用 QTextEdit 支持流式更新）
        self.message_edit = QTextEdit()
        self.message_edit.setReadOnly(True)
        self.message_edit.setMaximumWidth(500)
        self.message_edit.setMinimumHeight(40)
        self.message_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        # 设置样式
        bg_color = THEME_COLORS["bubble_user"] if self.is_user else THEME_COLORS["bubble_ai"]
        self.message_edit.setStyleSheet(
            f"""
            QTextEdit {{
                background-color: {bg_color};
                color: {THEME_COLORS['text_primary']};
                border: none;
                border-radius: 8px;
                padding: 10px 14px;
                font-size: 14px;
            }}
        """
        )

        # 禁用垂直滚动条（自动调整高度）
        self.message_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.message_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # 时间戳
        self.time_label = QLabel(self.timestamp)
        self.time_label.setStyleSheet(
            f"""
            QLabel {{
                color: {THEME_COLORS['text_secondary']};
                font-size: 11px;
            }}
        """
        )

        # 根据是否为用户消息调整时间戳位置
        if self.is_user:
            self.time_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        else:
            self.time_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        # 添加到布局
        message_layout.addWidget(self.message_edit)
        message_layout.addWidget(self.time_label)

        main_layout.addWidget(message_container)

        if not self.is_user:
            main_layout.addStretch()

    def append_text(self, text: str):
        """
        追加文本（流式输出）

        Args:
            text: 要追加的文本
        """
        self.message += text

        # 移动光标到末尾
        cursor = self.message_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.message_edit.setTextCursor(cursor)

        # 插入文本
        self.message_edit.insertPlainText(text)

        # 自动调整高度
        self._adjust_height()

    def _adjust_height(self):
        """自动调整高度以适应内容"""
        doc_height = self.message_edit.document().size().height()
        self.message_edit.setMaximumHeight(int(doc_height) + 20)

    def get_message(self) -> str:
        """
        获取完整消息

        Returns:
            str: 消息内容
        """
        return self.message

    def finish(self):
        """标记流式输出完成"""
        self.finished.emit()
