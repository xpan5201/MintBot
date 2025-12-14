"""
浅色主题无边框窗口组件

基于 Material Design 3 浅色主题
参考 QQ 现代化界面设计
支持毛玻璃效果和圆角窗口
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QGraphicsDropShadowEffect
)
from PyQt6.QtCore import Qt, QPoint, QRect, pyqtSignal
from PyQt6.QtGui import QMouseEvent, QCursor, QPainter, QColor, QPainterPath, QFont

import os

from .material_design_light import (
    MD3_LIGHT_COLORS, MD3_RADIUS, get_light_elevation_shadow
)
from .material_icons import MATERIAL_ICONS

WINDOW_SHADOW_ENABLED = os.getenv("MINTCHAT_GUI_WINDOW_SHADOW", "0").lower() not in {
    "0",
    "false",
    "no",
    "off",
}


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
        layout.setContentsMargins(16, 0, 8, 0)
        layout.setSpacing(8)

        # 标题
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(f"""
            QLabel {{
                color: {MD3_LIGHT_COLORS['on_surface']};
                font-size: 16px;
                font-weight: 500;
                background: transparent;
            }}
        """)
        layout.addWidget(self.title_label)

        layout.addStretch()

        # 窗口控制按钮 - 使用 Material Design 图标
        # 设置 Material Symbols 字体
        icon_font = QFont("Material Symbols Outlined")
        icon_font.setPixelSize(18)

        button_style = f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: {MD3_RADIUS['full']};
                color: {MD3_LIGHT_COLORS['on_surface_variant']};
                min-width: 32px;
                max-width: 32px;
                min-height: 32px;
                max-height: 32px;
            }}
            QPushButton:hover {{
                background: {MD3_LIGHT_COLORS['surface_container_high']};
            }}
            QPushButton:pressed {{
                background: {MD3_LIGHT_COLORS['surface_container_highest']};
            }}
        """

        # 最小化按钮
        self.minimize_btn = QPushButton(MATERIAL_ICONS["minimize"])
        self.minimize_btn.setFont(icon_font)
        self.minimize_btn.setStyleSheet(button_style)
        self.minimize_btn.setToolTip("最小化")
        self.minimize_btn.clicked.connect(self.minimize_clicked.emit)
        layout.addWidget(self.minimize_btn)

        # 最大化按钮
        self.maximize_btn = QPushButton(MATERIAL_ICONS["maximize"])
        self.maximize_btn.setFont(icon_font)
        self.maximize_btn.setStyleSheet(button_style)
        self.maximize_btn.setToolTip("最大化")
        self.maximize_btn.clicked.connect(self.maximize_clicked.emit)
        layout.addWidget(self.maximize_btn)

        # 关闭按钮
        close_button_style = f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: {MD3_RADIUS['full']};
                color: {MD3_LIGHT_COLORS['on_surface_variant']};
                min-width: 32px;
                max-width: 32px;
                min-height: 32px;
                max-height: 32px;
            }}
            QPushButton:hover {{
                background: {MD3_LIGHT_COLORS['error']};
                color: {MD3_LIGHT_COLORS['on_error']};
            }}
            QPushButton:pressed {{
                background: #D32F2F;
                color: {MD3_LIGHT_COLORS['on_error']};
            }}
        """
        self.close_btn = QPushButton(MATERIAL_ICONS["close"])
        self.close_btn.setFont(icon_font)
        self.close_btn.setStyleSheet(close_button_style)
        self.close_btn.setToolTip("关闭")
        self.close_btn.clicked.connect(self.close_clicked.emit)
        layout.addWidget(self.close_btn)

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
        self.container.setStyleSheet(f"""
            QWidget {{
                background: {MD3_LIGHT_COLORS['gradient_light_mint']};
                border-radius: {MD3_RADIUS['large']};
            }}
        """)

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
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

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
