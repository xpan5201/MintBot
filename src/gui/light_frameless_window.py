"""
浅色主题无边框窗口组件

基于 Material Design 3 浅色主题
参考 QQ 现代化界面设计
支持毛玻璃效果和圆角窗口
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QGraphicsDropShadowEffect
)
from PyQt6.QtCore import (
    Qt,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    pyqtSignal,
    QEvent,
    QPropertyAnimation,
    QEasingCurve,
    pyqtProperty,
)
from PyQt6.QtGui import QMouseEvent, QCursor, QColor, QPainter, QPen

import os

from .material_design_light import MD3_LIGHT_COLORS, MD3_RADIUS

WINDOW_SHADOW_ENABLED = os.getenv("MINTCHAT_GUI_WINDOW_SHADOW", "0").lower() not in {
    "0",
    "false",
    "no",
    "off",
}


class MacWindowControlButton(QPushButton):
    """macOS-style three-color window control button (close/minimize/maximize)."""

    TYPE_CLOSE = "close"
    TYPE_MINIMIZE = "minimize"
    TYPE_MAXIMIZE = "maximize"

    def __init__(
        self,
        button_type: str,
        *,
        size: int = 14,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._button_type = str(button_type)
        self._size = int(size)
        self._hover_t = 0.0
        self._press_t = 0.0

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedSize(self._size, self._size)
        self.setFlat(True)

        self._hover_anim = QPropertyAnimation(self, b"hover_t", self)
        self._hover_anim.setDuration(120)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._press_anim = QPropertyAnimation(self, b"press_t", self)
        self._press_anim.setDuration(90)
        self._press_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        if self._button_type == self.TYPE_CLOSE:
            self.setToolTip("关闭")
        elif self._button_type == self.TYPE_MINIMIZE:
            self.setToolTip("最小化")
        else:
            self.setToolTip("最大化/还原")

    @pyqtProperty(float)
    def hover_t(self) -> float:
        return float(self._hover_t)

    @hover_t.setter
    def hover_t(self, value: float) -> None:
        self._hover_t = max(0.0, min(1.0, float(value)))
        self.update()

    @pyqtProperty(float)
    def press_t(self) -> float:
        return float(self._press_t)

    @press_t.setter
    def press_t(self, value: float) -> None:
        self._press_t = max(0.0, min(1.0, float(value)))
        self.update()

    def _start_anim(self, anim: QPropertyAnimation, end_value: float) -> None:
        anim.stop()
        if anim is self._hover_anim:
            anim.setStartValue(float(self._hover_t))
        else:
            anim.setStartValue(float(self._press_t))
        anim.setEndValue(float(end_value))
        anim.start()

    def enterEvent(self, event):  # noqa: N802 - Qt API naming
        super().enterEvent(event)
        self._start_anim(self._hover_anim, 1.0)

    def leaveEvent(self, event):  # noqa: N802 - Qt API naming
        super().leaveEvent(event)
        self._start_anim(self._hover_anim, 0.0)

    def mousePressEvent(self, event: QMouseEvent):  # noqa: N802 - Qt API naming
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_anim(self._press_anim, 1.0)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):  # noqa: N802 - Qt API naming
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_anim(self._press_anim, 0.0)
        super().mouseReleaseEvent(event)

    def _lerp(self, a: int, b: int, t: float) -> int:
        return int(round(a + (b - a) * t))

    def _blend(self, c1: QColor, c2: QColor, t: float) -> QColor:
        tt = max(0.0, min(1.0, float(t)))
        return QColor(
            self._lerp(c1.red(), c2.red(), tt),
            self._lerp(c1.green(), c2.green(), tt),
            self._lerp(c1.blue(), c2.blue(), tt),
            self._lerp(c1.alpha(), c2.alpha(), tt),
        )

    def _colors(self) -> tuple[QColor, QColor, QColor, QColor]:
        if self._button_type == self.TYPE_CLOSE:
            return (
                QColor("#FF5F57"),
                QColor("#E2463F"),
                QColor("#E0443E"),
                QColor("#C53A34"),
            )
        if self._button_type == self.TYPE_MINIMIZE:
            return (
                QColor("#FFBD2E"),
                QColor("#E1A116"),
                QColor("#D79E29"),
                QColor("#B98522"),
            )
        return (
            QColor("#28C840"),
            QColor("#1FA52D"),
            QColor("#1FA52D"),
            QColor("#178A24"),
        )

    def paintEvent(self, _event):  # noqa: N802 - Qt API naming
        base, border, pressed, pressed_border = self._colors()
        fill = self._blend(base, pressed, self._press_t)
        stroke = self._blend(border, pressed_border, self._press_t)

        rect = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
        # Keep the visible dot close to macOS size while allowing a slightly larger hit box.
        min_side = float(min(self.width(), self.height()))
        dot_diameter = min(12.0, max(8.0, min_side - 1.0))
        dot_inset = max(0.0, (min_side - dot_diameter) / 2.0)
        press_inset = 0.8 * self._press_t
        circle = rect.adjusted(
            dot_inset + press_inset,
            dot_inset + press_inset,
            -(dot_inset + press_inset),
            -(dot_inset + press_inset),
        )

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Hover glow (lightweight feedback)
        if self._hover_t > 0.01:
            glow = QColor(fill)
            glow.setAlpha(int(45 * self._hover_t))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(circle.adjusted(-2.0, -2.0, 2.0, 2.0))

        painter.setPen(QPen(stroke, 1.0))
        painter.setBrush(fill)
        painter.drawEllipse(circle)


class LightTitleBar(QWidget):
    """浅色主题标题栏"""

    minimize_clicked = pyqtSignal()
    maximize_clicked = pyqtSignal()
    close_clicked = pyqtSignal()

    def __init__(self, title: str = "MintChat", parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)
        self.setup_ui(title)

    def setup_ui(self, title: str):
        """设置 UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(0)

        button_size = 16
        button_spacing = 11

        controls = QWidget()
        controls.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(button_spacing)

        self.close_btn = MacWindowControlButton(
            MacWindowControlButton.TYPE_CLOSE, size=button_size, parent=controls
        )
        self.close_btn.clicked.connect(self.close_clicked.emit)
        controls_layout.addWidget(self.close_btn)

        self.maximize_btn = MacWindowControlButton(
            MacWindowControlButton.TYPE_MAXIMIZE, size=button_size, parent=controls
        )
        self.maximize_btn.clicked.connect(self.maximize_clicked.emit)
        controls_layout.addWidget(self.maximize_btn)

        self.minimize_btn = MacWindowControlButton(
            MacWindowControlButton.TYPE_MINIMIZE, size=button_size, parent=controls
        )
        self.minimize_btn.clicked.connect(self.minimize_clicked.emit)
        controls_layout.addWidget(self.minimize_btn)

        controls_width = button_size * 3 + button_spacing * 2
        controls.setFixedWidth(controls_width)

        right_spacer = QWidget()
        right_spacer.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        right_spacer.setFixedWidth(controls_width)

        self.title_label = QLabel(title)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet(
            f"""
            QLabel {{
                color: {MD3_LIGHT_COLORS['on_surface']};
                font-size: 14px;
                font-weight: 600;
                background: transparent;
            }}
        """
        )

        layout.addWidget(controls)
        layout.addWidget(self.title_label, 1)
        layout.addWidget(right_spacer)

        # 设置背景 - 使用淡薄荷绿
        self.setStyleSheet(f"""
            LightTitleBar {{
                background: {MD3_LIGHT_COLORS['primary_container']};
                border-top-left-radius: {MD3_RADIUS['large']};
                border-top-right-radius: {MD3_RADIUS['large']};
            }}
        """)


class LightFramelessWindow(QWidget):
    """浅色主题无边框窗口基类"""

    def __init__(self, title: str = "MintChat", parent=None):
        super().__init__(parent)

        # 设置窗口标志
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowSystemMenuHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # 窗口拖动相关
        self.dragging = False
        self.drag_position = QPoint()

        # 窗口调整大小相关
        self.resizing = False
        self.resize_direction = None
        self.resize_margin = 8

        # 设置 UI
        self.setup_ui(title)

        # 添加阴影效果
        self.add_shadow()

    def setup_ui(self, title: str):
        """设置 UI"""
        # 主布局
        main_layout = QVBoxLayout(self)
        # 性能：窗口外层阴影会导致每次重绘都进行大面积离屏渲染，默认关闭并同步去掉外边距
        outer_margin = 10 if WINDOW_SHADOW_ENABLED else 0
        main_layout.setContentsMargins(outer_margin, outer_margin, outer_margin, outer_margin)
        main_layout.setSpacing(0)

        # 容器 widget（用于圆角和背景）
        self.container = QWidget()
        self._apply_window_chrome_style(is_maximized=False)

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # 标题栏
        self.title_bar = LightTitleBar(title)
        self.title_bar.minimize_clicked.connect(self.showMinimized)
        self.title_bar.maximize_clicked.connect(self.toggle_maximize)
        self.title_bar.close_clicked.connect(self.close)
        container_layout.addWidget(self.title_bar)

        # 内容区域
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet(f"""
            QWidget {{
                background: transparent;
            }}
        """)
        container_layout.addWidget(self.content_widget)

        main_layout.addWidget(self.container)

        self._apply_window_chrome_style(is_maximized=self.isMaximized())

    def _apply_window_chrome_style(self, is_maximized: bool | None = None) -> None:
        maximized = self.isMaximized() if is_maximized is None else bool(is_maximized)
        radius = "0px" if maximized else MD3_RADIUS["large"]

        try:
            self.container.setStyleSheet(
                f"""
                QWidget {{
                    background: {MD3_LIGHT_COLORS['gradient_light_mint']};
                    border-radius: {radius};
                }}
                """
            )
        except Exception:
            pass

        try:
            self.title_bar.setStyleSheet(
                f"""
                LightTitleBar {{
                    background: {MD3_LIGHT_COLORS['primary_container']};
                    border-top-left-radius: {radius};
                    border-top-right-radius: {radius};
                }}
                """
            )
        except Exception:
            pass

    def changeEvent(self, event):
        super().changeEvent(event)
        try:
            if event.type() == QEvent.Type.WindowStateChange:
                self._apply_window_chrome_style()
        except Exception:
            pass

    def add_shadow(self):
        """添加阴影效果"""
        if not WINDOW_SHADOW_ENABLED:
            try:
                self.container.setGraphicsEffect(None)
            except Exception:
                pass
            return
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 40))
        self.container.setGraphicsEffect(shadow)

    def toggle_maximize(self):
        """切换最大化状态"""
        maximized_next = not self.isMaximized()
        if maximized_next:
            self.showMaximized()
        else:
            self.showNormal()
        self._apply_window_chrome_style(is_maximized=maximized_next)

    def mousePressEvent(self, event: QMouseEvent):
        """鼠标按下事件"""
        if event.button() == Qt.MouseButton.LeftButton:
            # 检查是否在标题栏区域
            if self.title_bar.geometry().contains(event.pos()):
                self.dragging = True
                self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            else:
                # 检查是否在边缘（用于调整大小）
                direction = self.get_resize_direction(event.pos())
                if direction:
                    self.resizing = True
                    self.resize_direction = direction
                    self.drag_position = event.globalPosition().toPoint()

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        """鼠标移动事件"""
        if self.dragging:
            # 拖动窗口
            self.move(event.globalPosition().toPoint() - self.drag_position)
        elif self.resizing:
            # 调整窗口大小
            self.resize_window(event.globalPosition().toPoint())
        else:
            # 更新鼠标光标
            direction = self.get_resize_direction(event.pos())
            if direction:
                self.set_resize_cursor(direction)
            else:
                self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        """鼠标释放事件"""
        self.dragging = False
        self.resizing = False
        self.resize_direction = None
        super().mouseReleaseEvent(event)

    def get_resize_direction(self, pos: QPoint) -> str:
        """获取调整大小的方向"""
        rect = self.rect()
        margin = self.resize_margin

        # 检查角落
        if QRect(0, 0, margin, margin).contains(pos):
            return "top_left"
        elif QRect(rect.width() - margin, 0, margin, margin).contains(pos):
            return "top_right"
        elif QRect(0, rect.height() - margin, margin, margin).contains(pos):
            return "bottom_left"
        elif QRect(rect.width() - margin, rect.height() - margin, margin, margin).contains(pos):
            return "bottom_right"
        # 检查边缘
        elif QRect(0, 0, rect.width(), margin).contains(pos):
            return "top"
        elif QRect(0, rect.height() - margin, rect.width(), margin).contains(pos):
            return "bottom"
        elif QRect(0, 0, margin, rect.height()).contains(pos):
            return "left"
        elif QRect(rect.width() - margin, 0, margin, rect.height()).contains(pos):
            return "right"

        return None

    def set_resize_cursor(self, direction: str):
        """设置调整大小的光标"""
        cursor_map = {
            "top": Qt.CursorShape.SizeVerCursor,
            "bottom": Qt.CursorShape.SizeVerCursor,
            "left": Qt.CursorShape.SizeHorCursor,
            "right": Qt.CursorShape.SizeHorCursor,
            "top_left": Qt.CursorShape.SizeFDiagCursor,
            "bottom_right": Qt.CursorShape.SizeFDiagCursor,
            "top_right": Qt.CursorShape.SizeBDiagCursor,
            "bottom_left": Qt.CursorShape.SizeBDiagCursor,
        }
        self.setCursor(QCursor(cursor_map.get(direction, Qt.CursorShape.ArrowCursor)))

    def resize_window(self, global_pos: QPoint):
        """调整窗口大小"""
        delta = global_pos - self.drag_position
        self.drag_position = global_pos

        rect = self.geometry()

        if "left" in self.resize_direction:
            rect.setLeft(rect.left() + delta.x())
        if "right" in self.resize_direction:
            rect.setRight(rect.right() + delta.x())
        if "top" in self.resize_direction:
            rect.setTop(rect.top() + delta.y())
        if "bottom" in self.resize_direction:
            rect.setBottom(rect.bottom() + delta.y())

        self.setGeometry(rect)
