"""
通知和提示组件

基于 Material Design 3 最佳实践
提供优雅的错误提示、成功提示、警告提示等
包含 Snackbar、Toast、Banner 等组件
"""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QGraphicsOpacityEffect, QPushButton
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QTimer, pyqtSignal, pyqtProperty, QPoint
from PyQt6.QtGui import QPainter, QColor, QPainterPath

from .material_design_light import MD3_LIGHT_COLORS, MD3_RADIUS, MD3_DURATION
from .material_icons import MaterialIcon


class Snackbar(QWidget):
    """Snackbar 提示条 - Material Design 3 标准组件"""

    # 信号
    action_clicked = pyqtSignal()
    closed = pyqtSignal()

    def __init__(self, message: str, action_text: str = "", duration: int = 3000, parent=None):
        super().__init__(parent)

        self.message_text = message
        self.action_text = action_text
        self.duration = duration

        # 动画参数
        self._opacity = 0.0
        self._y_offset = 0

        # 设置属性
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)

        # 设置 UI
        self.setup_ui()

        # 设置动画
        self.setup_animations()

    def setup_ui(self):
        """设置 UI"""
        # 主布局
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # 消息文本
        self.message_label = QLabel(self.message_text)
        self.message_label.setStyleSheet(f"""
            QLabel {{
                color: {MD3_LIGHT_COLORS['on_surface']};
                font-size: 14px;
                background: transparent;
            }}
        """)
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label, 1)

        # 操作按钮（如果有）
        if self.action_text:
            self.action_btn = QPushButton(self.action_text)
            self.action_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {MD3_LIGHT_COLORS['primary']};
                    border: none;
                    padding: 8px 12px;
                    font-size: 14px;
                    font-weight: 500;
                }}
                QPushButton:hover {{
                    background: {MD3_LIGHT_COLORS['primary_container']};
                    border-radius: {MD3_RADIUS['small']};
                }}
            """)
            self.action_btn.clicked.connect(self.action_clicked)
            layout.addWidget(self.action_btn)

        # 设置背景样式
        self.setStyleSheet(f"""
            QWidget {{
                background: {MD3_LIGHT_COLORS['surface_container_high']};
                border-radius: {MD3_RADIUS['small']};
            }}
        """)

        # 调整大小
        self.adjustSize()
        self.setMinimumWidth(300)
        self.setMaximumWidth(600)

    def setup_animations(self):
        """设置动画"""
        # 透明度效果
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)

        # 淡入淡出动画
        self.fade_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_animation.setDuration(MD3_DURATION["medium1"])
        self.fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        # 滑入滑出动画
        self.slide_animation = QPropertyAnimation(self, b"y_offset")
        self.slide_animation.setDuration(MD3_DURATION["medium3"])
        self.slide_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    @pyqtProperty(int)
    def y_offset(self):
        return self._y_offset

    @y_offset.setter
    def y_offset(self, value):
        self._y_offset = value
        # 更新位置
        if self.parent():
            parent_rect = self.parent().rect()
            x = (parent_rect.width() - self.width()) // 2
            y = parent_rect.height() - self.height() - 24 + value
            self.move(x, y)

    def show_animated(self):
        """显示动画"""
        # 设置初始位置
        if self.parent():
            parent_rect = self.parent().rect()
            x = (parent_rect.width() - self.width()) // 2
            y = parent_rect.height() - self.height() - 24 + 50  # 初始在下方
            self.move(x, y)

        self.show()

        # 淡入
        self.fade_animation.setStartValue(0.0)
        self.fade_animation.setEndValue(1.0)
        self.fade_animation.start()

        # 滑入
        self.slide_animation.setStartValue(50)
        self.slide_animation.setEndValue(0)
        self.slide_animation.start()

        # 自动隐藏
        if self.duration > 0:
            QTimer.singleShot(self.duration, self.hide_animated)

    def hide_animated(self):
        """隐藏动画"""
        # 淡出
        self.fade_animation.setStartValue(1.0)
        self.fade_animation.setEndValue(0.0)
        self.fade_animation.start()

        # 滑出
        self.slide_animation.setStartValue(0)
        self.slide_animation.setEndValue(50)
        self.slide_animation.start()

        # 动画结束后隐藏
        QTimer.singleShot(MD3_DURATION["medium3"], self.hide)
        QTimer.singleShot(MD3_DURATION["medium3"], self.closed.emit)


class Toast(QWidget):
    """Toast 提示 - 轻量级提示组件"""

    TYPE_INFO = "info"
    TYPE_SUCCESS = "success"
    TYPE_WARNING = "warning"
    TYPE_ERROR = "error"

    def __init__(self, message: str, toast_type: str = TYPE_INFO, duration: int = 2000, parent=None):
        super().__init__(parent)

        self.message_text = message
        self.toast_type = toast_type
        self.duration = duration

        # 设置属性
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)

        # 设置 UI
        self.setup_ui()

        # 设置动画
        self.setup_animations()

    def setup_ui(self):
        """设置 UI"""
        # 主布局
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # 图标
        icon_name, icon_color = self._get_icon_and_color()
        icon = MaterialIcon(icon_name, 20)
        icon.setStyleSheet(f"color: {icon_color};")
        layout.addWidget(icon)

        # 消息文本
        message_label = QLabel(self.message_text)
        message_label.setStyleSheet(f"""
            QLabel {{
                color: {MD3_LIGHT_COLORS['on_surface']};
                font-size: 14px;
                background: transparent;
            }}
        """)
        layout.addWidget(message_label)

        # 设置背景样式
        bg_color = self._get_background_color()
        self.setStyleSheet(f"""
            QWidget {{
                background: {bg_color};
                border-radius: {MD3_RADIUS['medium']};
            }}
        """)

        # 调整大小
        self.adjustSize()

    def _get_icon_and_color(self):
        """获取图标和颜色"""
        if self.toast_type == self.TYPE_SUCCESS:
            return "check_circle", MD3_LIGHT_COLORS['success']
        elif self.toast_type == self.TYPE_WARNING:
            return "warning", MD3_LIGHT_COLORS['warning']
        elif self.toast_type == self.TYPE_ERROR:
            return "error", MD3_LIGHT_COLORS['error']
        else:
            return "info", MD3_LIGHT_COLORS['primary']

    def _get_background_color(self):
        """获取背景颜色"""
        if self.toast_type == self.TYPE_SUCCESS:
            return MD3_LIGHT_COLORS['success_container']
        elif self.toast_type == self.TYPE_WARNING:
            return MD3_LIGHT_COLORS['warning_container']
        elif self.toast_type == self.TYPE_ERROR:
            return MD3_LIGHT_COLORS['error_container']
        else:
            return MD3_LIGHT_COLORS['surface_container_high']

    def setup_animations(self):
        """设置动画"""
        # 透明度效果
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)

        # 淡入淡出动画
        self.fade_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_animation.setDuration(MD3_DURATION["medium1"])
        self.fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def show_animated(self):
        """显示动画"""
        # 设置位置（顶部中央）
        if self.parent():
            parent_rect = self.parent().rect()
            x = (parent_rect.width() - self.width()) // 2
            y = 24
            self.move(x, y)

        self.show()

        # 淡入
        self.fade_animation.setStartValue(0.0)
        self.fade_animation.setEndValue(1.0)
        self.fade_animation.start()

        # 自动隐藏
        if self.duration > 0:
            QTimer.singleShot(self.duration, self.hide_animated)

    def hide_animated(self):
        """隐藏动画"""
        # 淡出
        self.fade_animation.setStartValue(1.0)
        self.fade_animation.setEndValue(0.0)
        self.fade_animation.start()

        # 动画结束后隐藏
        QTimer.singleShot(MD3_DURATION["medium1"], self.hide)


def show_snackbar(parent: QWidget, message: str, action_text: str = "", duration: int = 3000):
    """显示 Snackbar"""
    snackbar = Snackbar(message, action_text, duration, parent)
    snackbar.show_animated()
    return snackbar


def show_toast(parent: QWidget, message: str, toast_type: str = Toast.TYPE_INFO, duration: int = 2000):
    """显示 Toast"""
    toast = Toast(message, toast_type, duration, parent)
    toast.show_animated()
    return toast
