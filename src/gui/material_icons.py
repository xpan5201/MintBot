"""
Material Design 图标组件

使用 Material Symbols 字体显示图标
符合 Material Design 3 规范
"""

from functools import lru_cache

from PyQt6.QtWidgets import QLabel, QPushButton
from PyQt6.QtCore import Qt, pyqtProperty, QPropertyAnimation, QEasingCurve, QPoint, QTimer
from PyQt6.QtGui import QFont, QFontDatabase, QPainter, QColor, QBrush, QMouseEvent

from .material_design_light import MD3_LIGHT_COLORS, MD3_RADIUS, MD3_DURATION, MD3_STATE_LAYERS
from .qss_utils import qss_rgba
from src.utils.logger import get_logger

logger = get_logger(__name__)


# Material Symbols 图标名称映射
MATERIAL_ICONS = {
    # 导航
    "chat": "chat",
    "contacts": "contacts",
    "star": "star",
    "folder": "folder",
    "settings": "settings",
    "home": "home",
    "menu": "menu",
    "arrow_back": "arrow_back",
    "arrow_forward": "arrow_forward",
    "close": "close",
    "check": "check",

    # 操作
    "send": "send",
    "attach_file": "attach_file",
    "emoji_emotions": "emoji_emotions",
    "add": "add",
    "remove": "remove",
    "edit": "edit",
    "delete": "delete",
    "search": "search",
    "more_vert": "more_vert",
    "more_horiz": "more_horiz",
    "save": "save",
    "refresh": "refresh",
    "restore": "restore_page",

    # 媒体
    "image": "image",
    "video": "videocam",
    "audio": "mic",
    "file": "description",
    "photo_camera": "photo_camera",
    "camera_alt": "camera_alt",
    "photo_library": "photo_library",
    "folder_open": "folder_open",

    # 状态
    "done": "done",
    "check_circle": "check_circle",
    "error": "error",
    "warning": "warning",
    "info": "info",
    "lightbulb": "lightbulb",

    # 用户
    "person": "person",
    "group": "group",
    "account_circle": "account_circle",
    "face": "face",
    "smart_toy": "smart_toy",
    "pets": "pets",

    # 系统
    "tune": "tune",
    "build": "build",
    "memory": "memory",
    "psychology": "psychology",
    "article": "article",
    "note": "note",
    "description": "description",
    "folder_special": "folder_special",
    "library_books": "library_books",
    "book": "book",
    "auto_stories": "auto_stories",

    # 文档和文件
    "text_snippet": "text_snippet",
    "assignment": "assignment",
    "topic": "topic",

    # 分析和搜索
    "pageview": "pageview",
    "find_in_page": "find_in_page",
    "manage_search": "manage_search",
    "troubleshoot": "troubleshoot",

    # 角色和表演
    "theater_comedy": "theater_comedy",
    "masks": "masks",

    # 窗口控制
    "minimize": "minimize",
    "maximize": "crop_square",
    "restore_window": "filter_none",
}


class MaterialIcon(QLabel):
    """Material Design 图标标签"""

    def __init__(self, icon_name: str, size: int = 24, parent=None):
        super().__init__(parent)

        self.icon_name = icon_name
        self.icon_size = size

        # 设置字体
        self.setup_font()

        # 设置样式
        self.setup_style()

    def setup_font(self):
        """设置 Material Symbols 字体"""
        # 设置字体
        font = QFont("Material Symbols Outlined")
        font.setPixelSize(self.icon_size)
        self.setFont(font)

        # 设置图标文本
        icon_text = MATERIAL_ICONS.get(self.icon_name, self.icon_name)
        self.setText(icon_text)

    def setup_style(self):
        """设置样式"""
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(f"""
            QLabel {{
                color: {MD3_LIGHT_COLORS['on_surface_variant']};
            }}
        """)


class MaterialIconButton(QPushButton):
    """Material Design 图标按钮 - 带涟漪效果"""

    def __init__(self, icon_name: str, tooltip: str = "", size: int = 48, icon_size: int = 24, parent=None):
        super().__init__(parent)

        self.icon_name = icon_name
        self.icon_size = icon_size
        self.button_size = size

        # 涟漪效果参数
        self._ripple_radius = 0
        self.ripple_opacity = 0.0
        self.ripple_center = QPoint()
        self.ripple_active = False

        # 悬停状态
        self._hover_opacity = 0.0

        # 设置提示
        if tooltip:
            self.setToolTip(tooltip)

        # 设置大小
        self.setFixedSize(size, size)

        # 设置字体
        self.setup_font()

        # 设置动画
        self.setup_animations()

        # 设置样式
        self.setup_style()

        # 启用鼠标追踪
        self.setMouseTracking(True)

    def setup_font(self):
        """设置 Material Symbols 字体"""
        font = QFont("Material Symbols Outlined")
        font.setPixelSize(self.icon_size)
        self.setFont(font)

        # 设置图标文本
        icon_text = MATERIAL_ICONS.get(self.icon_name, self.icon_name)
        self.setText(icon_text)

    def setup_animations(self):
        """设置动画"""
        # 涟漪动画 - 使用新的动画时长
        self.ripple_animation = QPropertyAnimation(self, b"ripple_radius")
        self.ripple_animation.setDuration(MD3_DURATION["ripple"])
        self.ripple_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.ripple_animation.finished.connect(self.on_ripple_finished)

        # 悬停动画 - 更快的响应
        self.hover_animation = QPropertyAnimation(self, b"hover_opacity")
        self.hover_animation.setDuration(MD3_DURATION["short3"])
        self.hover_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def setup_style(self):
        """设置样式 - v2.31.0: 优化悬停和选中效果"""
        hover_0 = qss_rgba(MD3_LIGHT_COLORS["primary"], 0.08)
        hover_1 = qss_rgba(MD3_LIGHT_COLORS["primary"], 0.12)
        pressed_0 = qss_rgba(MD3_LIGHT_COLORS["primary"], 0.15)
        pressed_1 = qss_rgba(MD3_LIGHT_COLORS["primary"], 0.20)
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: {MD3_RADIUS['medium']};
                color: {MD3_LIGHT_COLORS['on_surface_variant']};
            }}
            QPushButton:hover {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 {hover_0},
                    stop:1 {hover_1}
                );
            }}
            QPushButton:checked {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 {MD3_LIGHT_COLORS['primary_container']},
                    stop:1 {MD3_LIGHT_COLORS['tertiary_container']}
                );
                color: {MD3_LIGHT_COLORS['on_primary_container']};
            }}
            QPushButton:pressed {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 {pressed_0},
                    stop:1 {pressed_1}
                );
            }}
        """)
        self.setCheckable(True)

    @pyqtProperty(int)
    def ripple_radius(self):
        return self._ripple_radius

    @ripple_radius.setter
    def ripple_radius(self, value):
        self._ripple_radius = value
        self.update()

    @pyqtProperty(float)
    def hover_opacity(self):
        return self._hover_opacity

    @hover_opacity.setter
    def hover_opacity(self, value):
        self._hover_opacity = value
        self.update()

    def mousePressEvent(self, event: QMouseEvent):
        """鼠标按下 - 开始涟漪效果"""
        super().mousePressEvent(event)

        # 记录涟漪中心
        self.ripple_center = event.pos()
        self.ripple_active = True

        # 计算最大半径
        max_radius = self.button_size // 2 + 10

        # 开始涟漪动画
        self.ripple_animation.setStartValue(0)
        self.ripple_animation.setEndValue(max_radius)
        self.ripple_opacity = MD3_STATE_LAYERS["pressed"]
        self.ripple_animation.start()

        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        """鼠标释放"""
        super().mouseReleaseEvent(event)

        # 淡出涟漪
        QTimer.singleShot(100, self.fade_out_ripple)

    def enterEvent(self, event):
        """鼠标进入 - 显示悬停状态"""
        super().enterEvent(event)

        if not self.isChecked():
            self.hover_animation.setStartValue(self.hover_opacity)
            self.hover_animation.setEndValue(MD3_STATE_LAYERS["hover"])
            self.hover_animation.start()

    def leaveEvent(self, event):
        """鼠标离开 - 隐藏悬停状态"""
        super().leaveEvent(event)

        self.hover_animation.setStartValue(self.hover_opacity)
        self.hover_animation.setEndValue(0.0)
        self.hover_animation.start()

    def fade_out_ripple(self):
        """淡出涟漪"""
        self.ripple_opacity = 0.0
        self.update()

    def on_ripple_finished(self):
        """涟漪动画完成"""
        if self.ripple_opacity == 0.0:
            self.ripple_active = False
            self.ripple_radius = 0
            self.update()

    def paintEvent(self, event):
        """绘制按钮"""
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 绘制悬停状态 - 使用主题主色
        if self.hover_opacity > 0 and not self.isChecked():
            try:
                base = QColor(MD3_LIGHT_COLORS["primary"])
            except Exception:
                base = QColor(0, 0, 0)
            hover_color = QColor(base)
            hover_color.setAlpha(int(self.hover_opacity * 50))
            painter.setBrush(QBrush(hover_color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(self.rect(), 12, 12)

        # 绘制涟漪效果 - 使用主题主色
        if self.ripple_active and self.ripple_opacity > 0:
            try:
                base = QColor(MD3_LIGHT_COLORS["primary"])
            except Exception:
                base = QColor(0, 0, 0)
            ripple_color = QColor(base)
            ripple_color.setAlpha(int(self.ripple_opacity * 70))
            painter.setBrush(QBrush(ripple_color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(
                self.ripple_center,
                self.ripple_radius,
                self.ripple_radius
            )


@lru_cache(maxsize=1)
def load_material_symbols_font() -> bool:
    """
    加载 Material Symbols 字体

    注意：需要先安装 Material Symbols 字体
    可以从 Google Fonts 下载：https://fonts.google.com/icons
    """
    # 尝试加载系统字体
    try:
        font_families = set(QFontDatabase.families())
    except Exception as exc:
        logger.warning("读取系统字体列表失败: %s", exc)
        return False

    if "Material Symbols Outlined" not in font_families:
        logger.warning("警告: Material Symbols Outlined 字体未安装")
        logger.info("请从 https://fonts.google.com/icons 下载并安装字体")
        logger.info("或者使用 Emoji 图标作为替代")
        return False

    return True
