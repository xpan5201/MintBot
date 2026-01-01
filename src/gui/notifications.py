"""
通知和提示组件

基于 Material Design 3 最佳实践
提供优雅的错误提示、成功提示、警告提示等
包含 Snackbar、Toast、Banner 等组件
"""

from __future__ import annotations

from weakref import WeakKeyDictionary

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QGraphicsOpacityEffect, QPushButton
from PyQt6.QtCore import (
    Qt,
    QEvent,
    QPropertyAnimation,
    QEasingCurve,
    QTimer,
    pyqtSignal,
    pyqtProperty,
    QPoint,
    QRectF,
)
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen

from .material_design_enhanced import (
    MD3_ENHANCED_COLORS,
    MD3_ENHANCED_DURATION,
    MD3_ENHANCED_RADIUS,
    get_typography_css,
)
from .material_icons import MaterialIcon


def _resolve_host(parent: QWidget | None) -> QWidget | None:
    if parent is None:
        return None
    try:
        host = parent.window()
        return host if host is not None else parent
    except Exception:
        return parent


_ACTIVE_TOASTS: WeakKeyDictionary[QWidget, "Toast"] = WeakKeyDictionary()
_ACTIVE_SNACKBARS: WeakKeyDictionary[QWidget, "Snackbar"] = WeakKeyDictionary()


def _px(value: str, default: float = 8.0) -> float:
    try:
        return float(str(value).replace("px", "").strip())
    except Exception:
        return float(default)


class Snackbar(QWidget):
    """Snackbar 提示条 - Material Design 3 标准组件"""

    # 信号
    action_clicked = pyqtSignal()
    closed = pyqtSignal()

    def __init__(self, message: str, action_text: str = "", duration: int = 3000, parent=None):
        super().__init__(parent)

        c = MD3_ENHANCED_COLORS
        self._bg = QColor(c["surface_container_highest"])
        self._border = QColor(c["outline_variant"])
        self._radius = _px(MD3_ENHANCED_RADIUS["lg"], 12.0)

        self.message_text = message
        self.action_text = action_text
        self.duration = duration

        # 动画参数
        self._opacity = 0.0
        self._y_offset = 0
        self._closing = False
        self._finalized = False
        self._host = _resolve_host(parent)
        self._host_filter_installed = False
        self._auto_timer = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.timeout.connect(self.hide_animated)

        # 设置属性
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )

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
        self.message_label.setStyleSheet(
            f"""
            QLabel {{
                color: {MD3_ENHANCED_COLORS['on_surface']};
                background: transparent;
                {get_typography_css('label_large')}
                font-weight: 650;
            }}
        """
        )
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label, 1)

        # 操作按钮（如果有）
        if self.action_text:
            self.action_btn = QPushButton(self.action_text)
            self.action_btn.setStyleSheet(
                f"""
                QPushButton {{
                    background: transparent;
                    color: {MD3_ENHANCED_COLORS['primary']};
                    border: none;
                    padding: 8px 12px;
                    {get_typography_css('label_large')}
                    font-weight: 750;
                }}
                QPushButton:hover {{
                    background-color: {MD3_ENHANCED_COLORS['primary_container']};
                    border-radius: {MD3_ENHANCED_RADIUS['full']};
                }}
            """
            )
            self.action_btn.clicked.connect(self.action_clicked)
            layout.addWidget(self.action_btn)

        # 调整大小
        self.adjustSize()
        self.setMinimumWidth(300)
        self.setMaximumWidth(600)

    def paintEvent(self, event):  # noqa: N802 - Qt API naming
        # Draw background/border ourselves: translucent windows may not paint QSS reliably.
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)

        path = QPainterPath()
        path.addRoundedRect(rect, self._radius, self._radius)

        # subtle shadow (cheap): 1 pass fill behind
        shadow = QColor(0, 0, 0, 18)
        shadow_path = QPainterPath()
        shadow_path.addRoundedRect(rect.translated(0, 2), self._radius, self._radius)
        painter.fillPath(shadow_path, shadow)

        painter.fillPath(path, self._bg)
        try:
            pen = QPen(self._border, 1.0)
            painter.setPen(pen)
            painter.drawPath(path)
        except Exception:
            pass

    def setup_animations(self):
        """设置动画"""
        # 透明度效果
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)

        # 淡入淡出动画
        self.fade_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_animation.setDuration(MD3_ENHANCED_DURATION["medium1"])
        self.fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        # 滑入滑出动画
        self.slide_animation = QPropertyAnimation(self, b"y_offset")
        self.slide_animation.setDuration(MD3_ENHANCED_DURATION["medium3"])
        self.slide_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def eventFilter(self, obj, event):  # noqa: N802 - Qt API naming
        try:
            if obj is self._host and event.type() in {
                QEvent.Type.Move,
                QEvent.Type.Resize,
                QEvent.Type.WindowStateChange,
            }:
                self._reposition()
        except Exception:
            pass
        return False

    def _install_host_filter(self) -> None:
        if self._host is None or self._host_filter_installed:
            return
        try:
            self._host.installEventFilter(self)
            self._host_filter_installed = True
        except Exception:
            pass

    def _remove_host_filter(self) -> None:
        if self._host is None or not self._host_filter_installed:
            return
        try:
            self._host.removeEventFilter(self)
        except Exception:
            pass
        self._host_filter_installed = False

    def _reposition(self) -> None:
        host = self._host
        if host is None:
            return
        try:
            top_left = host.mapToGlobal(QPoint(0, 0))
            rect = host.rect()
            x = int(top_left.x() + (rect.width() - self.width()) / 2)
            y = int(top_left.y() + rect.height() - self.height() - 24 + int(self._y_offset))
            self.move(x, y)
        except Exception:
            pass

    @pyqtProperty(int)
    def y_offset(self):
        return self._y_offset

    @y_offset.setter
    def y_offset(self, value):
        self._y_offset = value
        self._reposition()

    def show_animated(self):
        """显示动画"""
        self._finalized = False
        self._closing = False
        self._install_host_filter()

        try:
            self.fade_animation.stop()
        except Exception:
            pass
        try:
            self.slide_animation.stop()
        except Exception:
            pass

        # 设置初始位置（底部居中）
        try:
            self._y_offset = 50
            self._reposition()
        except Exception:
            pass
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
        try:
            self._auto_timer.stop()
        except Exception:
            pass
        if int(self.duration) > 0:
            self._auto_timer.start(int(self.duration))

    def hide_animated(self):
        """隐藏动画"""
        if self._closing:
            return
        self._closing = True
        try:
            self._auto_timer.stop()
        except Exception:
            pass

        # 淡出
        self.fade_animation.setStartValue(1.0)
        self.fade_animation.setEndValue(0.0)
        self.fade_animation.start()

        # 滑出
        self.slide_animation.setStartValue(0)
        self.slide_animation.setEndValue(50)
        self.slide_animation.start()

        # 动画结束后隐藏并销毁（避免隐藏窗口堆积）
        QTimer.singleShot(MD3_ENHANCED_DURATION["medium3"], self._finalize_hide)

    def _finalize_hide(self) -> None:
        if self._finalized:
            return
        self._finalized = True
        try:
            self.hide()
        except Exception:
            pass
        try:
            self.closed.emit()
        except Exception:
            pass
        self._remove_host_filter()
        self.deleteLater()


class Toast(QWidget):
    """Toast 提示 - 轻量级提示组件"""

    TYPE_INFO = "info"
    TYPE_SUCCESS = "success"
    TYPE_WARNING = "warning"
    TYPE_ERROR = "error"

    closed = pyqtSignal()

    def __init__(
        self, message: str, toast_type: str = TYPE_INFO, duration: int = 2000, parent=None
    ):
        super().__init__(parent)

        self._bg = QColor(MD3_ENHANCED_COLORS["surface_container_highest"])
        self._border = QColor(MD3_ENHANCED_COLORS["outline_variant"])
        self._radius = _px(MD3_ENHANCED_RADIUS["lg"], 12.0)

        self.message_text = message
        self.toast_type = toast_type
        self.duration = duration
        self._closing = False
        self._finalized = False
        self._host = _resolve_host(parent)
        self._host_filter_installed = False
        self._auto_timer = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.timeout.connect(self.hide_animated)

        # 设置属性
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )

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
        self.icon_widget = MaterialIcon(icon_name, 20)
        self.icon_widget.setStyleSheet(f"color: {icon_color};")
        layout.addWidget(self.icon_widget)

        # 消息文本
        self.message_label = QLabel(self.message_text)
        self.message_label.setStyleSheet(
            f"""
            QLabel {{
                background: transparent;
                color: {MD3_ENHANCED_COLORS['on_surface']};
                {get_typography_css('label_large')}
                font-weight: 650;
            }}
        """
        )
        layout.addWidget(self.message_label)

        # Resolve background color once (paintEvent)
        try:
            bg_css = str(self._get_background_color() or "")
            if bg_css:
                self._bg = QColor(bg_css)
        except Exception:
            pass

        # 调整大小
        self.adjustSize()

    def paintEvent(self, event):  # noqa: N802 - Qt API naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)

        path = QPainterPath()
        path.addRoundedRect(rect, self._radius, self._radius)

        shadow = QColor(0, 0, 0, 18)
        shadow_path = QPainterPath()
        shadow_path.addRoundedRect(rect.translated(0, 2), self._radius, self._radius)
        painter.fillPath(shadow_path, shadow)

        painter.fillPath(path, self._bg)
        try:
            pen = QPen(self._border, 1.0)
            painter.setPen(pen)
            painter.drawPath(path)
        except Exception:
            pass

    def eventFilter(self, obj, event):  # noqa: N802 - Qt API naming
        try:
            if obj is self._host and event.type() in {
                QEvent.Type.Move,
                QEvent.Type.Resize,
                QEvent.Type.WindowStateChange,
            }:
                self._reposition()
        except Exception:
            pass
        return False

    def _install_host_filter(self) -> None:
        if self._host is None or self._host_filter_installed:
            return
        try:
            self._host.installEventFilter(self)
            self._host_filter_installed = True
        except Exception:
            pass

    def _remove_host_filter(self) -> None:
        if self._host is None or not self._host_filter_installed:
            return
        try:
            self._host.removeEventFilter(self)
        except Exception:
            pass
        self._host_filter_installed = False

    def _reposition(self) -> None:
        host = self._host
        if host is None:
            return
        try:
            top_left = host.mapToGlobal(QPoint(0, 0))
            rect = host.rect()
            x = int(top_left.x() + (rect.width() - self.width()) / 2)
            y = int(top_left.y() + 24)
            self.move(x, y)
        except Exception:
            pass

    def _get_icon_and_color(self):
        """获取图标和颜色"""
        if self.toast_type == self.TYPE_SUCCESS:
            return "check_circle", MD3_ENHANCED_COLORS["success"]
        elif self.toast_type == self.TYPE_WARNING:
            return "warning", MD3_ENHANCED_COLORS["warning"]
        elif self.toast_type == self.TYPE_ERROR:
            return "error", MD3_ENHANCED_COLORS["error"]
        else:
            return "info", MD3_ENHANCED_COLORS.get("info", MD3_ENHANCED_COLORS["primary"])

    def _get_background_color(self):
        """获取背景颜色"""
        if self.toast_type == self.TYPE_SUCCESS:
            return MD3_ENHANCED_COLORS.get(
                "success_container", MD3_ENHANCED_COLORS["surface_container_highest"]
            )
        elif self.toast_type == self.TYPE_WARNING:
            return MD3_ENHANCED_COLORS.get(
                "warning_container", MD3_ENHANCED_COLORS["surface_container_highest"]
            )
        elif self.toast_type == self.TYPE_ERROR:
            return MD3_ENHANCED_COLORS.get(
                "error_container", MD3_ENHANCED_COLORS["surface_container_highest"]
            )
        else:
            return MD3_ENHANCED_COLORS["surface_container_highest"]

    def setup_animations(self):
        """设置动画"""
        # 透明度效果
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)

        # 淡入淡出动画
        self.fade_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_animation.setDuration(MD3_ENHANCED_DURATION["medium1"])
        self.fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def show_animated(self):
        """显示动画"""
        self._finalized = False
        self._closing = False
        self._install_host_filter()
        self._reposition()

        try:
            self.fade_animation.stop()
        except Exception:
            pass
        self.show()

        # 淡入
        self.fade_animation.setStartValue(0.0)
        self.fade_animation.setEndValue(1.0)
        self.fade_animation.start()

        # 自动隐藏
        try:
            self._auto_timer.stop()
        except Exception:
            pass
        if int(self.duration) > 0:
            self._auto_timer.start(int(self.duration))

    def hide_animated(self):
        """隐藏动画"""
        if self._closing:
            return
        self._closing = True
        try:
            self._auto_timer.stop()
        except Exception:
            pass

        # 淡出
        self.fade_animation.setStartValue(1.0)
        self.fade_animation.setEndValue(0.0)
        self.fade_animation.start()

        # 动画结束后隐藏并销毁（避免隐藏窗口堆积）
        QTimer.singleShot(MD3_ENHANCED_DURATION["medium1"], self._finalize_hide)

    def _finalize_hide(self) -> None:
        if self._finalized:
            return
        self._finalized = True
        try:
            self.hide()
        except Exception:
            pass
        try:
            self.closed.emit()
        except Exception:
            pass
        self._remove_host_filter()
        self.deleteLater()


def show_snackbar(parent: QWidget, message: str, action_text: str = "", duration: int = 3000):
    """显示 Snackbar"""
    host = _resolve_host(parent) or parent
    try:
        old = _ACTIVE_SNACKBARS.get(host)
        if old is not None:
            old.hide_animated()
    except Exception:
        pass
    snackbar = Snackbar(message, action_text, duration, host)
    try:

        def _maybe_clear() -> None:
            try:
                if _ACTIVE_SNACKBARS.get(host) is snackbar:
                    _ACTIVE_SNACKBARS.pop(host, None)
            except Exception:
                pass

        snackbar.closed.connect(_maybe_clear)
    except Exception:
        pass
    snackbar.show_animated()
    try:
        _ACTIVE_SNACKBARS[host] = snackbar
    except Exception:
        pass
    return snackbar


def show_toast(
    parent: QWidget, message: str, toast_type: str = Toast.TYPE_INFO, duration: int = 2000
):
    """显示 Toast"""
    host = _resolve_host(parent) or parent
    try:
        old = _ACTIVE_TOASTS.get(host)
        if old is not None:
            old.hide_animated()
    except Exception:
        pass
    toast = Toast(message, toast_type, duration, host)
    try:

        def _maybe_clear() -> None:
            try:
                if _ACTIVE_TOASTS.get(host) is toast:
                    _ACTIVE_TOASTS.pop(host, None)
            except Exception:
                pass

        toast.closed.connect(_maybe_clear)
    except Exception:
        pass
    toast.show_animated()
    try:
        _ACTIVE_TOASTS[host] = toast
    except Exception:
        pass
    return toast
