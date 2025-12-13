"""
MintChat GUI - 动画消息气泡组件

提供带淡入动画的消息气泡，支持流式输出
遵循 Material Design 3 规范
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QGraphicsOpacityEffect
)
from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve,
    pyqtSignal, QTimer
)
from PyQt6.QtGui import QTextCursor

from .material_design import (
    MD3_COLORS, MD3_RADIUS, MD3_DURATION,
    get_typography_style
)


class AnimatedMessageBubble(QWidget):
    """带动画效果的消息气泡"""

    finished = pyqtSignal()

    def __init__(self, message: str = "", is_user: bool = False, parent=None):
        super().__init__(parent)
        self.message = message
        self.is_user = is_user
        self.is_streaming = False

        self._init_ui()
        self._apply_styles()
        self._setup_fade_in_animation()

    def _init_ui(self):
        """初始化 UI"""
        # 主布局
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(16, 8, 16, 8)

        # 根据发送者调整对齐方式
        if self.is_user:
            main_layout.addStretch()

        # 气泡容器
        bubble_widget = QWidget()
        bubble_widget.setObjectName("bubbleWidget")
        bubble_layout = QVBoxLayout(bubble_widget)
        bubble_layout.setContentsMargins(16, 12, 16, 12)
        bubble_layout.setSpacing(4)

        # 消息内容
        self.message_label = QLabel(self.message)
        self.message_label.setObjectName("messageLabel")
        self.message_label.setWordWrap(True)
        self.message_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.message_label.setMaximumWidth(500)
        bubble_layout.addWidget(self.message_label)

        # 时间戳
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M")
        self.time_label = QLabel(timestamp)
        self.time_label.setObjectName("timeLabel")
        self.time_label.setAlignment(
            Qt.AlignmentFlag.AlignRight if self.is_user
            else Qt.AlignmentFlag.AlignLeft
        )
        bubble_layout.addWidget(self.time_label)

        main_layout.addWidget(bubble_widget)

        # 根据发送者调整对齐方式
        if not self.is_user:
            main_layout.addStretch()

    def _apply_styles(self):
        """应用样式"""
        if self.is_user:
            bg_color = MD3_COLORS['primary_container']
            text_color = MD3_COLORS['on_primary_container']
        else:
            bg_color = MD3_COLORS['surface_container_high']
            text_color = MD3_COLORS['on_surface']

        self.setStyleSheet(f"""
            #bubbleWidget {{
                background-color: {bg_color};
                border-radius: {MD3_RADIUS['large']};
            }}

            #messageLabel {{
                color: {text_color};
                {get_typography_style('body_large')}
                background-color: transparent;
            }}

            #timeLabel {{
                color: {MD3_COLORS['on_surface_variant']};
                {get_typography_style('label_small')}
                background-color: transparent;
            }}
        """)

    def _setup_fade_in_animation(self):
        """设置淡入动画"""
        # 创建透明度效果
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)

        # 创建动画
        self.fade_in_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_in_animation.setDuration(MD3_DURATION['medium2'])
        self.fade_in_animation.setStartValue(0.0)
        self.fade_in_animation.setEndValue(1.0)
        self.fade_in_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)

    def show_with_animation(self):
        """显示时播放淡入动画"""
        self.fade_in_animation.start()

    def update_message(self, message: str):
        """更新消息内容"""
        self.message = message
        self.message_label.setText(message)


class StreamingMessageBubble(QWidget):
    """流式消息气泡（用于 AI 回复）"""

    finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.message = ""
        self.is_user = False

        self._init_ui()
        self._apply_styles()
        self._setup_fade_in_animation()

    def _init_ui(self):
        """初始化 UI"""
        # 主布局
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(16, 8, 16, 8)

        # 气泡容器
        bubble_widget = QWidget()
        bubble_widget.setObjectName("bubbleWidget")
        bubble_layout = QVBoxLayout(bubble_widget)
        bubble_layout.setContentsMargins(16, 12, 16, 12)
        bubble_layout.setSpacing(4)

        # 消息内容（使用 QTextEdit 支持流式输出）
        self.message_edit = QTextEdit()
        self.message_edit.setObjectName("messageEdit")
        self.message_edit.setReadOnly(True)
        self.message_edit.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.message_edit.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.message_edit.setMaximumWidth(500)
        self.message_edit.setMinimumHeight(40)
        bubble_layout.addWidget(self.message_edit)

        # 时间戳
        timestamp = datetime.now().strftime("%H:%M")
        self.time_label = QLabel(timestamp)
        self.time_label.setObjectName("timeLabel")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        bubble_layout.addWidget(self.time_label)

        main_layout.addWidget(bubble_widget)
        main_layout.addStretch()

    def _apply_styles(self):
        """应用样式"""
        self.setStyleSheet(f"""
            #bubbleWidget {{
                background-color: {MD3_COLORS['surface_container_high']};
                border-radius: {MD3_RADIUS['large']};
            }}

            #messageEdit {{
                color: {MD3_COLORS['on_surface']};
                {get_typography_style('body_large')}
                background-color: transparent;
                border: none;
            }}

            #timeLabel {{
                color: {MD3_COLORS['on_surface_variant']};
                {get_typography_style('label_small')}
                background-color: transparent;
            }}
        """)

    def _setup_fade_in_animation(self):
        """设置淡入动画"""
        # 创建透明度效果
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)

        # 创建动画
        self.fade_in_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_in_animation.setDuration(MD3_DURATION['medium2'])
        self.fade_in_animation.setStartValue(0.0)
        self.fade_in_animation.setEndValue(1.0)
        self.fade_in_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)

    def show_with_animation(self):
        """显示时播放淡入动画"""
        self.fade_in_animation.start()

    def append_text(self, text: str):
        """追加文本（流式输出）"""
        self.message += text
        cursor = self.message_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.message_edit.setTextCursor(cursor)
        self.message_edit.insertPlainText(text)
        self._adjust_height()

    def _adjust_height(self):
        """自动调整高度"""
        doc_height = self.message_edit.document().size().height()
        self.message_edit.setFixedHeight(int(doc_height) + 10)

    def get_message(self) -> str:
        """获取完整消息"""
        return self.message

    def finish(self):
        """完成流式输出"""
        self.finished.emit()


class TypingIndicator(QWidget):
    """打字指示器（三个跳动的点）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self._apply_styles()
        self._setup_animation()

    def _init_ui(self):
        """初始化 UI"""
        # 主布局
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(16, 8, 16, 8)

        # 气泡容器
        bubble_widget = QWidget()
        bubble_widget.setObjectName("bubbleWidget")
        bubble_layout = QHBoxLayout(bubble_widget)
        bubble_layout.setContentsMargins(16, 12, 16, 12)
        bubble_layout.setSpacing(4)

        # 三个点
        self.dot1 = QLabel("●")
        self.dot2 = QLabel("●")
        self.dot3 = QLabel("●")

        for dot in [self.dot1, self.dot2, self.dot3]:
            dot.setObjectName("dot")
            bubble_layout.addWidget(dot)

        main_layout.addWidget(bubble_widget)
        main_layout.addStretch()

    def _apply_styles(self):
        """应用样式"""
        self.setStyleSheet(f"""
            #bubbleWidget {{
                background-color: {MD3_COLORS['surface_container_high']};
                border-radius: {MD3_RADIUS['large']};
            }}

            #dot {{
                color: {MD3_COLORS['on_surface_variant']};
                font-size: 12px;
            }}
        """)

    def _setup_animation(self):
        """设置跳动动画"""
        # 为每个点创建透明度动画
        self.animations = []

        for i, dot in enumerate([self.dot1, self.dot2, self.dot3]):
            effect = QGraphicsOpacityEffect(dot)
            dot.setGraphicsEffect(effect)

            animation = QPropertyAnimation(effect, b"opacity")
            animation.setDuration(600)
            animation.setStartValue(0.3)
            animation.setEndValue(1.0)
            animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
            animation.setLoopCount(-1)  # 无限循环

            # 设置延迟
            QTimer.singleShot(i * 200, animation.start)

            self.animations.append(animation)

    def stop_animation(self):
        """停止动画"""
        for animation in self.animations:
            animation.stop()
