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
    QAbstractScrollArea,
    QTabWidget,
    QGraphicsDropShadowEffect,
    QLineEdit,
    QFileDialog,
)
from PyQt6.QtCore import (
    Qt,
    pyqtSignal,
    QPropertyAnimation,
    pyqtProperty,
    QSize,
)
from PyQt6.QtGui import QColor, QPixmap, QMovie, QIcon, QImageReader
from pathlib import Path
from typing import Optional, Dict
from functools import lru_cache

from .material_design_enhanced import (
    MD3_ENHANCED_COLORS,
    MD3_ENHANCED_SPACING,
    MD3_ENHANCED_RADIUS,
    MD3_ENHANCED_DURATION,
    MD3_ENHANCED_EASING,
    get_typography_css,
)
from .material_icons import MaterialIconButton, MaterialIcon


_STICKER_BUTTON_SIZE = 70
_STICKER_ICON_SIZE = 62
_STICKER_ANIM_EXTS = {".gif", ".webp"}


@lru_cache(maxsize=256)
def _load_sticker_preview_pixmap(path: str, size: int, mtime_ns: int) -> QPixmap:
    """加载表情包预览图（LRU缓存，含 mtime 失效键）。"""
    _ = mtime_ns  # 仅用于缓存键，文件变更时自动失效
    # 性能：优先用 QImageReader 按目标尺寸解码，避免先解码大图再缩放导致卡顿/内存飙升
    try:
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        original = reader.size()
        if original.isValid() and (original.width() > size or original.height() > size):
            target = QSize(size, size)
            reader.setScaledSize(original.scaled(target, Qt.AspectRatioMode.KeepAspectRatio))
        image = reader.read()
        if not image.isNull():
            return QPixmap.fromImage(image)
    except Exception:
        pass

    pixmap = QPixmap(path)
    if pixmap.isNull():
        return pixmap
    if pixmap.width() > size or pixmap.height() > size:
        pixmap = pixmap.scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    return pixmap


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

_ALL_EMOJIS = frozenset(emoji for emojis in EMOJI_CATEGORIES.values() for emoji in emojis)


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
        self._is_animated = False
        self._preview_icon: Optional[QIcon] = None

        # 设置样式 - v2.29.1 优化：更大的按钮，更美观的样式
        self.setFixedSize(_STICKER_BUTTON_SIZE, _STICKER_BUTTON_SIZE)  # 从56增加到70
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
        """加载表情包预览图（默认静态），动画在悬停时按需启用。"""
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

            self._is_animated = path.suffix.lower() in _STICKER_ANIM_EXTS
            try:
                mtime_ns = path.stat().st_mtime_ns
            except OSError:
                mtime_ns = 0

            pixmap = _load_sticker_preview_pixmap(str(path), _STICKER_ICON_SIZE, mtime_ns)
            if not pixmap.isNull():
                self._preview_icon = QIcon(pixmap)
                self.setIcon(self._preview_icon)
                self.setIconSize(QSize(_STICKER_ICON_SIZE, _STICKER_ICON_SIZE))
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
            if not pixmap.isNull():
                self.setIcon(QIcon(pixmap))
                self.setIconSize(QSize(_STICKER_ICON_SIZE, _STICKER_ICON_SIZE))

    def _ensure_movie(self) -> None:
        if self.movie is not None:
            return
        path = Path(self.sticker_path)
        if not path.exists():
            return
        if path.suffix.lower() not in _STICKER_ANIM_EXTS:
            return
        self.movie = QMovie(str(path))
        # 性能/内存：避免缓存所有帧（长时间悬停或大量动图时更稳）
        try:
            self.movie.setCacheMode(QMovie.CacheMode.CacheNone)
        except Exception:
            pass
        self.movie.setScaledSize(QSize(_STICKER_ICON_SIZE, _STICKER_ICON_SIZE))
        self.movie.frameChanged.connect(self.update_frame)

    def _start_animation(self) -> None:
        if not self._is_animated:
            return
        self._ensure_movie()
        if self.movie is None:
            return
        if self.movie.state() != QMovie.MovieState.Running:
            self.movie.start()

    def _stop_animation(self) -> None:
        if self.movie is None:
            return
        if self.movie.state() == QMovie.MovieState.Running:
            self.movie.stop()
        if self._preview_icon is not None:
            self.setIcon(self._preview_icon)
            self.setIconSize(QSize(_STICKER_ICON_SIZE, _STICKER_ICON_SIZE))

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
        # 性能优化：仅在悬停时播放动图，避免大量 QMovie 常驻占用 CPU
        self._start_animation()

    def leaveEvent(self, event):
        """鼠标离开 - 恢复"""
        super().leaveEvent(event)
        self.scale_animation.setStartValue(self.scale)
        self.scale_animation.setEndValue(1.0)
        self.scale_animation.start()
        self._stop_animation()

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
        self.search_results = []  # 搜索结果（emoji/sticker 混合）
        self._sticker_caption_threads = []  # 后台生成表情包说明标签的线程引用（避免被 GC）
        self._sticker_caption_in_progress = set()  # sticker_id 去重，避免重复生成 caption
        self._lazy_tab_builders: dict[int, dict[str, object]] = {}

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

            # 确保不会重复追加
            self.custom_stickers = []

            # 加载最近使用
            settings = user_session.get_settings()
            if settings:
                self.recent_emojis = settings.get("recent_emojis", [])
                self.favorite_emojis = set(settings.get("favorite_emojis", []))

            # 加载自定义表情包 - 从数据库加载 - v2.29.5 修复
            from src.utils.logger import get_logger

            logger = get_logger(__name__)

            data_manager = user_session.data_manager
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
                                "type": sticker.get("file_type"),
                                "size": sticker.get("file_size"),
                                "caption": sticker.get("caption"),
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
        title_icon = MaterialIcon("emoji_emotions", size=22)
        title_icon.setStyleSheet(
            f"""
            QLabel {{
                color: {MD3_ENHANCED_COLORS['on_surface']};
                background: transparent;
            }}
        """
        )
        top_bar.addWidget(title_icon)

        title = QLabel("表情包")
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
            upload_btn = MaterialIconButton("add", "上传自定义表情包", size=44, icon_size=22)
            upload_btn.setToolTip("上传自定义表情包")
            upload_btn.setFixedSize(44, 44)
            upload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            upload_btn.setStyleSheet(
                f"""
                QPushButton {{
                    background: {MD3_ENHANCED_COLORS['primary_container']};
                    color: {MD3_ENHANCED_COLORS['on_primary_container']};
                    border: none;
                    border-radius: {MD3_ENHANCED_RADIUS['xl']};
                }}
                QPushButton:hover {{
                    background: {MD3_ENHANCED_COLORS['primary']};
                    color: {MD3_ENHANCED_COLORS['on_primary']};
                }}
                QPushButton:pressed {{
                    background: {MD3_ENHANCED_COLORS['primary_60']};
                    color: {MD3_ENHANCED_COLORS['on_primary']};
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
        search_icon = MaterialIcon("search", size=18)
        search_icon.setStyleSheet(
            f"""
            QLabel {{
                color: {MD3_ENHANCED_COLORS['on_surface_variant']};
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

        # 搜索结果区域（默认隐藏）：搜索时显示，避免破坏 tab 结构并减少重建开销
        self.search_results_area = QScrollArea()
        self.search_results_area.setWidgetResizable(True)
        try:
            if hasattr(self.search_results_area, "setViewportUpdateMode"):
                self.search_results_area.setViewportUpdateMode(
                    QAbstractScrollArea.ViewportUpdateMode.MinimalViewportUpdate
                )
        except Exception:
            pass
        self.search_results_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.search_results_area.setStyleSheet(
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
        self.search_results_area.hide()

        self._search_results_widget = QWidget()
        self._search_results_grid = QGridLayout(self._search_results_widget)
        self._search_results_grid.setSpacing(8)
        self._search_results_grid.setContentsMargins(8, 8, 8, 8)
        self.search_results_area.setWidget(self._search_results_widget)
        container_layout.addWidget(self.search_results_area)

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

        # 标签页内容按需创建：减少首次打开时的 widget 数量与动画对象，提升弹窗打开速度
        self._build_tabs()

        container_layout.addWidget(self.tab_widget)

        layout.addWidget(container)

    def _create_tab_placeholder(self, text: str) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 24, 0, 0)
        layout.setSpacing(12)

        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(
            f"""
            QLabel {{
                color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                {get_typography_css('body_medium')}
                background: transparent;
            }}
        """
        )
        layout.addWidget(label)
        layout.addStretch()
        return widget

    def _build_tabs(self) -> None:
        """构建/重建标签页（类别页按需延迟创建）。"""
        try:
            self._lazy_tab_builders.clear()
        except Exception:
            self._lazy_tab_builders = {}

        # 最近使用
        if self.recent_emojis:
            recent_scroll = self.create_emoji_grid(self.recent_emojis[:32])
            self.tab_widget.addTab(recent_scroll, "最近")

        # 收藏
        if self.favorite_emojis:
            favorite_scroll = self.create_emoji_grid(list(self.favorite_emojis))
            self.tab_widget.addTab(favorite_scroll, "收藏")

        # 自定义（始终显示；内容按需创建）
        custom_placeholder = self._create_tab_placeholder("加载自定义表情包…")
        custom_index = self.tab_widget.addTab(custom_placeholder, "自定义")
        self._lazy_tab_builders[custom_index] = {"kind": "custom"}

        # 分类（按需创建）
        for category, emojis in EMOJI_CATEGORIES.items():
            placeholder = self._create_tab_placeholder("加载中…")
            idx = self.tab_widget.addTab(placeholder, category)
            self._lazy_tab_builders[idx] = {"kind": "emoji", "emojis": emojis}

        try:
            self.tab_widget.currentChanged.disconnect(self._on_tab_changed)
        except Exception:
            pass
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        self._on_tab_changed(self.tab_widget.currentIndex())

    def _on_tab_changed(self, index: int) -> None:
        """懒加载标签页内容：首次切换到该页时才创建滚动网格。"""
        try:
            builder = self._lazy_tab_builders.pop(int(index), None)
        except Exception:
            builder = None
        if not builder:
            return

        placeholder = self.tab_widget.widget(index)
        label = self.tab_widget.tabText(index)

        kind = str(builder.get("kind") or "")
        if kind == "custom":
            new_widget = self.create_custom_sticker_grid()
        else:
            emojis = builder.get("emojis") or []
            new_widget = self.create_emoji_grid(list(emojis))

        old_block = self.tab_widget.blockSignals(True)
        try:
            self.tab_widget.removeTab(index)
            self.tab_widget.insertTab(index, new_widget, label)
        finally:
            self.tab_widget.blockSignals(old_block)

        try:
            self.tab_widget.setCurrentIndex(index)
        except Exception:
            pass

        if placeholder is not None:
            try:
                placeholder.deleteLater()
            except Exception:
                pass

    def _set_search_active(self, active: bool) -> None:
        """切换搜索结果视图与分类标签页视图。"""
        try:
            self.search_results_area.setVisible(bool(active))
            self.tab_widget.setVisible(not bool(active))
        except Exception:
            pass

    def create_emoji_grid(self, emojis: list) -> QScrollArea:
        """创建表情网格

        Args:
            emojis: 表情列表
        """
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        # 性能：减少滚动时的无效重绘（不同 PyQt 版本可能不提供该 API，需兼容）
        try:
            if hasattr(scroll_area, "setViewportUpdateMode"):
                scroll_area.setViewportUpdateMode(
                    QAbstractScrollArea.ViewportUpdateMode.MinimalViewportUpdate
                )
        except Exception:
            pass
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
        # 性能：减少滚动时的无效重绘（不同 PyQt 版本可能不提供该 API，需兼容）
        try:
            if hasattr(scroll_area, "setViewportUpdateMode"):
                scroll_area.setViewportUpdateMode(
                    QAbstractScrollArea.ViewportUpdateMode.MinimalViewportUpdate
                )
        except Exception:
            pass
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
                """
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
                btn = CustomStickerButton(sticker["path"], sticker["id"], parent=grid_widget)
                btn.clicked.connect(lambda checked, s=sticker: self.on_sticker_clicked(s))
                btn.delete_requested.connect(self.on_sticker_delete_requested)

                # 添加工具提示
                size_kb = None
                try:
                    size_value = sticker.get("size")
                    if size_value is not None:
                        size_kb = float(size_value) / 1024
                except Exception:
                    size_kb = None
                btn.setToolTip(
                    f"{sticker.get('name', '未命名')}\n大小: {size_kb:.2f}KB"
                    if size_kb is not None
                    else f"{sticker.get('name', '未命名')}\n大小: 未知"
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
        try:
            sticker_id = str(sticker.get("id") or "").strip()
            sticker_path = str(sticker.get("path") or "").strip()
            caption = str(sticker.get("caption") or "").strip()
            fallback_name = str(sticker.get("name") or "").strip()
            if self.user_id and sticker_id and sticker_path and not caption:
                self._schedule_sticker_caption_generation(
                    sticker_id=sticker_id,
                    sticker_path=sticker_path,
                    fallback_name=fallback_name,
                )
        except Exception:
            pass
        self.sticker_selected.emit(sticker["path"])
        self.hide()

    def on_sticker_delete_requested(self, sticker_id: str):
        """删除自定义表情包 - v2.29.7 修复：添加导入"""
        from PyQt6.QtWidgets import QMessageBox
        from src.auth.user_session import user_session
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
                # 先从内存列表中拿到文件路径（删除 DB 后仍可删除文件）
                file_path_to_delete = None
                try:
                    for s in self.custom_stickers:
                        if s.get("id") == sticker_id:
                            file_path_to_delete = s.get("path")
                            break
                except Exception:
                    file_path_to_delete = None

                # 从数据库删除
                data_manager = user_session.data_manager
                data_manager.delete_custom_sticker(self.user_id, sticker_id)
                logger.info(f"已从数据库删除表情包: {sticker_id}")

                # 从列表中移除
                self.custom_stickers = [s for s in self.custom_stickers if s["id"] != sticker_id]
                logger.info(f"已从列表中移除表情包: {sticker_id}")

                # 删除文件
                deleted = False
                if file_path_to_delete:
                    try:
                        file = Path(str(file_path_to_delete))
                        if file.exists():
                            file.unlink()
                            deleted = True
                            logger.info(f"已删除文件: {file}")
                    except Exception:
                        deleted = False

                # 兜底：历史数据可能缺 path，按 sticker_id 扫描常见扩展名
                if not deleted:
                    try:
                        from src.config.settings import settings

                        sticker_path = (
                            Path(settings.data_dir)
                            / "users"
                            / str(self.user_id)
                            / "stickers"
                            / str(sticker_id)
                        )
                    except Exception:
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
        """搜索文本变化（优先匹配：自定义表情包 caption/文件名、分类名称、直接输入 emoji）。"""
        query = (text or "").strip()
        if not query:
            self.search_results = []
            self._set_search_active(False)
            return

        q = query.lower()
        results: list[dict[str, object]] = []

        # 1) 自定义表情包：匹配 caption 或文件名
        for sticker in list(getattr(self, "custom_stickers", []) or []):
            try:
                caption = str(sticker.get("caption") or "")
                name = str(sticker.get("name") or "")
                if q in caption.lower() or q in name.lower():
                    results.append({"type": "sticker", "sticker": sticker})
            except Exception:
                continue

        # 2) 分类名称匹配：返回该分类下的所有 emoji
        for category, emojis in EMOJI_CATEGORIES.items():
            try:
                if q in str(category).lower():
                    for emoji in emojis:
                        results.append({"type": "emoji", "emoji": emoji})
            except Exception:
                continue

        # 3) 直接输入 emoji：如果命中已知表情，提升到最前
        if query in _ALL_EMOJIS:
            results.insert(0, {"type": "emoji", "emoji": query})

        # 去重（保持顺序）
        emoji_seen: set[str] = set()
        sticker_seen: set[str] = set()
        deduped: list[dict[str, object]] = []
        for item in results:
            kind = str(item.get("type") or "")
            if kind == "emoji":
                emoji = str(item.get("emoji") or "")
                if not emoji or emoji in emoji_seen:
                    continue
                emoji_seen.add(emoji)
                deduped.append(item)
                continue

            if kind == "sticker":
                sticker = item.get("sticker") or {}
                try:
                    key = str(sticker.get("id") or sticker.get("path") or "")
                except Exception:
                    key = ""
                if not key or key in sticker_seen:
                    continue
                sticker_seen.add(key)
                deduped.append(item)

        self.search_results = deduped[:64]
        self._update_search_results_display()
        self._set_search_active(True)

    def _update_search_results_display(self) -> None:
        """更新搜索结果显示（使用独立滚动区域，避免破坏 tab 内容结构）。"""
        grid = getattr(self, "_search_results_grid", None)
        if grid is None:
            return

        # 清空旧内容
        while grid.count():
            item = grid.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.deleteLater()

        results = list(getattr(self, "search_results", []) or [])
        if not results:
            empty = QLabel("未找到匹配结果")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(
                f"""
                QLabel {{
                    color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                    {get_typography_css('body_medium')}
                    background: transparent;
                    padding: 24px 0;
                }}
            """
            )
            grid.addWidget(empty, 0, 0)
            return

        cols = 7
        for idx, item in enumerate(results):
            row = idx // cols
            col = idx % cols
            kind = str(item.get("type") or "")

            if kind == "sticker":
                sticker = item.get("sticker") or {}
                try:
                    sticker_id = str(sticker.get("id") or "")
                except Exception:
                    sticker_id = ""
                try:
                    sticker_path = str(sticker.get("path") or "")
                except Exception:
                    sticker_path = ""

                if sticker_id and sticker_path:
                    btn = CustomStickerButton(sticker_path, sticker_id)
                    btn.clicked.connect(lambda checked=False, s=sticker: self.on_sticker_clicked(s))
                    btn.delete_requested.connect(self.on_sticker_delete_requested)
                    grid.addWidget(btn, row, col)
                continue

            emoji = str(item.get("emoji") or "")
            if not emoji:
                continue
            is_fav = emoji in getattr(self, "favorite_emojis", set())
            btn = EmojiButton(emoji, is_favorite=is_fav)
            btn.clicked.connect(lambda checked=False, e=emoji: self.on_emoji_clicked(e))
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, e=emoji, b=btn: self.show_emoji_context_menu(e, b, pos)
            )
            grid.addWidget(btn, row, col)

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
            if was_visible:
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
            try:
                from src.config.settings import settings

                stickers_dir = Path(settings.data_dir) / "users" / str(self.user_id) / "stickers"
            except Exception:
                stickers_dir = Path(f"data/users/{self.user_id}/stickers")
            stickers_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"表情包目录: {stickers_dir}")

            # 生成唯一ID并复制文件
            sticker_id = str(uuid.uuid4())[:8]
            dest = stickers_dir / f"{sticker_id}{source.suffix}"

            logger.info(f"复制文件: {source} -> {dest}")
            shutil.copy2(source, dest)

            # 保存到数据库
            from src.auth.user_session import user_session

            data_manager = user_session.data_manager
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
                    "caption": None,
                }
            )

            # 刷新界面
            self.refresh_ui()

            # 切换到自定义表情包标签页
            for i in range(self.tab_widget.count()):
                if self.tab_widget.tabText(i) == "🖼️ 自定义":
                    self.tab_widget.setCurrentIndex(i)
                    break

            # v2.46.x: 后台调用视觉模型生成表情包说明标签（不阻塞 UI，不在聊天区展示过程）
            try:
                self._schedule_sticker_caption_generation(
                    sticker_id=sticker_id,
                    sticker_path=str(dest),
                    fallback_name=source.stem,
                )
            except Exception:
                pass

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

    def _schedule_sticker_caption_generation(
        self,
        *,
        sticker_id: str,
        sticker_path: str,
        fallback_name: str = "",
    ) -> None:
        """后台生成表情包说明标签（caption），写入数据库供 LLM 快速理解。"""
        if not self.user_id:
            return

        sticker_id = (sticker_id or "").strip()
        sticker_path = (sticker_path or "").strip()
        if not (sticker_id and sticker_path):
            return

        if sticker_id in self._sticker_caption_in_progress:
            return
        self._sticker_caption_in_progress.add(sticker_id)

        from PyQt6.QtCore import QThread, pyqtSignal
        from src.utils.logger import get_logger

        logger = get_logger(__name__)

        class StickerCaptionThread(QThread):
            caption_ready = pyqtSignal(str, str)  # sticker_id, caption
            caption_error = pyqtSignal(str, str)  # sticker_id, error

            def __init__(
                self, *, user_id: int, sticker_id: str, sticker_path: str, fallback_name: str
            ):
                super().__init__()
                self._user_id = user_id
                self._sticker_id = sticker_id
                self._sticker_path = sticker_path
                self._fallback_name = (fallback_name or "").strip()

            @staticmethod
            def _sanitize_caption(text: str) -> str:
                caption = (text or "").strip()
                if not caption:
                    return ""
                caption = caption.splitlines()[0].strip()
                caption = caption.strip(" \t\r\n\"'`“”‘’")
                caption = caption.strip()
                if len(caption) > 48:
                    caption = caption[:48].rstrip() + "…"
                return caption

            def run(self) -> None:
                try:
                    from src.llm.factory import get_vision_llm
                    from src.multimodal.vision import get_vision_processor_instance
                    from src.auth.user_session import user_session

                    vision_llm = get_vision_llm()
                    if vision_llm is None:
                        logger.info(
                            "VISION_LLM 未启用，跳过表情包 caption 生成: %s", self._sticker_id
                        )
                        return

                    processor = get_vision_processor_instance()
                    prompt = (
                        "这是一个聊天表情包/贴纸，用于表达情绪或动作。\n"
                        "请用中文生成一个简短标签（不超过12个字），描述它表达的情绪、动作或含义。\n"
                        "如果画面包含清晰可读的文字，优先用该文字或其含义。\n"
                        "只输出标签本身，不要解释，不要加引号，不要换行。"
                    )

                    # 表情包标签不需要超大分辨率：缩小输入可减少 base64 体积与视觉模型耗时
                    sticker_max_size = 512
                    try:
                        from src.config.settings import settings

                        cfg_max = int(getattr(settings, "max_image_size", 1024) or 1024)
                        sticker_max_size = min(cfg_max, 512)
                    except Exception:
                        sticker_max_size = 512

                    image_data = None
                    try:
                        image_data = processor.prepare_image_for_llm(
                            self._sticker_path, max_size=sticker_max_size
                        )
                    except Exception:
                        image_data = None

                    raw = processor.analyze_image(
                        self._sticker_path,
                        prompt=prompt,
                        llm=vision_llm,
                        image_data=image_data,
                    )
                    caption = self._sanitize_caption(str(raw))
                    if not caption and self._fallback_name:
                        caption = self._sanitize_caption(self._fallback_name)

                    if not caption:
                        logger.info("表情包 caption 为空，跳过写入: %s", self._sticker_id)
                        return

                    try:
                        user_session.data_manager.update_custom_sticker_caption(
                            self._user_id, self._sticker_id, caption
                        )
                    except Exception as update_exc:
                        logger.warning("写入表情包 caption 失败: %s", update_exc)

                    self.caption_ready.emit(self._sticker_id, caption)
                except Exception as e:
                    self.caption_error.emit(self._sticker_id, str(e))

        thread = StickerCaptionThread(
            user_id=int(self.user_id),
            sticker_id=sticker_id,
            sticker_path=sticker_path,
            fallback_name=fallback_name,
        )

        def _on_caption_ready(done_id: str, caption: str) -> None:
            logger.info("表情包 caption 已生成: %s -> %s", done_id, caption)
            try:
                for sticker in self.custom_stickers:
                    if sticker.get("id") == done_id:
                        sticker["caption"] = caption
                        break
            except Exception:
                pass

        def _on_caption_error(done_id: str, error: str) -> None:
            logger.warning("表情包 caption 生成失败: %s (%s)", done_id, error)

        thread.caption_ready.connect(_on_caption_ready)
        thread.caption_error.connect(_on_caption_error)

        def _cleanup() -> None:
            try:
                if thread in self._sticker_caption_threads:
                    self._sticker_caption_threads.remove(thread)
            finally:
                try:
                    self._sticker_caption_in_progress.discard(sticker_id)
                except Exception:
                    pass

        thread.finished.connect(_cleanup)

        self._sticker_caption_threads.append(thread)
        thread.start()

    def clear_all_stickers(self):
        """清空所有自定义表情包 - v2.29.1 新增"""
        from PyQt6.QtWidgets import QMessageBox
        from src.utils.logger import get_logger

        logger = get_logger(__name__)
        total = len(self.custom_stickers)

        reply = QMessageBox.question(
            self,
            "确认清空",
            f"确定要删除所有 {total} 个表情包吗？\n此操作不可恢复！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                from src.auth.user_session import user_session

                # 删除所有表情包
                failed_count = 0
                data_manager = user_session.data_manager
                for sticker in self.custom_stickers[:]:  # 使用副本遍历
                    try:
                        # 从数据库删除
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
                        f"成功删除 {max(0, total - failed_count)} 个表情包\n失败 {failed_count} 个",
                    )

            except Exception as e:
                logger.error(f"清空表情包失败: {e}", exc_info=True)
                QMessageBox.critical(self, "清空失败", f"清空表情包失败：{str(e)}")

    def _dispose_tabs(self) -> None:
        """删除 tab 页面，避免 QTabWidget.clear() 仅移除不释放导致的内存/动画泄漏。"""
        if not hasattr(self, "tab_widget") or self.tab_widget is None:
            return

        while self.tab_widget.count() > 0:
            page = self.tab_widget.widget(0)
            self.tab_widget.removeTab(0)
            if page is None:
                continue
            for btn in page.findChildren(CustomStickerButton):
                try:
                    btn.cleanup()
                except Exception:
                    pass
            page.deleteLater()

    def refresh_ui(self):
        """刷新界面 - v2.29.1 优化版"""
        # 清空标签页
        self._dispose_tabs()
        self._build_tabs()

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

        # 清理自定义表情包动画（避免 QMovie 常驻占用 CPU）
        for btn in self.findChildren(CustomStickerButton):
            try:
                btn.cleanup()
            except Exception:
                pass
