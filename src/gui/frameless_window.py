"""
MintChat GUI - 无边框窗口组件

提供自定义标题栏、窗口拖动、调整大小等功能
遵循 Material Design 3 规范
"""

from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import Qt, QPoint, QRect, pyqtSignal
from PyQt6.QtGui import QMouseEvent

from .material_design import MD3_COLORS, MD3_RADIUS


class TitleBar(QWidget):
    """自定义标题栏"""

    # 信号
    minimize_clicked = pyqtSignal()
    maximize_clicked = pyqtSignal()
    close_clicked = pyqtSignal()

    def __init__(self, title: str = "MintChat", parent=None):
        super().__init__(parent)
        self.title_text = title
        self.is_maximized = False
        self._init_ui()
        self._apply_styles()

    def _init_ui(self):
        """初始化 UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 8, 8)
        layout.setSpacing(8)

        # 标题
        self.title_label = QLabel(self.title_text)
        self.title_label.setObjectName("titleLabel")
        layout.addWidget(self.title_label)

        # 弹性空间
        layout.addStretch()

        # 窗口控制按钮
        self.min_button = QPushButton("─")
        self.min_button.setObjectName("minButton")
        self.min_button.setFixedSize(40, 32)
        self.min_button.clicked.connect(self.minimize_clicked.emit)
        layout.addWidget(self.min_button)

        self.max_button = QPushButton("□")
        self.max_button.setObjectName("maxButton")
        self.max_button.setFixedSize(40, 32)
        self.max_button.clicked.connect(self._on_maximize_clicked)
        layout.addWidget(self.max_button)

        self.close_button = QPushButton("✕")
        self.close_button.setObjectName("closeButton")
        self.close_button.setFixedSize(40, 32)
        self.close_button.clicked.connect(self.close_clicked.emit)
        layout.addWidget(self.close_button)

        # 设置固定高度
        self.setFixedHeight(48)

    def _on_maximize_clicked(self):
        """最大化/还原按钮点击"""
        self.is_maximized = not self.is_maximized
        self.max_button.setText("❐" if self.is_maximized else "□")
        self.maximize_clicked.emit()

    def _apply_styles(self):
        """应用样式"""
        self.setStyleSheet(
            f"""
            TitleBar {{
                background-color: {MD3_COLORS['surface_container']};
                border-bottom: 1px solid {MD3_COLORS['outline_variant']};
            }}

            #titleLabel {{
                color: {MD3_COLORS['on_surface']};
                font-size: 16px;
                font-weight: 500;
            }}

            QPushButton {{
                background-color: transparent;
                color: {MD3_COLORS['on_surface']};
                border: none;
                border-radius: {MD3_RADIUS['small']};
                font-size: 16px;
            }}

            QPushButton:hover {{
                background-color: {MD3_COLORS['surface_container_highest']};
            }}

            QPushButton:pressed {{
                background-color: {MD3_COLORS['surface_container_high']};
            }}

            #closeButton:hover {{
                background-color: {MD3_COLORS['error_container']};
                color: {MD3_COLORS['on_error_container']};
            }}
        """
        )


class FramelessWindow(QWidget):
    """无边框窗口基类"""

    def __init__(self, title: str = "MintChat", parent=None):
        super().__init__(parent)
        self.title = title

        # 窗口拖动相关
        self._drag_position = QPoint()
        self._is_dragging = False

        # 窗口调整大小相关
        self._resize_direction = None
        self._resize_start_pos = QPoint()
        self._resize_start_geometry = QRect()
        self._resize_margin = 8  # 调整大小的边缘宽度

        # 设置窗口标志
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)

        # 设置窗口属性
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # 初始化 UI
        self._init_ui()
        self._apply_shadow()

    def _init_ui(self):
        """初始化 UI"""
        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 标题栏
        self.title_bar = TitleBar(self.title, self)
        self.title_bar.minimize_clicked.connect(self.showMinimized)
        self.title_bar.maximize_clicked.connect(self._toggle_maximize)
        self.title_bar.close_clicked.connect(self.close)
        main_layout.addWidget(self.title_bar)

        # 内容区域（由子类实现）
        self.content_widget = QWidget()
        self.content_widget.setObjectName("contentWidget")
        main_layout.addWidget(self.content_widget)

        # 应用样式
        self.setStyleSheet(
            f"""
            FramelessWindow {{
                background-color: {MD3_COLORS['surface']};
                border-radius: {MD3_RADIUS['large']};
            }}

            #contentWidget {{
                background-color: {MD3_COLORS['surface']};
                border-bottom-left-radius: {MD3_RADIUS['large']};
                border-bottom-right-radius: {MD3_RADIUS['large']};
            }}
        """
        )

    def _apply_shadow(self):
        """应用阴影效果"""
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setXOffset(0)
        shadow.setYOffset(8)
        shadow.setColor(Qt.GlobalColor.black)
        self.setGraphicsEffect(shadow)

    def _toggle_maximize(self):
        """切换最大化/还原"""
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def mousePressEvent(self, event: QMouseEvent):
        """鼠标按下事件"""
        if event.button() == Qt.MouseButton.LeftButton:
            # 检查是否在标题栏区域
            if self.title_bar.geometry().contains(event.pos()):
                self._is_dragging = True
                self._drag_position = (
                    event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                )
            else:
                # 检查是否在调整大小区域
                self._resize_direction = self._get_resize_direction(event.pos())
                if self._resize_direction:
                    self._resize_start_pos = event.globalPosition().toPoint()
                    self._resize_start_geometry = self.geometry()

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        """鼠标移动事件"""
        if self._is_dragging:
            # 拖动窗口
            self.move(event.globalPosition().toPoint() - self._drag_position)
        elif self._resize_direction:
            # 调整窗口大小
            self._resize_window(event.globalPosition().toPoint())
        else:
            # 更新鼠标光标
            direction = self._get_resize_direction(event.pos())
            self._update_cursor(direction)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        """鼠标释放事件"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = False
            self._resize_direction = None

        super().mouseReleaseEvent(event)

    def _get_resize_direction(self, pos: QPoint) -> str:
        """获取调整大小的方向"""
        if self.isMaximized():
            return None

        rect = self.rect()
        margin = self._resize_margin

        # 检查边角
        if pos.x() < margin and pos.y() < margin:
            return "top_left"
        elif pos.x() > rect.width() - margin and pos.y() < margin:
            return "top_right"
        elif pos.x() < margin and pos.y() > rect.height() - margin:
            return "bottom_left"
        elif pos.x() > rect.width() - margin and pos.y() > rect.height() - margin:
            return "bottom_right"

        # 检查边缘
        elif pos.x() < margin:
            return "left"
        elif pos.x() > rect.width() - margin:
            return "right"
        elif pos.y() < margin:
            return "top"
        elif pos.y() > rect.height() - margin:
            return "bottom"

        return None

    def _update_cursor(self, direction: str):
        """更新鼠标光标"""
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

        if direction in cursor_map:
            self.setCursor(cursor_map[direction])
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def _resize_window(self, global_pos: QPoint):
        """调整窗口大小"""
        delta = global_pos - self._resize_start_pos
        geo = QRect(self._resize_start_geometry)

        if "left" in self._resize_direction:
            geo.setLeft(geo.left() + delta.x())
        if "right" in self._resize_direction:
            geo.setRight(geo.right() + delta.x())
        if "top" in self._resize_direction:
            geo.setTop(geo.top() + delta.y())
        if "bottom" in self._resize_direction:
            geo.setBottom(geo.bottom() + delta.y())

        # 限制最小尺寸
        if geo.width() >= self.minimumWidth() and geo.height() >= self.minimumHeight():
            self.setGeometry(geo)
