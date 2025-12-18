"""
浅色主题消息气泡组件 (v2.22.1 Material Design 3 标准规范版)

严格遵循 Google Material Design 3 官方规范（2025）
https://m3.material.io/

v2.22.1 修复内容：
- 🔧 修复自定义头像图片路径无法显示的问题：
  * 添加 _create_avatar_label() 辅助函数，支持 emoji 和图片路径
  * 检测图片路径并加载图片，缩放并裁剪为圆形
  * 图片加载失败时使用默认 emoji
  * 更新所有消息气泡类使用新的辅助函数
  * 确保用户和AI助手的自定义头像正确显示

v2.21.5 性能优化内容：
- ⚡ 优化流式消息气泡性能：
  * 使用 setUpdatesEnabled 减少重绘：追加文本时暂时禁用更新
  * 增加高度调整延迟：从100ms增加到200ms，减少重绘频率
  * 提升AI思考时的流畅度，减少卡顿

v2.21.4 优化内容：
- ⚡ 优化气泡显示逻辑，提升用户体验：
  * 修复文本气泡宽度问题：移除 setFixedWidth，使用自适应宽度
  * 修复对齐问题：用户消息内容右对齐，AI消息内容左对齐
  * 修复流式气泡宽度：移除最小宽度限制，自适应内容
  * 优化尺寸策略：使用 Preferred 策略，优先使用内容宽度
  * 短消息不再过宽，长消息自动换行，视觉效果更自然

v2.22.1 修复内容：
- 🔧 修复用户气泡宽度问题：
  * 回退到 QLabel，使用 QFontMetrics 精确计算宽度
  * 短文本：使用实际宽度 + padding (32px)，使用 setFixedWidth
  * 长文本：使用最大宽度 500px，自动换行
  * 最小宽度：100px，确保能容纳 4-5 个中文字符
  * 避免气泡过宽或竖排问题

v2.20.1 优化内容：
- 🔧 优化用户气泡换行逻辑：
  * 最小宽度：80px (减小，避免短消息过宽)
  * 最大宽度：600px (增加，给长消息更多空间)
  * 对齐方式：左对齐 + 顶部对齐
  * 改善中文换行效果

v2.19.0 优化内容：
- 📐 MD3 Elevation：Level 1 (消息气泡), Level 2 (图片)
  * Level 1: 0px 1px 3px 1px rgba(0,0,0,0.15)
  * Level 2: 0px 2px 6px 2px rgba(0,0,0,0.15)
- 🎨 MD3 颜色：Primary Container (用户), Surface Container High (AI)
- 🔘 圆角规范：20px (消息气泡), 16px (图片)
- ✨ 简洁设计：移除过度渐变，使用纯色背景
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QGraphicsOpacityEffect,
    QGraphicsDropShadowEffect, QSizePolicy
)
from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QTimer,
    QParallelAnimationGroup, QSequentialAnimationGroup, QPoint, pyqtProperty, QSize
)
from PyQt6.QtGui import (
    QFont,
    QColor,
    QPixmap,
    QMovie,
    QPainter,
    QPainterPath,
    QImageReader,
    QTextCursor,
    QTextOption,
)
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Optional
import time
import os

from .material_design_light import (
    MD3_LIGHT_COLORS, MD3_RADIUS, MD3_DURATION, get_light_elevation_shadow
)
from .material_design_enhanced import (
    MD3_ENHANCED_COLORS, MD3_ENHANCED_TYPOGRAPHY, MD3_ENHANCED_SPACING,
    MD3_ENHANCED_RADIUS, MD3_ENHANCED_DURATION, MD3_ENHANCED_EASING,
    get_elevation_shadow, get_typography_css
)
from .enhanced_animations import AnimationMixin
from .theme_manager import is_anime_theme

from src.utils.logger import get_logger


logger = get_logger(__name__)

# 预解析常用 spacing（避免每个气泡都做字符串 replace/int 转换）
_SPACING_LG = int(MD3_ENHANCED_SPACING["lg"].removesuffix("px"))
_SPACING_SM = int(MD3_ENHANCED_SPACING["sm"].removesuffix("px"))
_SPACING_1 = int(MD3_ENHANCED_SPACING["1"].removesuffix("px"))

# 圆角 token（保持主题可切换且避免散落 magic number）
_BUBBLE_RADIUS = MD3_ENHANCED_RADIUS.get("2xl", "20px")
_IMAGE_RADIUS = MD3_ENHANCED_RADIUS.get("xl", "16px")

# 流式气泡高度更新节流（过高会导致“气泡扩张跟不上文本”，过低会导致频繁布局重算）
STREAMING_HEIGHT_UPDATE_INTERVAL_MS = max(
    0, int(os.getenv("MINTCHAT_GUI_STREAM_BUBBLE_HEIGHT_MS", "33"))
)
STREAMING_BUBBLE_MAX_HEIGHT = max(0, int(os.getenv("MINTCHAT_GUI_STREAM_BUBBLE_MAX_HEIGHT", "0")))
BUBBLE_WRAP_DEBUG = os.getenv("MINTCHAT_GUI_BUBBLE_WRAP_DEBUG", "0").lower() not in {
    "0",
    "false",
    "no",
    "off",
}

if is_anime_theme():
    _MESSAGE_LABEL_QSS_USER = f"""
        QLabel {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 {MD3_ENHANCED_COLORS['primary_container']},
                stop:1 {MD3_ENHANCED_COLORS['secondary_container']}
            );
            color: {MD3_ENHANCED_COLORS['on_primary_container']};
            border-radius: {_BUBBLE_RADIUS};
            border: 1px solid {MD3_ENHANCED_COLORS['outline_variant']};
            padding: 12px 16px;
            {get_typography_css('body_large')}
            font-weight: 500;
            line-height: 1.5;
        }}
    """
else:
    _MESSAGE_LABEL_QSS_USER = f"""
        QLabel {{
            background: {MD3_ENHANCED_COLORS['primary_container']};
            color: {MD3_ENHANCED_COLORS['on_primary_container']};
            border-radius: {_BUBBLE_RADIUS};
            padding: 12px 16px;
            {get_typography_css('body_large')}
            font-weight: 500;
            line-height: 1.5;
        }}
    """

if is_anime_theme():
    _MESSAGE_LABEL_QSS_AI = f"""
        QLabel {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {MD3_ENHANCED_COLORS['surface_container_high']},
                stop:1 {MD3_ENHANCED_COLORS['surface_container_low']}
            );
            color: {MD3_ENHANCED_COLORS['on_surface']};
            border-radius: {_BUBBLE_RADIUS};
            padding: 12px 16px;
            {get_typography_css('body_large')}
            line-height: 1.5;
            border: 1px solid {MD3_ENHANCED_COLORS['outline_variant']};
        }}
    """
else:
    _MESSAGE_LABEL_QSS_AI = f"""
        QLabel {{
            background: {MD3_ENHANCED_COLORS['surface_container_high']};
            color: {MD3_ENHANCED_COLORS['on_surface']};
            border-radius: {_BUBBLE_RADIUS};
            padding: 12px 16px;
            {get_typography_css('body_large')}
            line-height: 1.5;
            border: 1px solid {MD3_ENHANCED_COLORS['outline_variant']};
        }}
    """

_TIME_LABEL_QSS = f"""
    QLabel {{
        color: {MD3_ENHANCED_COLORS['on_surface_variant']};
        {get_typography_css('label_small')}
        background: transparent;
    }}
"""

_IMAGE_LABEL_QSS = f"""
    QLabel {{
        background: {MD3_ENHANCED_COLORS['surface_bright']};
        border-radius: {_IMAGE_RADIUS};
        padding: 4px;
        border: 1px solid {MD3_ENHANCED_COLORS['outline_variant']};
    }}
"""

_IMAGE_LABEL_ERROR_QSS = f"""
    QLabel {{
        background: {MD3_ENHANCED_COLORS['error_container']};
        color: {MD3_ENHANCED_COLORS['on_error_container']};
        border-radius: {_IMAGE_RADIUS};
        padding: 20px 30px;
        {get_typography_css('body_large')}
    }}
"""


@lru_cache(maxsize=16)
def _get_avatar_qss(size: int, is_user: bool) -> str:
    """获取头像样式（缓存），减少每条消息重复格式化 QSS 的开销。"""
    border_radius = size // 2
    font_size = size // 2
    border_color = MD3_ENHANCED_COLORS["surface_bright"]
    if is_user:
        start = MD3_ENHANCED_COLORS["primary_40"]
        end = MD3_ENHANCED_COLORS["secondary_40"]
    else:
        start = MD3_ENHANCED_COLORS["tertiary_40"]
        end = MD3_ENHANCED_COLORS["primary_40"]
    return f"""
        QLabel {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 {start},
                stop:1 {end}
            );
            border-radius: {border_radius}px;
            font-size: {font_size}px;
            border: 2px solid {border_color};
        }}
    """


@lru_cache(maxsize=128)
def _load_scaled_pixmap(path: str, max_size: int, mtime_ns: int) -> QPixmap:
    """
    读取并按需缩放图片（带 LRU 缓存），减少频繁磁盘 IO 与重复缩放开销。
    """
    _ = mtime_ns  # 仅用于缓存键，文件变更时自动失效

    # v2.46.x: 优先用 QImageReader “按目标尺寸解码”，避免 QPixmap(path) 先解码整张大图再缩放导致卡顿/内存飙升
    try:
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        size = reader.size()
        if size.isValid() and (size.width() > max_size or size.height() > max_size):
            target = QSize(max_size, max_size)
            reader.setScaledSize(size.scaled(target, Qt.AspectRatioMode.KeepAspectRatio))
        image = reader.read()
        if not image.isNull():
            return QPixmap.fromImage(image)
    except Exception:
        pass

    # 兜底：沿用旧逻辑
    pixmap = QPixmap(path)
    if pixmap.isNull():
        return pixmap
    if pixmap.width() > max_size or pixmap.height() > max_size:
        pixmap = pixmap.scaled(
            max_size,
            max_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    return pixmap


@lru_cache(maxsize=128)
def _load_rounded_avatar_pixmap(path: str, size: int, mtime_ns: int) -> QPixmap:
    """加载并裁剪为圆形头像（带缓存）。"""
    _ = mtime_ns  # 仅用于缓存键，文件变更时自动失效

    pixmap = QPixmap(path)
    if pixmap.isNull():
        return QPixmap()

    scaled_pixmap = pixmap.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    if scaled_pixmap.width() > size or scaled_pixmap.height() > size:
        x = (scaled_pixmap.width() - size) // 2
        y = (scaled_pixmap.height() - size) // 2
        scaled_pixmap = scaled_pixmap.copy(x, y, size, size)

    rounded_pixmap = QPixmap(size, size)
    rounded_pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(rounded_pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    path_obj = QPainterPath()
    path_obj.addEllipse(0, 0, size, size)
    painter.setClipPath(path_obj)
    painter.drawPixmap(0, 0, scaled_pixmap)
    painter.end()

    return rounded_pixmap


def _create_avatar_label(avatar_text: str, size: int, is_user: bool) -> QLabel:
    """创建头像标签（支持 emoji 和图片路径）- v2.23.1 优化：真正的圆形头像

    Args:
        avatar_text: 头像文本（emoji 或图片路径）
        size: 头像大小（像素）
        is_user: 是否为用户头像

    Returns:
        QLabel: 配置好的头像标签
    """
    avatar_label = QLabel()
    avatar_label.setFixedSize(size, size)
    avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

    # 检查是否为图片路径
    avatar_path = Path(avatar_text) if avatar_text else None
    if avatar_path and avatar_path.is_file():
        try:
            mtime_ns = avatar_path.stat().st_mtime_ns
        except OSError:
            mtime_ns = 0

        rounded_pixmap = _load_rounded_avatar_pixmap(str(avatar_path), size, mtime_ns)
        if not rounded_pixmap.isNull():
            avatar_label.setPixmap(rounded_pixmap)
            avatar_label.setScaledContents(False)
        else:
            avatar_label.setText("👤" if is_user else "🐱")
    else:
        # emoji 或无效路径：直接显示文本
        avatar_label.setText(avatar_text if avatar_text else ("👤" if is_user else "🐱"))

    # 设置样式（缓存）
    avatar_label.setStyleSheet(_get_avatar_qss(size, is_user))

    return avatar_label


class LightMessageBubble(QWidget):
    """浅色主题消息气泡 - v2.22.0 增强版（支持自定义头像）"""

    def __init__(self, message: str, is_user: bool = True, parent=None, *, enable_shadow: bool = True):
        super().__init__(parent)
        self.message = message
        self.is_user = is_user
        self._enable_shadow = bool(enable_shadow)

        # 动画参数
        self._scale = 0.85
        self._opacity = 0.0

        self.setup_ui()
        self.setup_animations()

    def setup_ui(self):
        """设置 UI - v2.22.0 优化：添加头像显示"""
        # 主布局
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(
            _SPACING_LG,
            _SPACING_SM,
            _SPACING_LG,
            _SPACING_SM,
        )
        main_layout.setSpacing(8)

        # v2.22.0 获取自定义头像
        from src.auth.user_session import user_session
        if self.is_user:
            avatar_text = user_session.get_user_avatar() if user_session.is_logged_in() else "👤"
        else:
            avatar_text = user_session.get_ai_avatar() if user_session.is_logged_in() else "🐱"

        # v2.22.0 添加头像（AI消息在左侧，用户消息在右侧）
        if not self.is_user:
            # AI消息：头像在左侧
            avatar_label = _create_avatar_label(avatar_text, 40, False)
            main_layout.addWidget(avatar_label, alignment=Qt.AlignmentFlag.AlignTop)

        if self.is_user:
            main_layout.addStretch()

        # 气泡容器
        bubble_layout = QVBoxLayout()
        bubble_layout.setSpacing(_SPACING_1)

        # 消息文本 - 使用 QLabel，自适应宽度
        self.message_label = QLabel(self.message)
        self.message_label.setWordWrap(True)
        self.message_label.setTextFormat(Qt.TextFormat.PlainText)

        # 使用最大宽度限制，让气泡自适应内容；略收窄减少布局抖动
        max_width = 520
        self.message_label.setMaximumWidth(max_width)

        # 设置尺寸策略：优先使用内容宽度
        self.message_label.setSizePolicy(
            QSizePolicy.Policy.Preferred,  # 水平方向优先使用内容宽度
            QSizePolicy.Policy.Minimum     # 垂直方向最小化
        )

        # 允许文本选择
        self.message_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        # v2.48.5 优化：气泡内文本统一左对齐，气泡本身通过布局控制位置
        # 这样可以避免文本对齐不一致的问题
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        # 设置样式 - 使用 MD3 标准 Elevation 和 Surface Tints
        if self.is_user:
            # 用户消息 - MD3 Primary Container + Elevation Level 1
            self.message_label.setStyleSheet(_MESSAGE_LABEL_QSS_USER)

            # 添加 MD3 Elevation Level 1 阴影效果
            if self._enable_shadow:
                shadow = QGraphicsDropShadowEffect(self.message_label)
                shadow.setBlurRadius(3)
                shadow.setXOffset(0)
                shadow.setYOffset(1)
                shadow.setColor(QColor(0, 0, 0, 38))
                self.message_label.setGraphicsEffect(shadow)
        else:
            # AI 消息 - MD3 Surface Container High + Elevation Level 1
            self.message_label.setStyleSheet(_MESSAGE_LABEL_QSS_AI)

            # 添加 MD3 Elevation Level 1 阴影效果
            if self._enable_shadow:
                shadow = QGraphicsDropShadowEffect(self.message_label)
                shadow.setBlurRadius(3)
                shadow.setXOffset(0)
                shadow.setYOffset(1)
                shadow.setColor(QColor(0, 0, 0, 38))
                self.message_label.setGraphicsEffect(shadow)

        bubble_layout.addWidget(self.message_label)

        # 时间戳 - 优化排版
        time_str = datetime.now().strftime("%H:%M")
        self.time_label = QLabel(time_str)
        self.time_label.setStyleSheet(_TIME_LABEL_QSS)

        # v2.48.5 优化：时间戳根据消息类型对齐
        # 用户消息时间戳右对齐，AI消息时间戳左对齐
        if self.is_user:
            self.time_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        else:
            self.time_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        bubble_layout.addWidget(self.time_label)

        main_layout.addLayout(bubble_layout)

        # v2.22.0 用户消息：头像在右侧
        if self.is_user:
            avatar_label = _create_avatar_label(avatar_text, 40, True)
            main_layout.addWidget(avatar_label, alignment=Qt.AlignmentFlag.AlignTop)

        if not self.is_user:
            main_layout.addStretch()

    def setup_animations(self):
        """设置动画 - v2.17.0 优化版

        动画在 show_with_animation 中按需创建，避免预先创建占用内存
        """
        pass

    def disable_shadow(self) -> None:
        """关闭阴影效果（用于大量消息时降低渲染开销）。"""
        if not getattr(self, "_enable_shadow", True):
            return
        self._enable_shadow = False
        if hasattr(self, "message_label") and self.message_label:
            self.message_label.setGraphicsEffect(None)

    def show_with_animation(self):
        """显示时带 Material Design 3 增强动画效果 - v2.48.6 优化

        组合动画效果（符合 MD3 规范）：
        1. 淡入动画 (250ms) - 透明度从 0 到 1
        2. 滑入动画 (250ms) - 从侧边滑入 30px

        所有动画并行执行，创造流畅的视觉体验
        动画时长：250ms（MD3 标准中等复杂度动画）
        缓动函数：OutCubic（MD3 标准缓动）
        """
        # 创建透明度效果
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)

        # 1. Material Design 3 淡入动画 - 使用 OutCubic 缓动
        self.fade_in = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_in.setDuration(250)  # 250ms 快速响应
        self.fade_in.setStartValue(0.0)
        self.fade_in.setEndValue(1.0)
        self.fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)

        # 2. Material Design 3 滑入动画 - 使用 OutCubic 缓动
        self.slide_in = QPropertyAnimation(self, b"pos")
        self.slide_in.setDuration(250)  # 250ms 快速响应
        self.slide_in.setEasingCurve(QEasingCurve.Type.OutCubic)

        # 设置滑入方向 - 根据消息类型从不同方向滑入
        current_pos = self.pos()
        if self.is_user:
            # 用户消息从右侧滑入 30px
            start_pos = current_pos + QPoint(30, 0)
        else:
            # AI 消息从左侧滑入 30px
            start_pos = current_pos - QPoint(30, 0)

        self.slide_in.setStartValue(start_pos)
        self.slide_in.setEndValue(current_pos)

        # 4. 并行动画组 - 同时执行所有动画，创造流畅的组合效果
        self.animation_group = QParallelAnimationGroup()
        self.animation_group.addAnimation(self.fade_in)
        self.animation_group.addAnimation(self.slide_in)

        # 动画完成后清理资源，提升性能
        self.animation_group.finished.connect(self._on_animation_finished)
        self.animation_group.start()

    def _on_animation_finished(self):
        """动画完成后清理资源

        移除图形效果以减少 GPU 负担，提升渲染性能
        """
        # 移除透明度效果，减少 GPU 渲染负担，并释放动画对象避免累计占用
        try:
            self.setGraphicsEffect(None)
        except Exception:
            pass

        for attr in ("opacity_effect", "fade_in", "slide_in", "animation_group"):
            obj = getattr(self, attr, None)
            if obj is None:
                continue
            try:
                if hasattr(obj, "stop"):
                    obj.stop()
            except Exception:
                pass
            try:
                if hasattr(obj, "deleteLater"):
                    obj.deleteLater()
            except Exception:
                pass
            try:
                setattr(self, attr, None)
            except Exception:
                pass

    @pyqtProperty(float)
    def scale(self):
        return self._scale

    @scale.setter
    def scale(self, value):
        """
        设置缩放值

        v2.48.5 修复: 移除不支持的 CSS transform 属性
        PyQt6 的 QSS 不支持 CSS transform，改用 QTransform 实现缩放
        """
        self._scale = value
        # v2.48.5: 使用 QTransform 实现缩放（替代不支持的 CSS transform）
        from PyQt6.QtGui import QTransform
        transform = QTransform()
        transform.scale(value, value)
        # 注意：QWidget 不直接支持 setTransform，这里仅更新内部状态
        # 实际的缩放效果通过动画的透明度和位置变化来体现
        self.update()

    def cleanup(self):
        """清理资源 - v2.19.2 新增：停止动画，释放资源"""
        # 停止所有动画
        if hasattr(self, 'animation_group') and self.animation_group:
            self.animation_group.stop()
        if hasattr(self, 'fade_in') and self.fade_in:
            self.fade_in.stop()
        if hasattr(self, 'slide_in') and self.slide_in:
            self.slide_in.stop()

        # 移除图形效果
        self.setGraphicsEffect(None)


class LightStreamingMessageBubble(QWidget):
    """浅色主题流式消息气泡 - v2.17.0 全方位深度优化版

    用于显示 AI 助手的流式回复，支持实时文本追加

    特性：
    - 容器模式：使用 QWidget 容器包裹 QTextEdit，确保圆角正确显示
    - 批量更新：使用定时器批量调整高度，减少重绘次数
    - 性能优化：透明背景、最小化重绘、及时清理资源
    - 视觉效果：垂直渐变背景、柔和阴影、圆角边框
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scale = 0.85
        self._adjust_timer = None  # 高度调整定时器
        self._doc_size_connected = False
        self._pending_height: int | None = None
        self._height_dirty = False
        self._last_height_update_ts = 0.0
        self._shadow_applied = False
        self._last_wrap_width = 0
        self._wrap_retry_count = 0
        self.setup_ui()
        self.setup_animations()

    def setup_ui(self):
        """设置 UI - v2.22.0 优化：添加头像显示

        使用容器模式解决 QTextEdit 圆角不显示的问题：
        1. 创建 QWidget 容器，应用圆角、边框、渐变、阴影
        2. QPlainTextEdit 使用透明背景，让容器的样式显示出来
        3. 容器自动适应 QPlainTextEdit 的高度变化
        """
        # 主布局
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(
            _SPACING_LG,
            _SPACING_SM,
            _SPACING_LG,
            _SPACING_SM,
        )
        main_layout.setSpacing(8)

        # v2.22.0 添加AI头像（流式消息始终是AI消息）
        from src.auth.user_session import user_session
        ai_avatar = user_session.get_ai_avatar() if user_session.is_logged_in() else "🐱"

        avatar_label = _create_avatar_label(ai_avatar, 40, False)
        main_layout.addWidget(avatar_label, alignment=Qt.AlignmentFlag.AlignTop)

        # 气泡容器
        bubble_layout = QVBoxLayout()
        bubble_layout.setSpacing(_SPACING_1)

        # 创建圆角容器 Widget 来包裹 QPlainTextEdit，确保圆角正确显示
        # 使用 MD3 Surface Container High + Elevation Level 1
        self.bubble_container = QWidget()
        # v2.21.4 优化：只设置最大宽度，让容器自适应内容
        self.bubble_container.setMaximumWidth(550)

        # v2.21.4 优化：设置尺寸策略，优先使用内容宽度
        self.bubble_container.setSizePolicy(
            QSizePolicy.Policy.Preferred,  # 水平方向优先使用内容宽度
            QSizePolicy.Policy.Minimum     # 垂直方向最小化
        )

        self.bubble_container.setStyleSheet(f"""
            QWidget {{
                background: {MD3_ENHANCED_COLORS['surface_container_high']};
                border-radius: 20px;
                border: 1px solid {MD3_ENHANCED_COLORS['outline_variant']};
            }}
        """)

        # v2.49.0 性能优化：流式过程中频繁更新文本/高度，阴影会显著拖慢帧率；
        # 因此默认延后到 finish() 再一次性加阴影（保持视觉一致同时提升流式 FPS）。
        self.bubble_container.setGraphicsEffect(None)

        # 容器内部布局
        container_layout = QVBoxLayout(self.bubble_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # 消息文本（使用 QPlainTextEdit 提升流式追加性能）
        self.message_text = QPlainTextEdit()
        self.message_text.setReadOnly(True)
        # 约束宽度：在部分平台上 QPlainTextEdit 的 sizeHint 会倾向于“单行展开”，配合最大宽度可确保触发换行
        try:
            self.message_text.setMaximumWidth(self.bubble_container.maximumWidth())
        except Exception:
            pass
        try:
            self.message_text.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        except Exception:
            pass
        # 修复：确保按控件宽度自动换行，否则会出现文本被裁切、气泡无法随内容增高的问题
        try:
            self.message_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        except Exception:
            # 不同 Qt/PyQt 版本可能缺少相关 API，兜底为默认行为
            pass
        wrap_modes = []
        # 兼容中文/无空格文本：优先使用 WrapAnywhere，避免部分平台下按“词边界”不换行的问题
        for attr in ("WrapAnywhere", "WrapAtWordBoundaryOrAnywhere"):
            try:
                wrap_modes.append(getattr(QTextOption.WrapMode, attr))
            except Exception:
                continue
        for mode in wrap_modes:
            try:
                self.message_text.setWordWrapMode(mode)
                break
            except Exception:
                continue
        try:
            option = self.message_text.document().defaultTextOption()
            for mode in wrap_modes:
                try:
                    option.setWrapMode(mode)
                    self.message_text.document().setDefaultTextOption(option)
                    break
                except Exception:
                    continue
        except Exception:
            pass
        # 性能：禁用撤销栈/最小化视口更新，减少流式追加时的内部开销
        self.message_text.setUndoRedoEnabled(False)
        try:
            self.message_text.setViewportUpdateMode(
                QPlainTextEdit.ViewportUpdateMode.MinimalViewportUpdate
            )
        except Exception:
            pass
        # v2.48.8 修复：设置初始高度为 60px（合理的最小值）
        self.message_text.setMinimumHeight(60)
        self.message_text.setMaximumHeight(60)
        self.message_text.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.message_text.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.message_text.setFrameStyle(0)  # 移除边框
        # QPlainTextEdit 使用透明背景，让容器的背景显示出来
        self.message_text.setStyleSheet(f"""
            QPlainTextEdit {{
                background: transparent;
                color: {MD3_ENHANCED_COLORS['on_surface']};
                border: none;
                padding: 12px 16px;
                {get_typography_css('body_large')}
                line-height: 1.5;
            }}
        """)

        # v2.48.8 修复：设置占位符文本，确保文档高度正常
        # 使用零宽空格，不可见但能撑起高度
        self.message_text.setPlainText("\u200B")

        # v2.49.0 性能优化：用 documentSizeChanged 事件驱动高度更新（替代频繁动画/轮询）
        self._setup_document_size_tracking()

        container_layout.addWidget(self.message_text)
        bubble_layout.addWidget(self.bubble_container)

        # 兼容：部分平台/主题下 QPlainTextEdit 的 document 宽度不会自动更新，导致不换行；
        # 这里在事件循环空闲时根据 viewport 宽度显式设置 textWidth，确保换行与高度计算生效。
        QTimer.singleShot(0, self._ensure_text_wrap)

        # 时间戳
        time_str = datetime.now().strftime("%H:%M")
        self.time_label = QLabel(time_str)
        self.time_label.setStyleSheet(f"""
            QLabel {{
                color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                {get_typography_css('label_small')}
                background: transparent;
            }}
        """)
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        bubble_layout.addWidget(self.time_label)

        main_layout.addLayout(bubble_layout)
        main_layout.addStretch()

    def _ensure_text_wrap(self) -> None:
        """确保文档按视口宽度换行（解决文本不换行导致气泡不扩张的问题）。"""
        try:
            viewport = self.message_text.viewport() if hasattr(self, "message_text") else None
            width = int(viewport.width()) if viewport is not None else 0
        except Exception:
            width = 0

        # QSS: padding 12px 16px（左右共 32px），需要从视口宽度中扣除，否则仍可能出现右侧裁切
        wrap_width = max(0, width - 32)
        if wrap_width <= 0:
            # 某些平台 showEvent 触发时布局尚未完成，viewport 宽度可能为 0，这里做有限次重试
            if self._wrap_retry_count < 3:
                self._wrap_retry_count += 1
                QTimer.singleShot(0, self._ensure_text_wrap)
            return

        if wrap_width == self._last_wrap_width:
            return

        self._last_wrap_width = wrap_width
        self._wrap_retry_count = 0

        # 兜底：再次明确启用按控件宽度换行（避免某些环境下 wrapMode 未生效）
        try:
            self.message_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        except Exception:
            pass

        wrap_modes = []
        # 兼容中文/无空格文本：优先使用 WrapAnywhere，避免部分平台下按“词边界”不换行的问题
        for attr in ("WrapAnywhere", "WrapAtWordBoundaryOrAnywhere"):
            try:
                wrap_modes.append(getattr(QTextOption.WrapMode, attr))
            except Exception:
                continue
        for mode in wrap_modes:
            try:
                self.message_text.setWordWrapMode(mode)
                break
            except Exception:
                continue

        try:
            doc = self.message_text.document()
            if doc is not None:
                doc.setTextWidth(wrap_width)
                # 主动触发一次高度评估：换行宽度变化时 documentSizeChanged 可能不可靠（QPlainTextEdit 下常见）
                self._on_document_size_changed(None)
        except Exception:
            pass

        if BUBBLE_WRAP_DEBUG:
            try:
                logger.debug(
                    "StreamBubble wrap updated: viewport=%s, wrap_width=%s, lineWrapMode=%s",
                    width,
                    wrap_width,
                    getattr(self.message_text, "lineWrapMode", lambda: None)(),
                )
            except Exception:
                pass

    def showEvent(self, event):
        super().showEvent(event)
        self._ensure_text_wrap()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._ensure_text_wrap()

    def setup_animations(self):
        """设置动画 - v2.48.6 优化：添加入场动画

        流式消息气泡的入场动画：
        1. 淡入动画 (250ms) - 透明度从 0 到 1
        2. 缩放动画 (250ms) - 从 0.9 缩放到 1.0（更subtle）
        3. 滑入动画 (250ms) - 从左侧滑入 30px

        使用更快的动画时长（250ms），符合 MD3 规范
        """
        pass  # 动画在 show_with_animation 中按需创建

    def disable_shadow(self) -> None:
        """关闭阴影效果（用于大量消息时降低渲染开销）。"""
        if getattr(self, "_shadow_disabled", False):
            return
        self._shadow_disabled = True
        self._shadow_applied = False
        if hasattr(self, "bubble_container") and self.bubble_container:
            self.bubble_container.setGraphicsEffect(None)

    def _apply_shadow_if_needed(self) -> None:
        """在不影响流式性能的前提下补齐阴影效果。"""
        if getattr(self, "_shadow_disabled", False) or self._shadow_applied:
            return
        if not hasattr(self, "bubble_container") or self.bubble_container is None:
            return

        shadow = QGraphicsDropShadowEffect(self.bubble_container)
        shadow.setBlurRadius(3)  # MD3 Level 1
        shadow.setXOffset(0)
        shadow.setYOffset(1)  # MD3 Level 1
        shadow.setColor(QColor(0, 0, 0, 38))  # 0.15 * 255
        self.bubble_container.setGraphicsEffect(shadow)
        self._shadow_applied = True

    def show_with_animation(self):
        """显示时带 Material Design 3 入场动画 - v2.48.6 新增

        组合动画效果：
        1. 淡入动画 (250ms) - 透明度从 0 到 1
        2. 滑入动画 (250ms) - 从左侧滑入 30px

        所有动画并行执行，创造流畅的视觉体验
        """
        # 创建透明度效果
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)

        # 1. Material Design 3 淡入动画 - 使用 OutCubic 缓动
        self.fade_in = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_in.setDuration(250)  # 250ms 快速响应
        self.fade_in.setStartValue(0.0)
        self.fade_in.setEndValue(1.0)
        self.fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)

        # 2. Material Design 3 滑入动画 - 使用 OutCubic 缓动
        self.slide_in = QPropertyAnimation(self, b"pos")
        self.slide_in.setDuration(250)  # 250ms 快速响应
        self.slide_in.setEasingCurve(QEasingCurve.Type.OutCubic)

        # AI 消息从左侧滑入 30px
        current_pos = self.pos()
        start_pos = current_pos - QPoint(30, 0)
        self.slide_in.setStartValue(start_pos)
        self.slide_in.setEndValue(current_pos)

        # 4. 并行动画组 - 同时执行所有动画
        self.animation_group = QParallelAnimationGroup()
        self.animation_group.addAnimation(self.fade_in)
        self.animation_group.addAnimation(self.slide_in)

        # 动画完成后清理资源
        self.animation_group.finished.connect(self._on_animation_finished)
        self.animation_group.start()

    def _on_animation_finished(self):
        """动画完成后清理资源 - v2.48.6 新增

        移除图形效果以减少 GPU 负担，提升渲染性能
        """
        # 移除透明度效果，减少 GPU 渲染负担，并释放动画对象避免累计占用
        try:
            self.setGraphicsEffect(None)
        except Exception:
            pass

        for attr in ("opacity_effect", "fade_in", "slide_in", "animation_group"):
            obj = getattr(self, attr, None)
            if obj is None:
                continue
            try:
                if hasattr(obj, "stop"):
                    obj.stop()
            except Exception:
                pass
            try:
                if hasattr(obj, "deleteLater"):
                    obj.deleteLater()
            except Exception:
                pass
            try:
                setattr(self, attr, None)
            except Exception:
                pass

    @pyqtProperty(float)
    def scale(self):
        """缩放属性 - v2.25.0 修复：添加缺失的属性定义"""
        return self._scale

    @scale.setter
    def scale(self, value):
        """设置缩放 - v2.25.0 修复：添加缺失的属性定义"""
        self._scale = value
        # 应用缩放变换（虽然流式消息通常不使用缩放动画）
        self.update()

    def append_text(self, text: str):
        """追加文本 - v2.48.9 修复：优化高度自适应延迟

        使用批量更新策略减少重绘次数：
        1. 首次追加时清除占位符文本
        2. 使用 TextCursor 批量插入文本
        3. 使用定时器延迟高度调整（20ms，及时响应换行）
        4. 避免每次追加都触发重绘
        5. 使用 setUpdatesEnabled 减少中间状态重绘

        Args:
            text: 要追加的文本内容
        """
        # v2.48.8 修复：首次追加时清除占位符
        if not hasattr(self, '_first_append_done'):
            self._first_append_done = True
            self.message_text.clear()

        # 小片段（逐字流式）不值得频繁切换 updatesEnabled，反而会引入额外开销；仅对较大追加使用。
        disable_updates = len(text) >= 32
        if disable_updates:
            # v2.21.5 优化：暂时禁用更新，减少重绘（务必用 finally 保证恢复，避免偶发异常导致界面不再刷新）
            self.message_text.setUpdatesEnabled(False)
        try:
            # 确保文档按当前视口宽度换行（某些环境下仅在插入后才会更新布局）
            try:
                self._ensure_text_wrap()
            except Exception:
                pass
            # 双保险：若 wrap 配置被重置，重新应用
            try:
                if hasattr(self.message_text, "lineWrapMode"):
                    if (
                        self.message_text.lineWrapMode()
                        != QPlainTextEdit.LineWrapMode.WidgetWidth
                    ):
                        self.message_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
            except Exception:
                pass

            # 批量更新文本，减少重绘次数（避免 setTextCursor 影响用户选中/触发额外更新）
            cursor = self.message_text.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            try:
                cursor.beginEditBlock()
            except Exception:
                pass
            cursor.insertText(text)
            try:
                cursor.endEditBlock()
            except Exception:
                pass
        finally:
            # v2.21.5 优化：重新启用更新
            if disable_updates:
                self.message_text.setUpdatesEnabled(True)

        # 高度更新：不依赖 documentSizeChanged（在 QPlainTextEdit 下常见不可靠），统一用节流计时器调度
        self._on_document_size_changed(None)

    def _adjust_height(self):
        """根据内容自动调整高度 - 性能优化版

        调整策略：
        1. 计算文档实际高度
        2. 添加内边距（24px = 12px top + 12px bottom）
        3. 限制在最小高度（60px）和最大高度（600px）之间
        4. 同时设置 min 和 max 高度，让容器自动适应
        """
        # 获取文档实际高度（优先使用 documentLayout 的 documentSize，避免部分平台下 size() 不准确）
        try:
            self._ensure_text_wrap()
        except Exception:
            pass

        doc_height = self._get_visual_document_height()
        # 添加内边距（QPlainTextEdit 的 padding: 12px 16px）
        padding = 24  # 12px top + 12px bottom
        # 设置最小和最大高度限制
        min_height = 60
        max_height = self._get_max_stream_height()
        # 计算最终高度
        new_height = int(max(min_height, min(doc_height + padding, max_height)))
        # 设置 QPlainTextEdit 的高度
        self.message_text.setMinimumHeight(new_height)
        self.message_text.setMaximumHeight(new_height)
        try:
            self.bubble_container.updateGeometry()
            self.updateGeometry()
        except Exception:
            pass
        # 容器会自动调整大小

    def _get_visual_document_height(self) -> float:
        """获取 QPlainTextEdit 的可视文档高度（包含换行后的行数）。"""
        try:
            doc = self.message_text.document()
            if doc is None:
                return 0.0

            last_block = doc.lastBlock()
            if not last_block.isValid():
                return 0.0

            # 注意：QPlainTextEdit 的 QTextDocument.size()/documentSize() 在某些平台/版本下
            # 不会反映“自动换行”带来的高度变化；blockBounding* 才能拿到真实可视高度。
            geometry = self.message_text.blockBoundingGeometry(last_block)
            rect = self.message_text.blockBoundingRect(last_block)
            height = float(geometry.y() + rect.height())
            if height <= 0 or height > 100000:
                return 0.0

            # 兼容：部分平台 contentOffset 会带来额外偏移（通常很小），这里取正值补偿
            try:
                offset_y = float(self.message_text.contentOffset().y())
                if offset_y > 0:
                    height += offset_y
            except Exception:
                pass

            return height
        except Exception:
            return 0.0

    def _setup_document_size_tracking(self) -> None:
        """连接 documentSizeChanged，用更低开销的方式驱动高度更新。"""
        try:
            # 计时器总是可用：即便 documentSizeChanged 不触发，也能通过 append_text/_ensure_text_wrap 手动调度
            if not hasattr(self, "_height_update_timer"):
                self._height_update_timer = QTimer(self)
                self._height_update_timer.setSingleShot(True)
                self._height_update_timer.timeout.connect(self._apply_pending_height)

            doc = self.message_text.document()
            layout = doc.documentLayout() if doc is not None else None
            if layout is None or not hasattr(layout, "documentSizeChanged"):
                self._doc_size_connected = False
                return

            layout.documentSizeChanged.connect(self._on_document_size_changed)
            self._doc_size_connected = True
        except Exception:
            self._doc_size_connected = False

    def _on_document_size_changed(self, size) -> None:
        """文档尺寸变化事件：节流后批量应用高度，避免频繁触发布局重算。"""
        # QPlainTextEdit 下 documentLayout().documentSize() 往往只随 blockCount 改变，
        # 并不会反映“自动换行”导致的可视高度变化；
        # 因此这里只负责“标记脏 + 定时器节流”，实际高度计算放到 _apply_pending_height()。
        self._height_dirty = True

        timer = getattr(self, "_height_update_timer", None)
        if timer is None:
            return

        if timer.isActive():
            return

        now = time.monotonic()
        interval_ms = STREAMING_HEIGHT_UPDATE_INTERVAL_MS
        elapsed_ms = (now - self._last_height_update_ts) * 1000.0 if self._last_height_update_ts else 9999.0
        wait_ms = max(0, int(interval_ms - elapsed_ms))
        timer.start(wait_ms)

    def _apply_pending_height(self) -> None:
        """应用已计算的目标高度（不使用动画，避免持续掉帧）。"""
        self._last_height_update_ts = time.monotonic()
        if not getattr(self, "_height_dirty", False):
            return

        self._height_dirty = False

        try:
            self._ensure_text_wrap()
        except Exception:
            pass

        doc_height = self._get_visual_document_height()
        if doc_height <= 0 or doc_height > 10000:
            return

        padding = 24
        min_height = 60
        max_height = self._get_max_stream_height()
        new_height = int(max(min_height, min(doc_height + padding, max_height)))

        current_height = self.message_text.minimumHeight()
        if abs(new_height - current_height) < 12:
            return

        self.message_text.setMinimumHeight(new_height)
        self.message_text.setMaximumHeight(new_height)
        try:
            self.bubble_container.updateGeometry()
            self.updateGeometry()
        except Exception:
            pass
        # 高度变化会改变滚动区域的 maximum，这里异步触发一次“到达底部”，避免文本增长时视图不跟随
        try:
            window = self.window()
            if window is not None and hasattr(window, "_scroll_to_bottom"):
                QTimer.singleShot(0, window._scroll_to_bottom)
        except Exception:
            pass

    def _get_max_stream_height(self) -> int:
        """获取流式气泡最大高度（可配置，默认随视口动态变化）。"""
        if STREAMING_BUBBLE_MAX_HEIGHT > 0:
            return STREAMING_BUBBLE_MAX_HEIGHT

        # 默认：不超过视口高度的 70%，并限制在 [600, 900]，避免过大导致布局成本飙升
        try:
            window = self.window()
            scroll_area = getattr(window, "scroll_area", None) if window is not None else None
            viewport = scroll_area.viewport() if scroll_area is not None else None
            viewport_height = int(viewport.height()) if viewport is not None else 0
            if viewport_height > 0:
                return min(900, max(600, int(viewport_height * 0.7)))
        except Exception:
            pass

        return 600

    def finish(self):
        """完成流式输出 - 清理资源

        在流式输出完成后调用，执行最终的高度调整并清理定时器
        """
        # 最终调整高度到准确值
        self._adjust_height()
        # 流式结束后再补齐阴影，避免流式期间持续掉帧
        self._apply_shadow_if_needed()
        # 清理定时器，释放资源
        if hasattr(self, "_height_update_timer"):
            self._height_update_timer.stop()

    def cleanup(self):
        """清理资源 - v2.19.2 新增：停止定时器，释放资源"""
        # 停止定时器
        if hasattr(self, "_height_update_timer") and self._height_update_timer:
            self._height_update_timer.stop()

        # 移除图形效果
        self.setGraphicsEffect(None)
        if hasattr(self, "bubble_container") and self.bubble_container:
            self.bubble_container.setGraphicsEffect(None)


class LightTypingIndicator(QWidget):
    """浅色主题打字指示器 - v2.17.0 优化版

    显示 AI 正在输入的动画指示器

    特性：
    - 三点波浪动画：使用透明度动画模拟打字效果
    - 流畅缓动：InOutSine 缓动曲线，自然流畅
    - 延迟启动：三个点依次启动，形成波浪效果
    - 视觉统一：与消息气泡保持一致的样式
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.animations = []  # 存储动画对象，避免被垃圾回收
        self.setup_ui()
        self.start_animation()

    def setup_ui(self):
        """设置 UI - 优化视觉效果

        创建一个小气泡，内含三个点，样式与消息气泡保持一致
        """
        # 主布局
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(
            _SPACING_LG,
            _SPACING_SM,
            _SPACING_LG,
            _SPACING_SM,
        )

        # 气泡容器
        bubble = QWidget()
        bubble.setFixedSize(70, 44)
        bubble.setStyleSheet(f"""
            QWidget {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 {MD3_ENHANCED_COLORS['surface_bright']},
                    stop:1 {MD3_ENHANCED_COLORS['surface_container_high']}
                );
                border-radius: 18px;
                border: 2px solid {MD3_ENHANCED_COLORS['outline_variant']};
            }}
        """)

        # 添加柔和阴影
        shadow = QGraphicsDropShadowEffect(bubble)
        shadow.setBlurRadius(8)
        shadow.setXOffset(0)
        shadow.setYOffset(2)
        shadow.setColor(QColor(0, 0, 0, 20))
        bubble.setGraphicsEffect(shadow)

        # 三个点
        dots_layout = QHBoxLayout(bubble)
        dots_layout.setContentsMargins(18, 14, 18, 14)
        dots_layout.setSpacing(6)

        self.dots = []
        for i in range(3):
            dot = QLabel("●")
            dot.setStyleSheet(f"""
                QLabel {{
                    color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                    font-size: 14px;
                    background: transparent;
                }}
            """)
            dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            dots_layout.addWidget(dot)
            self.dots.append(dot)

            # 创建透明度效果
            opacity_effect = QGraphicsOpacityEffect(dot)
            dot.setGraphicsEffect(opacity_effect)

        main_layout.addWidget(bubble)
        main_layout.addStretch()

    def start_animation(self):
        """开始动画 - 优化流畅度

        创建三点波浪动画：
        1. 每个点使用透明度动画（0.2 到 1.0）
        2. 使用 InOutSine 缓动曲线，自然流畅
        3. 延迟启动（0ms, 150ms, 300ms），形成波浪效果
        4. 无限循环，直到停止
        """
        self.animations = []

        for i, dot in enumerate(self.dots):
            # 创建透明度动画
            animation = QPropertyAnimation(dot.graphicsEffect(), b"opacity")
            animation.setDuration(MD3_ENHANCED_DURATION["slow"])  # 500ms 一个周期
            animation.setStartValue(0.2)  # 最小透明度 20%
            animation.setEndValue(1.0)    # 最大透明度 100%
            animation.setEasingCurve(QEasingCurve.Type.InOutSine)  # 正弦缓动，流畅自然
            animation.setLoopCount(-1)  # 无限循环

            # 延迟启动，创建波浪效果（每个点延迟 150ms）
            QTimer.singleShot(i * 150, animation.start)
            self.animations.append(animation)  # 保存引用，避免被垃圾回收

    def stop_animation(self):
        """停止动画 - 清理资源

        停止所有点的动画，释放资源
        """
        for animation in self.animations:
            animation.stop()
        self.animations.clear()  # 清空动画列表

    def cleanup(self):
        """清理资源 - v2.19.2 新增：停止动画，释放资源"""
        self.stop_animation()


class LightImageMessageBubble(QWidget):
    """浅色主题图片消息气泡 - v2.19.0 升级版

    用于显示图片附件消息和自定义表情包

    特性：
    - 图片预览：自动缩放图片到合适尺寸
    - 动画支持：支持 GIF/WEBP 动画播放
    - 优雅动画：淡入 + 缩放动画
    - 错误处理：图片加载失败时显示错误提示
    - 视觉效果：圆角边框、柔和阴影
    """

    def __init__(
        self,
        image_path: str,
        is_user: bool = True,
        is_sticker: bool = False,
        parent=None,
        *,
        with_animation: bool = True,
        enable_shadow: bool = True,
        autoplay: bool = True,
        hover_play: bool = True,
    ):
        super().__init__(parent)
        self.image_path = image_path
        self.is_user = is_user
        self.is_sticker = is_sticker  # 是否为表情包
        self.movie = None  # 用于播放动画
        self._with_animation = bool(with_animation)
        self._enable_shadow = bool(enable_shadow)
        self._autoplay = bool(autoplay)
        self._hover_play = bool(hover_play)
        self._is_animated = False
        self._static_pixmap: Optional[QPixmap] = None
        self._max_size = 0
        self._animation_enabled = False

        # 动画参数
        self._scale = 0.85
        self._opacity = 0.0

        self.setup_ui()
        if self._with_animation:
            self.setup_animations()

    def setup_ui(self):
        """设置 UI - v2.22.0 优化：添加头像显示"""
        # 主布局
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(
            _SPACING_LG,
            _SPACING_SM,
            _SPACING_LG,
            _SPACING_SM,
        )
        main_layout.setSpacing(8)

        # v2.22.0 获取自定义头像
        from src.auth.user_session import user_session
        if self.is_user:
            avatar_text = user_session.get_user_avatar() if user_session.is_logged_in() else "👤"
        else:
            avatar_text = user_session.get_ai_avatar() if user_session.is_logged_in() else "🐱"

        # v2.22.0 添加头像（AI消息在左侧）
        if not self.is_user:
            avatar_label = _create_avatar_label(avatar_text, 40, False)
            main_layout.addWidget(avatar_label, alignment=Qt.AlignmentFlag.AlignTop)

        if self.is_user:
            main_layout.addStretch()

        # 气泡容器
        bubble_layout = QVBoxLayout()
        bubble_layout.setSpacing(_SPACING_1)

        # 图片标签
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setScaledContents(False)

        # 尝试加载图片
        try:
            path = Path(self.image_path)
            max_size = 200 if self.is_sticker else 400
            self._max_size = max_size

            # 检查是否为动画格式
            suffix = path.suffix.lower()
            self._is_animated = suffix in {".gif", ".webp"}
            try:
                mtime_ns = path.stat().st_mtime_ns
            except OSError:
                mtime_ns = 0

            pixmap = _load_scaled_pixmap(str(path), max_size, mtime_ns)
            if pixmap.isNull():
                raise ValueError("无法加载图片")

            self._static_pixmap = pixmap
            self.image_label.setPixmap(pixmap)
            self.image_label.setFixedSize(pixmap.size())

            if self._is_animated and self._autoplay:
                self.set_animation_enabled(True)

            # 设置样式 - MD3 圆角边框 + Elevation Level 2
            self.image_label.setStyleSheet(_IMAGE_LABEL_QSS)

            # 添加 MD3 Elevation Level 2 阴影效果（图片需要更明显的阴影）
            # MD3 Level 2: 0px 2px 6px 2px rgba(0,0,0,0.15)
            if self._enable_shadow:
                shadow = QGraphicsDropShadowEffect(self.image_label)
                shadow.setBlurRadius(6)  # MD3 Level 2
                shadow.setXOffset(0)
                shadow.setYOffset(2)  # MD3 Level 2
                shadow.setColor(QColor(0, 0, 0, 38))  # 0.15 * 255
                self.image_label.setGraphicsEffect(shadow)

        except Exception as e:
            # 图片加载失败，显示错误提示
            self.image_label.setText("❌ 图片加载失败")
            self.image_label.setStyleSheet(_IMAGE_LABEL_ERROR_QSS)
            logger.warning("图片加载失败: %s", e)

        bubble_layout.addWidget(self.image_label)

        # 时间戳
        time_str = datetime.now().strftime("%H:%M")
        self.time_label = QLabel(time_str)
        self.time_label.setStyleSheet(_TIME_LABEL_QSS)

        if self.is_user:
            self.time_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        else:
            self.time_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        bubble_layout.addWidget(self.time_label)

        main_layout.addLayout(bubble_layout)

        # v2.22.0 用户消息：头像在右侧
        if self.is_user:
            avatar_label = _create_avatar_label(avatar_text, 40, True)
            main_layout.addWidget(avatar_label, alignment=Qt.AlignmentFlag.AlignTop)

        if not self.is_user:
            main_layout.addStretch()

    def supports_animation(self) -> bool:
        return bool(self._is_animated)

    def wants_autoplay(self) -> bool:
        """该气泡是否配置为“自动播放”（用于聊天窗口的动图预算策略）。"""
        return bool(self._autoplay)

    def is_animation_enabled(self) -> bool:
        """当前是否处于播放状态（用于聊天窗口的动图预算策略）。"""
        return bool(self._animation_enabled)

    def set_animation_enabled(self, enabled: bool) -> None:
        """启用/禁用动图播放（用于长对话性能保护）。"""
        if not self._is_animated:
            return

        enabled = bool(enabled)
        if enabled and self._animation_enabled:
            # 确保运行中
            if self.movie is not None and self.movie.state() != QMovie.MovieState.Running:
                self.movie.start()
            return
        if not enabled and not self._animation_enabled:
            return

        if enabled:
            if self.movie is None:
                try:
                    self.movie = QMovie(str(Path(self.image_path)))
                    # 性能/内存：避免缓存所有帧（长对话/多动图更稳）
                    try:
                        self.movie.setCacheMode(QMovie.CacheMode.CacheNone)
                    except Exception:
                        pass
                    if self._max_size > 0:
                        self.movie.setScaledSize(QSize(self._max_size, self._max_size))
                except Exception:
                    self.movie = None
            if self.movie is None:
                return
            self.image_label.setMovie(self.movie)
            self.movie.start()
            self._animation_enabled = True
            return

        # disable
        self._animation_enabled = False
        if self.movie is not None:
            try:
                self.movie.stop()
            except Exception:
                pass
        if self._static_pixmap is not None and not self._static_pixmap.isNull():
            self.image_label.setPixmap(self._static_pixmap)
            self.image_label.setFixedSize(self._static_pixmap.size())

    def setup_animations(self):
        """设置动画 - 淡入（性能优先）"""
        # 透明度动画
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0.0)

        self.opacity_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.opacity_animation.setDuration(MD3_ENHANCED_DURATION["medium2"])
        self.opacity_animation.setStartValue(0.0)
        self.opacity_animation.setEndValue(1.0)
        self.opacity_animation.setEasingCurve(MD3_ENHANCED_EASING["emphasized_decelerate"])
        self.opacity_animation.finished.connect(self._on_animation_finished)

        # 启动动画（小延迟避免首次 show 期间的额外布局抖动）
        QTimer.singleShot(30, self.opacity_animation.start)

    def _on_animation_finished(self):
        """动画完成后清理资源（避免累计占用与无意义重绘）。"""
        try:
            self.setGraphicsEffect(None)
        except Exception:
            pass

        for attr in ("opacity_effect", "opacity_animation"):
            obj = getattr(self, attr, None)
            if obj is None:
                continue
            try:
                if hasattr(obj, "stop"):
                    obj.stop()
            except Exception:
                pass
            try:
                if hasattr(obj, "deleteLater"):
                    obj.deleteLater()
            except Exception:
                pass
            try:
                setattr(self, attr, None)
            except Exception:
                pass

    @pyqtProperty(float)
    def scale(self):
        return self._scale

    @scale.setter
    def scale(self, value):
        """
        设置缩放值

        v2.48.5 修复: 移除不支持的 CSS transform 属性
        """
        self._scale = value
        # v2.48.5: 移除不支持的 CSS transform 属性，改用 update() 触发重绘
        self.update()

    def disable_shadow(self) -> None:
        """关闭阴影效果（用于大量消息时降低渲染开销）。"""
        if not getattr(self, "_enable_shadow", True):
            return
        self._enable_shadow = False
        if hasattr(self, "image_label") and self.image_label:
            self.image_label.setGraphicsEffect(None)

    def cleanup(self):
        """清理资源 - v2.19.0 新增"""
        if self.movie:
            try:
                self.movie.stop()
            except Exception:
                pass
            try:
                self.movie.deleteLater()
            except Exception:
                pass
            self.movie = None
        self._animation_enabled = False

    def enterEvent(self, event):
        super().enterEvent(event)
        if self._hover_play and self._is_animated:
            self.set_animation_enabled(True)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if self._hover_play and self._is_animated and not self._autoplay:
            self.set_animation_enabled(False)

    def hideEvent(self, event):
        """隐藏事件 - 清理动画资源"""
        super().hideEvent(event)
        self.cleanup()
