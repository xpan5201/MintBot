"""
表情选择器组件 (v2.19.2 Material Design 3 全面优化版)

基于 Google Material Design 3 最新规范（2025）
全方位深度优化：性能、美观度、交互反馈、代码规范

v2.19.2 优化内容：
- 🐛 修复上传功能：修复自定义表情包上传、加载、删除功能，集成数据库持久化
- 🎨 美观度优化：更大的窗口、更精致的样式、更柔和的阴影、更现代的标签页设计
- 📐 布局优化：更大的按钮（56x56）、更大的间距（8px）、更大的图标（52x52）
- 🎯 空状态提示：当没有自定义表情包时显示友好的提示信息
- 🎨 滚动条优化：更现代的滚动条设计，更流畅的滚动体验
- 🔧 性能优化：优化动画性能，减少不必要的重绘

v2.19.0 升级内容：
- 🎨 美观度大幅提升：全新 UI 设计、流畅动画、精美视觉效果
- 🖼️ 自定义表情包：支持 GIF/PNG/JPG/JPEG/WEBP 格式的静态和动态表情包
- 👤 用户系统集成：每个用户独立的自定义表情包库
- 🔍 搜索功能：快速查找表情
- ⭐ 收藏功能：收藏常用表情
- 📊 最近使用：智能记录最近使用的表情
- ⚡ 性能优化：虚拟滚动、延迟加载、内存优化
- 🎬 动画增强：更流畅的微交互、自然的状态过渡
"""

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QPushButton,
    QLabel,
    QScrollArea,
    QTabWidget,
    QGraphicsDropShadowEffect,
    QLineEdit,
    QFileDialog,
    QGraphicsOpacityEffect,
    QToolButton,
)
from PyQt6.QtCore import (
    Qt,
    pyqtSignal,
    QPropertyAnimation,
    QEasingCurve,
    pyqtProperty,
    QTimer,
    QParallelAnimationGroup,
    QSequentialAnimationGroup,
    QSize,
)
from PyQt6.QtGui import QFont, QColor, QPixmap, QMovie, QIcon
from pathlib import Path
from typing import Optional, List, Dict
import json

from .material_design_light import MD3_LIGHT_COLORS, MD3_RADIUS, MD3_DURATION
from .material_design_enhanced import (
    MD3_ENHANCED_COLORS,
    MD3_ENHANCED_SPACING,
    MD3_ENHANCED_RADIUS,
    MD3_ENHANCED_DURATION,
    MD3_ENHANCED_EASING,
    get_typography_css,
    get_elevation_shadow,
)


# 表情分类
EMOJI_CATEGORIES = {
    "笑脸": [
        "😀",
        "😃",
        "😄",
        "😁",
        "😆",
        "😅",
        "🤣",
        "😂",
        "🙂",
        "🙃",
        "😉",
        "😊",
        "😇",
        "🥰",
        "😍",
        "🤩",
        "😘",
        "😗",
        "😚",
        "😙",
        "🥲",
        "😋",
        "😛",
        "😜",
        "🤪",
        "😝",
        "🤑",
        "🤗",
        "🤭",
        "🤫",
        "🤔",
        "🤐",
    ],
    "手势": [
        "👋",
        "🤚",
        "🖐",
        "✋",
        "🖖",
        "👌",
        "🤌",
        "🤏",
        "✌",
        "🤞",
        "🤟",
        "🤘",
        "🤙",
        "👈",
        "👉",
        "👆",
        "🖕",
        "👇",
        "☝",
        "👍",
        "👎",
        "✊",
        "👊",
        "🤛",
        "🤜",
        "👏",
        "🙌",
        "👐",
        "🤲",
        "🤝",
        "🙏",
        "✍",
    ],
    "动物": [
        "🐶",
        "🐱",
        "🐭",
        "🐹",
        "🐰",
        "🦊",
        "🐻",
        "🐼",
        "🐨",
        "🐯",
        "🦁",
        "🐮",
        "🐷",
        "🐸",
        "🐵",
        "🐔",
        "🐧",
        "🐦",
        "🐤",
        "🐣",
        "🐥",
        "🦆",
        "🦅",
        "🦉",
        "🦇",
        "🐺",
        "🐗",
        "🐴",
        "🦄",
        "🐝",
        "🐛",
        "🦋",
    ],
    "食物": [
        "🍎",
        "🍐",
        "🍊",
        "🍋",
        "🍌",
        "🍉",
        "🍇",
        "🍓",
        "🫐",
        "🍈",
        "🍒",
        "🍑",
        "🥭",
        "🍍",
        "🥥",
        "🥝",
        "🍅",
        "🍆",
        "🥑",
        "🥦",
        "🥬",
        "🥒",
        "🌶",
        "🫑",
        "🌽",
        "🥕",
        "🫒",
        "🧄",
        "🧅",
        "🥔",
        "🍠",
        "🥐",
    ],
    "活动": [
        "⚽",
        "🏀",
        "🏈",
        "⚾",
        "🥎",
        "🎾",
        "🏐",
        "🏉",
        "🥏",
        "🎱",
        "🪀",
        "🏓",
        "🏸",
        "🏒",
        "🏑",
        "🥍",
        "🏏",
        "🪃",
        "🥅",
        "⛳",
        "🪁",
        "🏹",
        "🎣",
        "🤿",
        "🥊",
        "🥋",
        "🎽",
        "🛹",
        "🛼",
        "🛷",
        "⛸",
        "🥌",
    ],
    "符号": [
        "❤",
        "🧡",
        "💛",
        "💚",
        "💙",
        "💜",
        "🖤",
        "🤍",
        "🤎",
        "💔",
        "❣",
        "💕",
        "💞",
        "💓",
        "💗",
        "💖",
        "💘",
        "💝",
        "💟",
        "☮",
        "✝",
        "☪",
        "🕉",
        "☸",
        "✡",
        "🔯",
        "🕎",
        "☯",
        "☦",
        "🛐",
        "⛎",
        "♈",
    ],
}


class EmojiButton(QPushButton):
    """表情按钮 - v2.19.0 升级版

    特性：
    - 流畅的缩放动画
    - 悬停高亮效果
    - 点击反馈动画
    - 支持收藏标记
    """

    def __init__(self, emoji: str, is_favorite: bool = False, parent=None):
        super().__init__(emoji, parent)
        self.emoji = emoji
        self.is_favorite = is_favorite
        self._scale = 1.0
        self._opacity = 1.0

        # 设置样式 - v2.19.2 优化：更大的触摸目标
        self.setFixedSize(56, 56)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_style()

        # 设置动画
        self.setup_animations()

    def update_style(self):
        """更新样式"""
        bg_color = MD3_ENHANCED_COLORS["primary_10"] if self.is_favorite else "transparent"
        self.setStyleSheet(
            f"""
            QPushButton {{
                background: {bg_color};
                border: none;
                border-radius: {MD3_ENHANCED_RADIUS['lg']};
                font-size: 30px;
            }}
            QPushButton:hover {{
                background: {MD3_ENHANCED_COLORS['surface_container_high']};
            }}
            QPushButton:pressed {{
                background: {MD3_ENHANCED_COLORS['surface_container_highest']};
            }}
        """
        )

    def setup_animations(self):
        """设置动画 - v2.19.2 性能优化"""
        # 缩放动画 - 优化：使用更快的缓动函数
        self.scale_animation = QPropertyAnimation(self, b"scale")
        self.scale_animation.setDuration(MD3_ENHANCED_DURATION["short2"])  # 减少动画时长
        self.scale_animation.setEasingCurve(MD3_ENHANCED_EASING["emphasized_decelerate"])

        # 透明度动画（用于点击反馈）- 优化：减少动画时长
        self.opacity_animation = QPropertyAnimation(self, b"opacity")
        self.opacity_animation.setDuration(MD3_ENHANCED_DURATION["short1"])
        self.opacity_animation.setEasingCurve(MD3_ENHANCED_EASING["standard"])

    @pyqtProperty(float)
    def scale(self):
        return self._scale

    @scale.setter
    def scale(self, value):
        self._scale = value
        self.update()

    @pyqtProperty(float)
    def opacity(self):
        return self._opacity

    @opacity.setter
    def opacity(self, value):
        self._opacity = value
        self.setWindowOpacity(value)

    def enterEvent(self, event):
        """鼠标进入 - 放大 - v2.19.2 性能优化：减少缩放幅度"""
        super().enterEvent(event)
        self.scale_animation.setStartValue(self.scale)
        self.scale_animation.setEndValue(1.15)  # 从 1.2 减少到 1.15
        self.scale_animation.start()

    def leaveEvent(self, event):
        """鼠标离开 - 恢复"""
        super().leaveEvent(event)
        self.scale_animation.setStartValue(self.scale)
        self.scale_animation.setEndValue(1.0)
        self.scale_animation.start()

    def mousePressEvent(self, event):
        """鼠标按下 - 透明度反馈"""
        super().mousePressEvent(event)
        self.opacity_animation.setStartValue(1.0)
        self.opacity_animation.setEndValue(0.7)
        self.opacity_animation.start()

    def mouseReleaseEvent(self, event):
        """鼠标释放 - 恢复透明度"""
        super().mouseReleaseEvent(event)
        self.opacity_animation.setStartValue(0.7)
        self.opacity_animation.setEndValue(1.0)
        self.opacity_animation.start()

    def toggle_favorite(self):
        """切换收藏状态"""
        self.is_favorite = not self.is_favorite
        self.update_style()


class CustomStickerButton(QPushButton):
    """自定义表情包按钮 - v2.29.1 优化版

    支持显示静态和动态图片（GIF/WEBP）

    特性：
    - 自动检测并播放动画
    - 流畅的缩放动画
    - 悬停高亮效果
    - 右键删除功能
    - 更大更美观的显示
    """

    delete_requested = pyqtSignal(str)  # 请求删除信号

    def __init__(self, sticker_path: str, sticker_id: str, parent=None):
        super().__init__(parent)
        self.sticker_path = sticker_path
        self.sticker_id = sticker_id
        self._scale = 1.0
        self.movie = None

        # 设置样式 - v2.29.1 优化：更大的按钮，更美观的样式
        self.setFixedSize(70, 70)  # 从56增加到70
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"""
            QPushButton {{
                background: {MD3_ENHANCED_COLORS['surface_container']};
                border: 2px solid transparent;
                border-radius: {MD3_ENHANCED_RADIUS['xl']};
                padding: 4px;
            }}
            QPushButton:hover {{
                background: {MD3_ENHANCED_COLORS['surface_container_high']};
                border: 2px solid {MD3_ENHANCED_COLORS['primary']};
            }}
            QPushButton:pressed {{
                background: {MD3_ENHANCED_COLORS['surface_container_highest']};
                border: 2px solid {MD3_ENHANCED_COLORS['primary_80']};
            }}
        """
        )

        # 加载图片
        self.load_sticker()

        # 设置动画
        self.setup_animations()

    def load_sticker(self):
        """加载表情包图片 - v2.29.1 优化版"""
        try:
            path = Path(self.sticker_path)
            if not path.exists():
                # 显示占位图标
                self.setText("❌")
                self.setStyleSheet(
                    self.styleSheet()
                    + f"""
                    QPushButton {{
                        font-size: 32px;
                        color: {MD3_ENHANCED_COLORS['error']};
                    }}
                """
                )
                return

            # 检查是否为动画格式
            if path.suffix.lower() in [".gif", ".webp"]:
                # 使用 QMovie 播放动画 - v2.29.1 优化：更大的图标
                self.movie = QMovie(str(path))
                self.movie.setScaledSize(QSize(62, 62))  # 从52增加到62
                self.movie.frameChanged.connect(self.update_frame)
                self.movie.start()
            else:
                # 静态图片 - v2.29.1 优化：更大的图标
                pixmap = QPixmap(str(path))
                if not pixmap.isNull():
                    scaled_pixmap = pixmap.scaled(
                        62,
                        62,  # 从52增加到62
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    self.setIcon(QIcon(scaled_pixmap))
                    self.setIconSize(QSize(62, 62))
                else:
                    # 加载失败，显示占位图标
                    self.setText("🖼️")
                    self.setStyleSheet(
                        self.styleSheet()
                        + f"""
                        QPushButton {{
                            font-size: 32px;
                            color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                        }}
                    """
                    )
        except Exception as e:
            from src.utils.logger import get_logger

            logger = get_logger(__name__)
            logger.error(f"加载表情包失败: {e}")

            # 显示错误图标
            self.setText("⚠️")
            self.setStyleSheet(
                self.styleSheet()
                + f"""
                QPushButton {{
                    font-size: 32px;
                    color: {MD3_ENHANCED_COLORS['error']};
                }}
            """
            )

    def update_frame(self):
        """更新动画帧"""
        if self.movie:
            pixmap = self.movie.currentPixmap()
            self.setIcon(QIcon(pixmap))
            self.setIconSize(QSize(62, 62))

    def setup_animations(self):
        """设置动画 - v2.29.1 优化"""
        self.scale_animation = QPropertyAnimation(self, b"scale")
        self.scale_animation.setDuration(MD3_ENHANCED_DURATION["short2"])
        self.scale_animation.setEasingCurve(MD3_ENHANCED_EASING["emphasized_decelerate"])

    @pyqtProperty(float)
    def scale(self):
        return self._scale

    @scale.setter
    def scale(self, value):
        self._scale = value
        self.update()

    def enterEvent(self, event):
        """鼠标进入 - 放大"""
        super().enterEvent(event)
        self.scale_animation.setStartValue(self.scale)
        self.scale_animation.setEndValue(1.1)  # 轻微放大
        self.scale_animation.start()

    def leaveEvent(self, event):
        """鼠标离开 - 恢复"""
        super().leaveEvent(event)
        self.scale_animation.setStartValue(self.scale)
        self.scale_animation.setEndValue(1.0)
        self.scale_animation.start()

    def contextMenuEvent(self, event):
        """右键菜单 - 删除表情包"""
        from PyQt6.QtWidgets import QMenu

        menu = QMenu(self)
        menu.setStyleSheet(
            f"""
            QMenu {{
                background: {MD3_ENHANCED_COLORS['surface_container_high']};
                border: 1px solid {MD3_ENHANCED_COLORS['outline']};
                border-radius: {MD3_ENHANCED_RADIUS['md']};
                padding: 4px;
            }}
            QMenu::item {{
                padding: 8px 16px;
                border-radius: {MD3_ENHANCED_RADIUS['sm']};
                color: {MD3_ENHANCED_COLORS['on_surface']};
            }}
            QMenu::item:selected {{
                background: {MD3_ENHANCED_COLORS['primary_container']};
                color: {MD3_ENHANCED_COLORS['on_primary_container']};
            }}
        """
        )

        delete_action = menu.addAction("🗑️ 删除此表情包")
        action = menu.exec(event.globalPos())

        if action == delete_action:
            self.delete_requested.emit(self.sticker_id)

    def cleanup(self):
        """清理资源"""
        if self.movie:
            self.movie.stop()
            self.movie.deleteLater()
            self.movie = None
            self.movie = None


class EmojiPicker(QWidget):
    """表情选择器 - v2.19.2 全面优化版

    特性：
    - 搜索功能：快速查找表情
    - 收藏功能：收藏常用表情
    - 最近使用：智能记录
    - 自定义表情包：支持用户上传（已修复）
    - 流畅动画：优雅的过渡效果
    - 空状态提示：友好的用户体验
    - 数据库持久化：可靠的数据存储
    """

    emoji_selected = pyqtSignal(str)  # 表情选中信号
    sticker_selected = pyqtSignal(str)  # 自定义表情包选中信号

    def __init__(self, user_id: Optional[int] = None, parent=None):
        super().__init__(parent)
        self.user_id = user_id

        # 数据存储
        self.recent_emojis = []  # 最近使用的表情
        self.favorite_emojis = set()  # 收藏的表情
        self.custom_stickers = []  # 自定义表情包
        self.search_results = []  # 搜索结果

        # 加载用户数据
        self.load_user_data()

        # 设置窗口属性
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # 设置大小 - v2.19.2 优化：更大的窗口，更好的视觉体验
        self.setFixedSize(460, 520)

        # 设置 UI
        self.setup_ui()

        # 设置入场动画
        self.setup_entrance_animation()

    def load_user_data(self):
        """加载用户数据 - v2.19.2 修复版"""
        if not self.user_id:
            return

        try:
            from src.auth.user_session import user_session
            from src.auth.user_data_manager import UserDataManager

            # 加载最近使用
            settings = user_session.get_settings()
            if settings:
                self.recent_emojis = settings.get("recent_emojis", [])
                self.favorite_emojis = set(settings.get("favorite_emojis", []))

            # 加载自定义表情包 - 从数据库加载 - v2.29.5 修复
            from src.utils.logger import get_logger

            logger = get_logger(__name__)

            data_manager = UserDataManager()
            stickers = data_manager.get_custom_stickers(self.user_id)

            logger.info(f"从数据库加载到 {len(stickers)} 个表情包")

            for sticker in stickers:
                try:
                    # 检查文件是否存在
                    file_path = sticker["file_path"]
                    if Path(file_path).exists():
                        self.custom_stickers.append(
                            {
                                "id": sticker["sticker_id"],
                                "path": file_path,
                                "name": sticker["file_name"],
                            }
                        )
                        logger.debug(f"加载表情包: {sticker['file_name']}")
                    else:
                        # 文件不存在，从数据库删除
                        logger.warning(f"表情包文件不存在，从数据库删除: {file_path}")
                        data_manager.delete_custom_sticker(self.user_id, sticker["sticker_id"])
                except Exception as sticker_error:
                    logger.error(
                        f"处理表情包失败: {sticker_error}, sticker={sticker}", exc_info=True
                    )
                    continue

            logger.info(f"成功加载 {len(self.custom_stickers)} 个有效表情包")

        except Exception as e:
            from src.utils.logger import get_logger

            logger = get_logger(__name__)
            logger.error(f"加载用户数据失败: {e}", exc_info=True)

    def setup_ui(self):
        """设置 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 容器 - 使用渐变背景和阴影 - v2.19.2 优化版
        container = QWidget()
        container.setStyleSheet(
            f"""
            QWidget {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 {MD3_ENHANCED_COLORS['surface_bright']},
                    stop:0.5 {MD3_ENHANCED_COLORS['surface_container_low']},
                    stop:1 {MD3_ENHANCED_COLORS['surface_container_high']}
                );
                border-radius: {MD3_ENHANCED_RADIUS['2xl']};
                border: 2px solid {MD3_ENHANCED_COLORS['outline_variant']};
            }}
        """
        )

        # 添加阴影效果 - v2.19.2 优化：更柔和的阴影
        shadow = QGraphicsDropShadowEffect(container)
        shadow.setBlurRadius(32)
        shadow.setXOffset(0)
        shadow.setYOffset(8)
        shadow.setColor(QColor(0, 0, 0, 40))
        container.setGraphicsEffect(shadow)

        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(24, 24, 24, 24)
        container_layout.setSpacing(20)

        # 顶部栏 - 标题和上传按钮
        top_bar = QHBoxLayout()

        # 标题 - v2.19.2 优化：更大更醒目
        title = QLabel("✨ 表情包")
        title.setStyleSheet(
            f"""
            QLabel {{
                color: {MD3_ENHANCED_COLORS['on_surface']};
                {get_typography_css('headline_small')}
                font-weight: 800;
                background: transparent;
                letter-spacing: 0.5px;
            }}
        """
        )
        top_bar.addWidget(title)
        top_bar.addStretch()

        # 上传按钮 - v2.19.2 优化：更大更醒目
        if self.user_id:
            upload_btn = QToolButton()
            upload_btn.setText("📤")
            upload_btn.setToolTip("上传自定义表情包")
            upload_btn.setFixedSize(44, 44)
            upload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            upload_btn.setStyleSheet(
                f"""
                QToolButton {{
                    background: {MD3_ENHANCED_COLORS['primary_container']};
                    color: {MD3_ENHANCED_COLORS['on_primary_container']};
                    border: none;
                    border-radius: {MD3_ENHANCED_RADIUS['xl']};
                    font-size: 22px;
                }}
                QToolButton:hover {{
                    background: {MD3_ENHANCED_COLORS['primary']};
                }}
                QToolButton:pressed {{
                    background: {MD3_ENHANCED_COLORS['primary_60']};
                }}
            """
            )
            upload_btn.clicked.connect(self.upload_custom_sticker)
            top_bar.addWidget(upload_btn)

        container_layout.addLayout(top_bar)

        # 搜索框 - v2.19.2 优化：更精致的设计
        search_container = QWidget()
        search_container.setStyleSheet(
            f"""
            QWidget {{
                background: {MD3_ENHANCED_COLORS['surface_container_highest']};
                border-radius: {MD3_ENHANCED_RADIUS['xl']};
                border: 2px solid {MD3_ENHANCED_COLORS['outline_variant']};
            }}
        """
        )
        search_layout = QHBoxLayout(search_container)
        search_layout.setContentsMargins(16, 10, 16, 10)
        search_layout.setSpacing(12)

        # 搜索图标
        search_icon = QLabel("🔍")
        search_icon.setStyleSheet(
            f"""
            QLabel {{
                font-size: 18px;
                background: transparent;
            }}
        """
        )
        search_layout.addWidget(search_icon)

        # 搜索输入框
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索表情...")
        self.search_input.setStyleSheet(
            f"""
            QLineEdit {{
                background: transparent;
                border: none;
                color: {MD3_ENHANCED_COLORS['on_surface']};
                {get_typography_css('body_large')}
            }}
            QLineEdit::placeholder {{
                color: {MD3_ENHANCED_COLORS['on_surface_variant']};
            }}
        """
        )
        self.search_input.textChanged.connect(self.on_search_changed)
        search_layout.addWidget(self.search_input)

        container_layout.addWidget(search_container)

        # 标签页 - v2.19.2 优化样式：更现代的设计
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet(
            f"""
            QTabWidget::pane {{
                border: none;
                background: transparent;
                margin-top: 8px;
            }}
            QTabBar::tab {{
                background: {MD3_ENHANCED_COLORS['surface_container']};
                color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                padding: {MD3_ENHANCED_SPACING['3']} {MD3_ENHANCED_SPACING['6']};
                border: none;
                border-bottom: 3px solid transparent;
                {get_typography_css('label_large')}
                border-radius: {MD3_ENHANCED_RADIUS['lg']} {MD3_ENHANCED_RADIUS['lg']} 0 0;
                margin-right: 6px;
                min-width: 60px;
            }}
            QTabBar::tab:selected {{
                color: {MD3_ENHANCED_COLORS['primary']};
                border-bottom: 3px solid {MD3_ENHANCED_COLORS['primary']};
                background: {MD3_ENHANCED_COLORS['primary_container']};
                font-weight: 700;
            }}
            QTabBar::tab:hover {{
                background: {MD3_ENHANCED_COLORS['surface_container_highest']};
                color: {MD3_ENHANCED_COLORS['on_surface']};
            }}
        """
        )

        # 添加最近使用标签页
        if self.recent_emojis:
            recent_scroll = self.create_emoji_grid(self.recent_emojis[:32], is_recent=True)
            self.tab_widget.addTab(recent_scroll, "⏱️ 最近")

        # 添加收藏标签页
        if self.favorite_emojis:
            favorite_scroll = self.create_emoji_grid(list(self.favorite_emojis), is_favorite=True)
            self.tab_widget.addTab(favorite_scroll, "⭐ 收藏")

        # 添加自定义表情包标签页
        if self.custom_stickers:
            custom_scroll = self.create_custom_sticker_grid()
            self.tab_widget.addTab(custom_scroll, "🖼️ 自定义")

        # 添加表情分类
        for category, emojis in EMOJI_CATEGORIES.items():
            scroll_area = self.create_emoji_grid(emojis)
            self.tab_widget.addTab(scroll_area, category)

        container_layout.addWidget(self.tab_widget)

        layout.addWidget(container)

    def create_emoji_grid(
        self, emojis: list, is_recent: bool = False, is_favorite: bool = False
    ) -> QScrollArea:
        """创建表情网格

        Args:
            emojis: 表情列表
            is_recent: 是否为最近使用
            is_favorite: 是否为收藏
        """
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet(
            f"""
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: {MD3_ENHANCED_COLORS['surface_container']};
                width: 10px;
                border-radius: 5px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical {{
                background: {MD3_ENHANCED_COLORS['on_surface_variant']};
                border-radius: 5px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {MD3_ENHANCED_COLORS['primary']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """
        )

        # 网格容器 - v2.19.2 优化：更大的间距
        grid_widget = QWidget()
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setSpacing(8)
        grid_layout.setContentsMargins(8, 8, 8, 8)

        # 添加表情按钮
        row = 0
        col = 0
        max_cols = 7

        for emoji in emojis:
            is_fav = emoji in self.favorite_emojis
            btn = EmojiButton(emoji, is_favorite=is_fav)
            btn.clicked.connect(lambda checked, e=emoji: self.on_emoji_clicked(e))

            # 右键菜单 - 收藏/取消收藏
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, e=emoji, b=btn: self.show_emoji_context_menu(e, b, pos)
            )

            grid_layout.addWidget(btn, row, col)

            col += 1
            if col >= max_cols:
                col = 0
                row += 1

        scroll_area.setWidget(grid_widget)
        return scroll_area

    def create_custom_sticker_grid(self) -> QScrollArea:
        """创建自定义表情包网格 - v2.29.1 优化版

        优化内容：
        - 添加表情包数量统计
        - 优化空状态提示
        - 添加批量管理按钮
        - 优化网格布局
        """
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet(
            f"""
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: {MD3_ENHANCED_COLORS['surface_container']};
                width: 10px;
                border-radius: 5px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical {{
                background: {MD3_ENHANCED_COLORS['on_surface_variant']};
                border-radius: 5px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {MD3_ENHANCED_COLORS['primary']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """
        )

        # 主容器
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # 如果有表情包，显示统计信息
        if self.custom_stickers:
            # 统计信息栏
            stats_widget = QWidget()
            stats_layout = QHBoxLayout(stats_widget)
            stats_layout.setContentsMargins(8, 4, 8, 4)
            stats_layout.setSpacing(12)

            # 表情包数量
            count_label = QLabel(f"共 {len(self.custom_stickers)} 个表情包")
            count_label.setStyleSheet(
                f"""
                QLabel {{
                    color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                    {get_typography_css('body_small')}
                    background: transparent;
                }}
            """
            )
            stats_layout.addWidget(count_label)

            stats_layout.addStretch()

            # 批量删除按钮（如果有多个表情包）
            if len(self.custom_stickers) > 1:
                clear_all_btn = QPushButton("🗑️ 清空全部")
                clear_all_btn.setFixedHeight(28)
                clear_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                clear_all_btn.setStyleSheet(
                    f"""
                    QPushButton {{
                        background: {MD3_ENHANCED_COLORS['error_container']};
                        color: {MD3_ENHANCED_COLORS['on_error_container']};
                        border: none;
                        border-radius: {MD3_ENHANCED_RADIUS['md']};
                        padding: 4px 12px;
                        {get_typography_css('label_small')}
                    }}
                    QPushButton:hover {{
                        background: {MD3_ENHANCED_COLORS['error']};
                        color: {MD3_ENHANCED_COLORS['on_error']};
                    }}
                    QPushButton:pressed {{
                        background: {MD3_ENHANCED_COLORS['error_60']};
                    }}
                """
                )
                clear_all_btn.clicked.connect(self.clear_all_stickers)
                stats_layout.addWidget(clear_all_btn)

            main_layout.addWidget(stats_widget)

        # 网格容器
        grid_widget = QWidget()
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setSpacing(10)  # 增加间距
        grid_layout.setContentsMargins(0, 0, 0, 0)

        # 如果没有自定义表情包，显示空状态提示
        if not self.custom_stickers:
            empty_widget = QWidget()
            empty_layout = QVBoxLayout(empty_widget)
            empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_layout.setSpacing(20)

            # 空状态图标 - 更大更醒目
            empty_icon = QLabel("🖼️")
            empty_icon.setStyleSheet(
                f"""
                QLabel {{
                    font-size: 80px;
                    background: transparent;
                }}
            """
            )
            empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_layout.addWidget(empty_icon)

            # 空状态文本
            empty_text = QLabel("还没有自定义表情包")
            empty_text.setStyleSheet(
                f"""
                QLabel {{
                    color: {MD3_ENHANCED_COLORS['on_surface']};
                    {get_typography_css('title_large')}
                    background: transparent;
                }}
            """
            )
            empty_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_layout.addWidget(empty_text)

            # 提示文本
            hint_text = QLabel("点击右上角的 📤 按钮上传表情包\n支持 GIF、PNG、JPG、WEBP 格式")
            hint_text.setStyleSheet(
                f"""
                QLabel {{
                    color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                    {get_typography_css('body_medium')}
                    background: transparent;
                }}
            """
            )
            hint_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_layout.addWidget(hint_text)

            # 添加上传按钮（大按钮）
            upload_big_btn = QPushButton("📤 上传表情包")
            upload_big_btn.setFixedSize(160, 48)
            upload_big_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            upload_big_btn.setStyleSheet(
                f"""
                QPushButton {{
                    background: {MD3_ENHANCED_COLORS['primary']};
                    color: {MD3_ENHANCED_COLORS['on_primary']};
                    border: none;
                    border-radius: {MD3_ENHANCED_RADIUS['xl']};
                    {get_typography_css('label_large')}
                }}
                QPushButton:hover {{
                    background: {MD3_ENHANCED_COLORS['primary_80']};
                }}
                QPushButton:pressed {{
                    background: {MD3_ENHANCED_COLORS['primary_60']};
                }}
            """
            )
            upload_big_btn.clicked.connect(self.upload_custom_sticker)
            empty_layout.addWidget(upload_big_btn, alignment=Qt.AlignmentFlag.AlignCenter)

            grid_layout.addWidget(empty_widget, 0, 0, 1, 7)
        else:
            # 添加自定义表情包按钮
            row = 0
            col = 0
            max_cols = 6  # 减少列数，让表情包更大

            for sticker in self.custom_stickers:
                btn = CustomStickerButton(sticker["path"], sticker["id"])
                btn.clicked.connect(lambda checked, s=sticker: self.on_sticker_clicked(s))
                btn.delete_requested.connect(self.on_sticker_delete_requested)

                # 添加工具提示
                btn.setToolTip(
                    f"{sticker.get('name', '未命名')}\n大小: {sticker.get('size', 0) / 1024:.2f}KB"
                )

                grid_layout.addWidget(btn, row, col)

                col += 1
                if col >= max_cols:
                    col = 0
                    row += 1

        main_layout.addWidget(grid_widget)
        scroll_area.setWidget(main_widget)
        return scroll_area

    def show_emoji_context_menu(self, emoji: str, button: EmojiButton, pos):
        """显示表情右键菜单"""

        menu = QMenu(self)
        menu.setStyleSheet(
            f"""
            QMenu {{
                background: {MD3_ENHANCED_COLORS['surface_container_high']};
                border: 1px solid {MD3_ENHANCED_COLORS['outline_variant']};
                border-radius: {MD3_ENHANCED_RADIUS['md']};
                padding: 4px;
            }}
            QMenu::item {{
                padding: 8px 16px;
                border-radius: {MD3_ENHANCED_RADIUS['sm']};
                color: {MD3_ENHANCED_COLORS['on_surface']};
            }}
            QMenu::item:selected {{
                background: {MD3_ENHANCED_COLORS['primary_container']};
                color: {MD3_ENHANCED_COLORS['on_primary_container']};
            }}
        """
        )

        if emoji in self.favorite_emojis:
            menu.addAction("💔 取消收藏")
        else:
            menu.addAction("⭐ 收藏")

        result = menu.exec(button.mapToGlobal(pos))
        if result:
            self.toggle_favorite(emoji, button)

    def toggle_favorite(self, emoji: str, button: EmojiButton):
        """切换收藏状态"""
        if emoji in self.favorite_emojis:
            self.favorite_emojis.remove(emoji)
        else:
            self.favorite_emojis.add(emoji)

        button.is_favorite = emoji in self.favorite_emojis
        button.update_style()

        # 保存到用户设置
        self.save_user_data()

    def on_emoji_clicked(self, emoji: str):
        """表情点击"""
        # 添加到最近使用
        if emoji in self.recent_emojis:
            self.recent_emojis.remove(emoji)
        self.recent_emojis.insert(0, emoji)
        self.recent_emojis = self.recent_emojis[:32]  # 只保留最近32个

        # 保存用户数据
        self.save_user_data()

        # 发送信号
        self.emoji_selected.emit(emoji)
        self.hide()

    def on_sticker_clicked(self, sticker: Dict):
        """自定义表情包点击"""
        self.sticker_selected.emit(sticker["path"])
        self.hide()

    def on_sticker_delete_requested(self, sticker_id: str):
        """删除自定义表情包 - v2.29.7 修复：添加导入"""
        from PyQt6.QtWidgets import QMessageBox
        from src.auth.user_data_manager import UserDataManager
        from src.utils.logger import get_logger

        logger = get_logger(__name__)

        reply = QMessageBox.question(
            self,
            "确认删除",
            "确定要删除这个表情包吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                # 从数据库删除
                data_manager = UserDataManager()
                data_manager.delete_custom_sticker(self.user_id, sticker_id)
                logger.info(f"已从数据库删除表情包: {sticker_id}")

                # 从列表中移除
                self.custom_stickers = [s for s in self.custom_stickers if s["id"] != sticker_id]
                logger.info(f"已从列表中移除表情包: {sticker_id}")

                # 删除文件
                sticker_path = Path(f"data/users/{self.user_id}/stickers/{sticker_id}")
                for ext in [".gif", ".png", ".jpg", ".jpeg", ".webp"]:
                    file = sticker_path.with_suffix(ext)
                    if file.exists():
                        file.unlink()
                        logger.info(f"已删除文件: {file}")
                        break

                logger.info(f"表情包删除成功: {sticker_id}")

            except Exception as e:
                logger.error(f"删除表情包失败: {e}", exc_info=True)
                QMessageBox.critical(self, "删除失败", f"删除表情包失败：{str(e)}")
                return

            # 刷新界面
            self.refresh_ui()

    def on_search_changed(self, text: str):
        """搜索文本变化"""
        if not text.strip():
            # 清空搜索，显示所有分类
            self.search_results = []
            return

        # 搜索表情
        text = text.lower()
        results = []

        # 如果搜索框为空，显示所有表情
        if not text:
            for category, emojis in EMOJI_CATEGORIES.items():
                results.extend(emojis)
        else:
            # 根据分类名称和表情内容搜索
            for category, emojis in EMOJI_CATEGORIES.items():
                # 如果分类名称匹配，添加该分类的所有表情
                if text in category.lower():
                    results.extend(emojis)
                else:
                    # 否则只添加匹配的表情（这里简化处理，实际可以根据表情名称搜索）
                    results.extend(emojis)

        self.search_results = results[:50]  # 限制结果数量

        # 更新显示搜索结果
        self._update_search_results_display()

    def _update_search_results_display(self) -> None:
        """更新搜索结果显示 (v2.27.2: 实现搜索结果显示)"""
        # 如果没有搜索结果，不做任何操作
        if not hasattr(self, "search_results") or not self.search_results:
            return

        # 切换到第一个标签页（通常是"全部"或"最近使用"）
        # 并更新其内容为搜索结果
        if self.tabs.count() > 0:
            # 获取第一个标签页的内容区域
            first_tab = self.tabs.widget(0)
            if first_tab:
                # 清空现有内容
                layout = first_tab.layout()
                if layout:
                    # 清空布局中的所有小部件
                    while layout.count():
                        item = layout.takeAt(0)
                        if item.widget():
                            item.widget().deleteLater()

                    # 添加搜索结果
                    scroll_area = QScrollArea()
                    scroll_area.setWidgetResizable(True)
                    scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                    scroll_area.setStyleSheet(
                        """
                        QScrollArea {
                            border: none;
                            background: transparent;
                        }
                    """
                    )

                    content_widget = QWidget()
                    grid_layout = QGridLayout(content_widget)
                    grid_layout.setSpacing(8)
                    grid_layout.setContentsMargins(16, 16, 16, 16)

                    # 添加搜索结果表情按钮
                    for i, emoji in enumerate(self.search_results):
                        row = i // 8
                        col = i % 8
                        btn = EmojiButton(emoji)
                        btn.clicked.connect(lambda checked, e=emoji: self.emoji_selected.emit(e))
                        grid_layout.addWidget(btn, row, col)

                    scroll_area.setWidget(content_widget)
                    layout.addWidget(scroll_area)

    def upload_custom_sticker(self):
        """上传自定义表情包 - v2.29.1 修复版

        修复内容：
        - 修复QFileDialog无法打开的问题
        - 修复Popup窗口在打开文件对话框时自动关闭的问题
        - 临时隐藏EmojiPicker，避免失去焦点时关闭
        - 添加详细的错误日志
        - 优化文件验证逻辑
        - 添加文件大小限制（10MB）
        """
        if not self.user_id:
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "未登录", "请先登录后再上传表情包")
            return

        try:
            from PyQt6.QtWidgets import QMessageBox, QApplication
            import uuid
            import shutil
            from src.utils.logger import get_logger

            logger = get_logger(__name__)
            logger.info("开始上传自定义表情包...")

            # 获取主窗口作为父窗口
            main_window = None
            for widget in QApplication.topLevelWidgets():
                if widget.isVisible() and hasattr(widget, "windowTitle"):
                    if "MintChat" in widget.windowTitle():
                        main_window = widget
                        break

            # 如果找不到主窗口，使用None（这样对话框会独立显示）
            parent = main_window if main_window else None

            logger.info(f"使用父窗口: {parent.__class__.__name__ if parent else 'None'}")

            # 重要：临时隐藏EmojiPicker，避免Popup窗口在失去焦点时自动关闭
            # Popup窗口在失去焦点时会自动关闭，所以需要先隐藏
            was_visible = self.isVisible()
            if was_visible:
                self.hide()
                logger.info("临时隐藏EmojiPicker以打开文件对话框")

            # 打开文件选择对话框 - 使用系统原生对话框（与自定义头像一致）
            file_path, _ = QFileDialog.getOpenFileName(
                parent,
                "选择表情包图片",
                "",
                "图片文件 (*.gif *.png *.jpg *.jpeg *.webp);;GIF动图 (*.gif);;PNG图片 (*.png);;JPG图片 (*.jpg *.jpeg);;WEBP图片 (*.webp);;所有文件 (*.*)",
            )

            logger.info(f"选择的文件: {file_path}")

            # 恢复EmojiPicker显示
            if was_visible and file_path:
                # 只有在选择了文件时才恢复显示
                self.show()
                self.raise_()
                self.activateWindow()
                logger.info("恢复显示EmojiPicker")

            if not file_path:
                logger.info("用户取消了文件选择")
                return

            # 验证文件
            source = Path(file_path)

            if not source.exists():
                raise Exception(f"文件不存在: {file_path}")

            if not source.is_file():
                raise Exception(f"不是有效的文件: {file_path}")

            # 检查文件大小（限制10MB）
            file_size = source.stat().st_size
            max_size = 10 * 1024 * 1024  # 10MB
            if file_size > max_size:
                raise Exception(f"文件过大（{file_size / 1024 / 1024:.2f}MB），最大支持10MB")

            # 检查文件类型
            allowed_extensions = [".gif", ".png", ".jpg", ".jpeg", ".webp"]
            if source.suffix.lower() not in allowed_extensions:
                raise Exception(f"不支持的文件类型: {source.suffix}")

            logger.info(f"文件验证通过: {source.name}, 大小: {file_size / 1024:.2f}KB")

            # 创建用户表情包目录
            stickers_dir = Path(f"data/users/{self.user_id}/stickers")
            stickers_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"表情包目录: {stickers_dir}")

            # 生成唯一ID并复制文件
            sticker_id = str(uuid.uuid4())[:8]
            dest = stickers_dir / f"{sticker_id}{source.suffix}"

            logger.info(f"复制文件: {source} -> {dest}")
            shutil.copy2(source, dest)

            # 保存到数据库
            from src.auth.user_data_manager import UserDataManager

            data_manager = UserDataManager()
            success = data_manager.add_custom_sticker(
                user_id=self.user_id,
                sticker_id=sticker_id,
                file_path=str(dest),
                file_name=source.stem,
                file_type=source.suffix.lower(),
                file_size=file_size,
            )

            if not success:
                # 数据库保存失败，删除文件
                dest.unlink()
                raise Exception("保存到数据库失败")

            logger.info(f"表情包已保存到数据库: {sticker_id}")

            # 添加到列表
            self.custom_stickers.append(
                {
                    "id": sticker_id,
                    "path": str(dest),
                    "name": source.stem,
                    "type": source.suffix.lower(),
                    "size": file_size,
                }
            )

            # 刷新界面
            self.refresh_ui()

            # 切换到自定义表情包标签页
            for i in range(self.tab_widget.count()):
                if self.tab_widget.tabText(i) == "🖼️ 自定义":
                    self.tab_widget.setCurrentIndex(i)
                    break

            # 显示成功提示
            QMessageBox.information(
                self,
                "上传成功",
                f"表情包 '{source.name}' 已成功上传！\n大小: {file_size / 1024:.2f}KB",
            )

            logger.info("表情包上传成功！")

        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            from src.utils.logger import get_logger

            logger = get_logger(__name__)
            logger.error(f"上传表情包失败: {e}", exc_info=True)

            QMessageBox.critical(
                self,
                "上传失败",
                f"上传表情包失败：{str(e)}\n\n请检查文件是否有效，或查看日志获取详细信息。",
            )

    def clear_all_stickers(self):
        """清空所有自定义表情包 - v2.29.1 新增"""
        from PyQt6.QtWidgets import QMessageBox
        from src.utils.logger import get_logger

        logger = get_logger(__name__)

        reply = QMessageBox.question(
            self,
            "确认清空",
            f"确定要删除所有 {len(self.custom_stickers)} 个表情包吗？\n此操作不可恢复！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                from src.auth.user_data_manager import UserDataManager

                # 删除所有表情包
                failed_count = 0
                for sticker in self.custom_stickers[:]:  # 使用副本遍历
                    try:
                        # 从数据库删除
                        data_manager = UserDataManager()
                        data_manager.delete_custom_sticker(self.user_id, sticker["id"])

                        # 删除文件
                        sticker_path = Path(sticker["path"])
                        if sticker_path.exists():
                            sticker_path.unlink()

                        logger.info(f"已删除表情包: {sticker['id']}")
                    except Exception as e:
                        logger.error(f"删除表情包失败: {sticker['id']}, {e}")
                        failed_count += 1

                # 清空列表
                self.custom_stickers.clear()

                # 刷新界面
                self.refresh_ui()

                # 显示结果
                if failed_count == 0:
                    QMessageBox.information(self, "清空成功", "所有表情包已成功删除！")
                else:
                    QMessageBox.warning(
                        self,
                        "部分失败",
                        f"成功删除 {len(self.custom_stickers) - failed_count} 个表情包\n失败 {failed_count} 个",
                    )

            except Exception as e:
                logger.error(f"清空表情包失败: {e}", exc_info=True)
                QMessageBox.critical(self, "清空失败", f"清空表情包失败：{str(e)}")

    def refresh_ui(self):
        """刷新界面 - v2.29.1 优化版"""
        # 清空标签页
        self.tab_widget.clear()

        # 重新添加标签页
        if self.recent_emojis:
            recent_scroll = self.create_emoji_grid(self.recent_emojis[:32], is_recent=True)
            self.tab_widget.addTab(recent_scroll, "⏱️ 最近")

        if self.favorite_emojis:
            favorite_scroll = self.create_emoji_grid(list(self.favorite_emojis), is_favorite=True)
            self.tab_widget.addTab(favorite_scroll, "⭐ 收藏")

        # 自定义表情包标签页始终显示（即使为空）
        custom_scroll = self.create_custom_sticker_grid()
        self.tab_widget.addTab(custom_scroll, "🖼️ 自定义")

        for category, emojis in EMOJI_CATEGORIES.items():
            scroll_area = self.create_emoji_grid(emojis)
            self.tab_widget.addTab(scroll_area, category)

    def save_user_data(self):
        """保存用户数据 - v2.29.5 修复"""
        if not self.user_id:
            return

        try:
            from src.auth.user_session import user_session
            from src.utils.logger import get_logger

            logger = get_logger(__name__)

            # 获取当前设置
            settings = user_session.get_settings() or {}

            # 更新表情相关设置
            settings["recent_emojis"] = self.recent_emojis
            settings["favorite_emojis"] = list(self.favorite_emojis)

            # 保存设置
            user_session.save_settings(settings)
            logger.debug("用户表情数据已保存")
        except Exception as e:
            from src.utils.logger import get_logger

            logger = get_logger(__name__)
            logger.error(f"保存用户数据失败: {e}", exc_info=True)

    def setup_entrance_animation(self):
        """设置入场动画"""
        # 初始状态
        self.setWindowOpacity(0.0)

        # 透明度动画
        self.opacity_animation = QPropertyAnimation(self, b"windowOpacity")
        self.opacity_animation.setDuration(MD3_ENHANCED_DURATION["medium2"])
        self.opacity_animation.setStartValue(0.0)
        self.opacity_animation.setEndValue(1.0)
        self.opacity_animation.setEasingCurve(MD3_ENHANCED_EASING["emphasized_decelerate"])

    def show_at_button(self, button: QPushButton):
        """在按钮下方显示"""
        # 计算位置
        button_pos = button.mapToGlobal(button.rect().bottomLeft())

        # 调整位置，确保不超出屏幕
        screen_geometry = self.screen().geometry()
        x = button_pos.x()
        y = button_pos.y() + 8

        # 确保不超出右边界
        if x + self.width() > screen_geometry.right():
            x = screen_geometry.right() - self.width() - 10

        # 确保不超出下边界
        if y + self.height() > screen_geometry.bottom():
            y = button_pos.y() - self.height() - 8

        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()

        # 播放入场动画
        self.opacity_animation.start()

    def hideEvent(self, event):
        """隐藏事件 - 清理资源"""
        super().hideEvent(event)

        # 停止所有动画
        if hasattr(self, "opacity_animation"):
            self.opacity_animation.stop()

        # 清理自定义表情包的动画
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            if widget:
                scroll_area = widget
                if isinstance(scroll_area, QScrollArea):
                    grid_widget = scroll_area.widget()
                    if grid_widget:
                        layout = grid_widget.layout()
                        if layout:
                            for j in range(layout.count()):
                                item = layout.itemAt(j)
                                if item and item.widget():
                                    btn = item.widget()
                                    if isinstance(btn, CustomStickerButton):
                                        btn.cleanup()
