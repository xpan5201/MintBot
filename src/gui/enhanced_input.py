"""
增强输入框组件 (v2.15.0 增强版)

基于 Material Design 3 最新规范
优化交互反馈、视觉层次、性能
增强用户体验和可访问性
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QLabel,
)
from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, pyqtSignal, pyqtProperty
)

from .material_design_light import (
    MD3_LIGHT_COLORS, MD3_RADIUS, MD3_DURATION
)
from .material_design_enhanced import (
    MD3_ENHANCED_COLORS, MD3_ENHANCED_SPACING, MD3_ENHANCED_RADIUS,
    MD3_ENHANCED_DURATION, MD3_ENHANCED_EASING, get_typography_css
)
from .material_icons import MaterialIcon


class EnhancedTextInput(QTextEdit):
    """增强文本输入框 - v2.15.0 优化版"""

    # 信号
    text_changed = pyqtSignal(str)  # 文本改变
    send_requested = pyqtSignal()  # 请求发送（Ctrl+Enter）

    def __init__(self, placeholder: str = "输入消息...", max_chars: int = 2000, parent=None):
        super().__init__(parent)
        self.placeholder = placeholder
        self.max_chars = max_chars

        # 聚焦状态
        self._is_focused = False
        self._focus_opacity = 0.0
        self._border_width = 1.0

        # 设置基本属性
        self.setPlaceholderText(placeholder)
        self.setMaximumHeight(150)  # 增加最大高度
        self.setMinimumHeight(48)   # 符合MD3最小触摸目标

        # 设置样式
        self.setup_style()

        # 设置动画
        self.setup_animations()

        # 连接信号
        self.textChanged.connect(self._on_text_changed)

    def setup_style(self):
        """设置样式 - 使用增强的设计系统"""
        self.setStyleSheet(f"""
            QTextEdit {{
                background: {MD3_ENHANCED_COLORS['surface_container']};
                color: {MD3_ENHANCED_COLORS['on_surface']};
                border: 1px solid {MD3_ENHANCED_COLORS['outline']};
                border-radius: {MD3_ENHANCED_RADIUS['lg']};
                padding: {MD3_ENHANCED_SPACING['3']} {MD3_ENHANCED_SPACING['4']};
                {get_typography_css('body_large')}
            }}
            QTextEdit:focus {{
                border: 2px solid {MD3_ENHANCED_COLORS['primary']};
                background: {MD3_ENHANCED_COLORS['surface_container_high']};
            }}
        """)

    def setup_animations(self):
        """设置动画 - 优化流畅度"""
        # 聚焦动画
        self.focus_animation = QPropertyAnimation(self, b"focus_opacity")
        self.focus_animation.setDuration(MD3_ENHANCED_DURATION["normal"])
        self.focus_animation.setEasingCurve(MD3_ENHANCED_EASING["emphasized_decelerate"])

        # 边框动画
        self.border_animation = QPropertyAnimation(self, b"border_width")
        self.border_animation.setDuration(MD3_ENHANCED_DURATION["fast"])
        self.border_animation.setEasingCurve(MD3_ENHANCED_EASING["smooth_out"])

    @pyqtProperty(float)
    def focus_opacity(self):
        return self._focus_opacity

    @focus_opacity.setter
    def focus_opacity(self, value):
        self._focus_opacity = value
        self.update()

    def focusInEvent(self, event):
        """聚焦事件"""
        super().focusInEvent(event)
        self._is_focused = True

        # 启动聚焦动画
        self.focus_animation.setStartValue(self._focus_opacity)
        self.focus_animation.setEndValue(1.0)
        self.focus_animation.start()

    def focusOutEvent(self, event):
        """失焦事件"""
        super().focusOutEvent(event)
        self._is_focused = False

        # 启动失焦动画
        self.focus_animation.setStartValue(self._focus_opacity)
        self.focus_animation.setEndValue(0.0)
        self.focus_animation.start()

    def keyPressEvent(self, event):
        """按键事件"""
        # Ctrl+Enter 发送
        if event.key() == Qt.Key.Key_Return and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.send_requested.emit()
            return

        # 检查字符限制
        if len(self.toPlainText()) >= self.max_chars and event.key() not in [
            Qt.Key.Key_Backspace, Qt.Key.Key_Delete, Qt.Key.Key_Left, Qt.Key.Key_Right
        ]:
            return

        super().keyPressEvent(event)

    def _on_text_changed(self):
        """文本改变事件"""
        text = self.toPlainText()

        # 限制字符数
        if len(text) > self.max_chars:
            cursor = self.textCursor()
            cursor.deletePreviousChar()
            self.setTextCursor(cursor)
            text = self.toPlainText()

        self.text_changed.emit(text)

        # 自动调整高度
        doc_height = self.document().size().height()
        new_height = min(max(40, int(doc_height) + 24), 120)
        self.setFixedHeight(new_height)


class SmartSendButton(QPushButton):
    """智能发送按钮 - 根据输入状态自动启用/禁用"""

    def __init__(self, parent=None):
        super().__init__(parent)

        # 状态
        self._is_sending = False
        self._scale = 1.0

        # 设置固定大小
        self.setFixedSize(90, 36)

        # 设置样式
        self.setup_style()

        # 设置动画
        self.setup_animations()

        # 设置图标和文本
        self.setup_content()

    def setup_content(self):
        """设置内容"""
        # 创建布局
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(6)

        # 发送图标
        self.icon = MaterialIcon("send", 18)
        self.icon.setStyleSheet(f"color: {MD3_LIGHT_COLORS['on_primary']};")
        layout.addWidget(self.icon)

        # 发送文本
        self.text_label = QLabel("发送")
        self.text_label.setStyleSheet(f"""
            QLabel {{
                color: {MD3_LIGHT_COLORS['on_primary']};
                font-size: 14px;
                font-weight: 500;
                background: transparent;
            }}
        """)
        layout.addWidget(self.text_label)

    def setup_style(self):
        """设置样式"""
        self.setStyleSheet(f"""
            QPushButton {{
                background: {MD3_LIGHT_COLORS['gradient_mint_cyan']};
                border: none;
                border-radius: {MD3_RADIUS['full']};
            }}
            QPushButton:hover {{
                background: {MD3_LIGHT_COLORS['primary']};
            }}
            QPushButton:pressed {{
                background: {MD3_LIGHT_COLORS['primary_light']};
            }}
            QPushButton:disabled {{
                background: {MD3_LIGHT_COLORS['surface_container']};
                opacity: 0.5;
            }}
        """)

    def setup_animations(self):
        """设置动画"""
        # 按压动画
        self.press_animation = QPropertyAnimation(self, b"scale")
        self.press_animation.setDuration(MD3_DURATION["short3"])
        self.press_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    @pyqtProperty(float)
    def scale(self):
        return self._scale

    @scale.setter
    def scale(self, value):
        self._scale = value
        self.update()

    def mousePressEvent(self, event):
        """鼠标按下"""
        super().mousePressEvent(event)

        if self.isEnabled():
            self.press_animation.setStartValue(1.0)
            self.press_animation.setEndValue(0.95)
            self.press_animation.start()

    def mouseReleaseEvent(self, event):
        """鼠标释放"""
        super().mouseReleaseEvent(event)

        if self.isEnabled():
            self.press_animation.setStartValue(0.95)
            self.press_animation.setEndValue(1.0)
            self.press_animation.start()

    def set_sending(self, is_sending: bool):
        """设置发送状态"""
        self._is_sending = is_sending
        self.setEnabled(not is_sending)

        if is_sending:
            self.text_label.setText("发送中...")
        else:
            self.text_label.setText("发送")


class EnhancedInputArea(QWidget):
    """增强输入区域 - 集成输入框、字符计数、发送按钮"""

    # 信号
    send_requested = pyqtSignal(str)  # 请求发送消息

    def __init__(self, parent=None):
        super().__init__(parent)

        # 设置 UI
        self.setup_ui()

        # 连接信号
        self.input_text.text_changed.connect(self._on_text_changed)
        self.input_text.send_requested.connect(self._on_send_requested)
        self.send_btn.clicked.connect(self._on_send_requested)

    def setup_ui(self):
        """设置 UI"""
        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(8)

        # 输入框和按钮行
        input_row = QHBoxLayout()
        input_row.setSpacing(12)

        # 增强输入框
        self.input_text = EnhancedTextInput()
        input_row.addWidget(self.input_text, 1)

        # 智能发送按钮
        self.send_btn = SmartSendButton()
        self.send_btn.setEnabled(False)  # 初始禁用
        input_row.addWidget(self.send_btn)

        main_layout.addLayout(input_row)

        # 底部信息行
        info_row = QHBoxLayout()
        info_row.setSpacing(8)

        # 提示文本
        self.hint_label = QLabel("Ctrl+Enter 发送")
        self.hint_label.setStyleSheet(f"""
            QLabel {{
                color: {MD3_LIGHT_COLORS['on_surface_variant']};
                font-size: 12px;
                background: transparent;
            }}
        """)
        info_row.addWidget(self.hint_label)

        info_row.addStretch()

        # 字符计数
        self.char_count_label = QLabel("0/2000")
        self.char_count_label.setStyleSheet(f"""
            QLabel {{
                color: {MD3_LIGHT_COLORS['on_surface_variant']};
                font-size: 12px;
                background: transparent;
            }}
        """)
        info_row.addWidget(self.char_count_label)

        main_layout.addLayout(info_row)

        # 设置背景
        self.setStyleSheet(f"""
            QWidget {{
                background: {MD3_LIGHT_COLORS['primary_container']};
                border-top: 1px solid {MD3_LIGHT_COLORS['primary_light']};
            }}
        """)

    def _on_text_changed(self, text: str):
        """文本改变"""
        # 更新字符计数
        char_count = len(text)
        self.char_count_label.setText(f"{char_count}/2000")

        # 更新字符计数颜色
        if char_count > 1800:
            self.char_count_label.setStyleSheet(f"""
                QLabel {{
                    color: {MD3_LIGHT_COLORS['error']};
                    font-size: 12px;
                    background: transparent;
                }}
            """)
        else:
            self.char_count_label.setStyleSheet(f"""
                QLabel {{
                    color: {MD3_LIGHT_COLORS['on_surface_variant']};
                    font-size: 12px;
                    background: transparent;
                }}
            """)

        # 更新发送按钮状态
        self.send_btn.setEnabled(len(text.strip()) > 0)

    def _on_send_requested(self):
        """请求发送"""
        text = self.input_text.toPlainText().strip()
        if text:
            self.send_requested.emit(text)
            self.input_text.clear()

    def set_sending(self, is_sending: bool):
        """设置发送状态"""
        self.send_btn.set_sending(is_sending)
        self.input_text.setEnabled(not is_sending)

    def focus_input(self):
        """聚焦输入框"""
        self.input_text.setFocus()
