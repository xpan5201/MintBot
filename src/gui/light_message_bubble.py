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
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QGraphicsOpacityEffect,
    QGraphicsDropShadowEffect, QSizePolicy
)
from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QTimer,
    QParallelAnimationGroup, QSequentialAnimationGroup, QPoint, pyqtProperty, QSize
)
from PyQt6.QtGui import QFont, QColor, QPixmap, QMovie
from datetime import datetime
from pathlib import Path

from .material_design_light import (
    MD3_LIGHT_COLORS, MD3_RADIUS, MD3_DURATION, get_light_elevation_shadow
)
from .material_design_enhanced import (
    MD3_ENHANCED_COLORS, MD3_ENHANCED_TYPOGRAPHY, MD3_ENHANCED_SPACING,
    MD3_ENHANCED_RADIUS, MD3_ENHANCED_DURATION, MD3_ENHANCED_EASING,
    get_elevation_shadow, get_typography_css
)
from .enhanced_animations import AnimationMixin


def _create_avatar_label(avatar_text: str, size: int, is_user: bool) -> QLabel:
    """创建头像标签（支持 emoji 和图片路径）- v2.23.1 优化：真正的圆形头像

    Args:
        avatar_text: 头像文本（emoji 或图片路径）
        size: 头像大小（像素）
        is_user: 是否为用户头像

    Returns:
        QLabel: 配置好的头像标签
    """
    from PyQt6.QtGui import QPainter, QPainterPath

    avatar_label = QLabel()
    avatar_label.setFixedSize(size, size)
    avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

    # 检查是否为图片路径
    if avatar_text and Path(avatar_text).exists() and Path(avatar_text).is_file():
        # 图片路径：加载图片
        pixmap = QPixmap(avatar_text)
        if not pixmap.isNull():
            # 缩放图片
            scaled_pixmap = pixmap.scaled(
                size, size,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            # 裁剪为正方形
            if scaled_pixmap.width() > size or scaled_pixmap.height() > size:
                x = (scaled_pixmap.width() - size) // 2
                y = (scaled_pixmap.height() - size) // 2
                scaled_pixmap = scaled_pixmap.copy(x, y, size, size)

            # v2.23.1 创建圆形遮罩
            rounded_pixmap = QPixmap(size, size)
            rounded_pixmap.fill(Qt.GlobalColor.transparent)

            painter = QPainter(rounded_pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

            # 创建圆形路径
            path = QPainterPath()
            path.addEllipse(0, 0, size, size)

            # 裁剪并绘制
            painter.setClipPath(path)
            painter.drawPixmap(0, 0, scaled_pixmap)
            painter.end()

            avatar_label.setPixmap(rounded_pixmap)
            avatar_label.setScaledContents(False)
        else:
            # 图片加载失败，使用默认 emoji
            avatar_label.setText("👤" if is_user else "🐱")
    else:
        # emoji 或无效路径：直接显示文本
        avatar_label.setText(avatar_text if avatar_text else ("👤" if is_user else "🐱"))

    # 设置样式
    if is_user:
        # 用户头像：主色调渐变
        avatar_label.setStyleSheet(f"""
            QLabel {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 {MD3_ENHANCED_COLORS['primary_40']},
                    stop:1 {MD3_ENHANCED_COLORS['secondary_40']}
                );
                border-radius: {size // 2}px;
                font-size: {size // 2}px;
                border: 2px solid {MD3_ENHANCED_COLORS['surface_bright']};
            }}
        """)
    else:
        # AI头像：第三色调渐变
        avatar_label.setStyleSheet(f"""
            QLabel {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 {MD3_ENHANCED_COLORS['tertiary_40']},
                    stop:1 {MD3_ENHANCED_COLORS['primary_40']}
                );
                border-radius: {size // 2}px;
                font-size: {size // 2}px;
                border: 2px solid {MD3_ENHANCED_COLORS['surface_bright']};
            }}
        """)

    return avatar_label


class LightMessageBubble(QWidget):
    """浅色主题消息气泡 - v2.22.0 增强版（支持自定义头像）"""

    def __init__(self, message: str, is_user: bool = True, parent=None):
        super().__init__(parent)
        self.message = message
        self.is_user = is_user

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
            int(MD3_ENHANCED_SPACING["lg"].replace("px", "")),
            int(MD3_ENHANCED_SPACING["sm"].replace("px", "")),
            int(MD3_ENHANCED_SPACING["lg"].replace("px", "")),
            int(MD3_ENHANCED_SPACING["sm"].replace("px", ""))
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
        bubble_layout.setSpacing(int(MD3_ENHANCED_SPACING["1"].replace("px", "")))

        # 消息文本 - 使用 QLabel，自适应宽度
        self.message_label = QLabel(self.message)
        self.message_label.setWordWrap(True)
        self.message_label.setTextFormat(Qt.TextFormat.PlainText)

        # 使用最大宽度限制，让气泡自适应内容；略收窄减少布局抖动
        max_width = 520
        self.message_label.setMaximumWidth(max_width)

        # 设置尺寸策略：优先使用内容宽度
        from PyQt6.QtWidgets import QSizePolicy
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
            self.message_label.setStyleSheet(f"""
                QLabel {{
                    background: {MD3_ENHANCED_COLORS['primary_container']};
                    color: {MD3_ENHANCED_COLORS['on_primary_container']};
                    border-radius: 20px;
                    padding: 12px 16px;
                    {get_typography_css('body_large')}
                    font-weight: 500;
                    line-height: 1.5;
                }}
            """)

            # 添加 MD3 Elevation Level 1 阴影效果
            shadow = QGraphicsDropShadowEffect(self.message_label)
            shadow.setBlurRadius(3)
            shadow.setXOffset(0)
            shadow.setYOffset(1)
            shadow.setColor(QColor(0, 0, 0, 38))
            self.message_label.setGraphicsEffect(shadow)
        else:
            # AI 消息 - MD3 Surface Container High + Elevation Level 1
            self.message_label.setStyleSheet(f"""
                QLabel {{
                    background: {MD3_ENHANCED_COLORS['surface_container_high']};
                    color: {MD3_ENHANCED_COLORS['on_surface']};
                    border-radius: 20px;
                    padding: 12px 16px;
                    {get_typography_css('body_large')}
                    line-height: 1.5;
                    border: 1px solid {MD3_ENHANCED_COLORS['outline_variant']};
                }}
            """)

            # 添加 MD3 Elevation Level 1 阴影效果
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
        self.time_label.setStyleSheet(f"""
            QLabel {{
                color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                {get_typography_css('label_small')}
                background: transparent;
            }}
        """)

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

    def show_with_animation(self):
        """显示时带 Material Design 3 增强动画效果 - v2.48.6 优化

        组合动画效果（符合 MD3 规范）：
        1. 淡入动画 (250ms) - 透明度从 0 到 1
        2. 缩放动画 (250ms) - 从 0.85 缩放到 1.0
        3. 滑入动画 (250ms) - 从侧边滑入 30px

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

        # 2. Material Design 3 缩放动画 - 使用 OutCubic 缓动
        self.scale_anim = QPropertyAnimation(self, b"scale")
        self.scale_anim.setDuration(250)  # 250ms 快速响应
        self.scale_anim.setStartValue(0.85)  # 从 85% 尺寸开始
        self.scale_anim.setEndValue(1.0)
        self.scale_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # 3. Material Design 3 滑入动画 - 使用 OutCubic 缓动
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
        self.animation_group.addAnimation(self.scale_anim)
        self.animation_group.addAnimation(self.slide_in)

        # 动画完成后清理资源，提升性能
        self.animation_group.finished.connect(self._on_animation_finished)
        self.animation_group.start()

    def _on_animation_finished(self):
        """动画完成后清理资源

        移除图形效果以减少 GPU 负担，提升渲染性能
        """
        # 移除透明度效果，减少 GPU 渲染负担
        self.setGraphicsEffect(None)

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
        if hasattr(self, 'scale_anim') and self.scale_anim:
            self.scale_anim.stop()
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
        self.setup_ui()
        self.setup_animations()

    def setup_ui(self):
        """设置 UI - v2.22.0 优化：添加头像显示

        使用容器模式解决 QTextEdit 圆角不显示的问题：
        1. 创建 QWidget 容器，应用圆角、边框、渐变、阴影
        2. QTextEdit 使用透明背景，让容器的样式显示出来
        3. 容器自动适应 QTextEdit 的高度变化
        """
        # 主布局
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(
            int(MD3_ENHANCED_SPACING["lg"].replace("px", "")),
            int(MD3_ENHANCED_SPACING["sm"].replace("px", "")),
            int(MD3_ENHANCED_SPACING["lg"].replace("px", "")),
            int(MD3_ENHANCED_SPACING["sm"].replace("px", ""))
        )
        main_layout.setSpacing(8)

        # v2.22.0 添加AI头像（流式消息始终是AI消息）
        from src.auth.user_session import user_session
        ai_avatar = user_session.get_ai_avatar() if user_session.is_logged_in() else "🐱"

        avatar_label = _create_avatar_label(ai_avatar, 40, False)
        main_layout.addWidget(avatar_label, alignment=Qt.AlignmentFlag.AlignTop)

        # 气泡容器
        bubble_layout = QVBoxLayout()
        bubble_layout.setSpacing(int(MD3_ENHANCED_SPACING["1"].replace("px", "")))

        # 创建圆角容器 Widget 来包裹 QTextEdit，确保圆角正确显示
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

        # 添加 MD3 Elevation Level 1 阴影到容器
        shadow = QGraphicsDropShadowEffect(self.bubble_container)
        shadow.setBlurRadius(3)  # MD3 Level 1
        shadow.setXOffset(0)
        shadow.setYOffset(1)  # MD3 Level 1
        shadow.setColor(QColor(0, 0, 0, 38))  # 0.15 * 255
        self.bubble_container.setGraphicsEffect(shadow)

        # 容器内部布局
        container_layout = QVBoxLayout(self.bubble_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # 消息文本（使用 QTextEdit 以支持流式追加）
        self.message_text = QTextEdit()
        self.message_text.setReadOnly(True)
        # v2.48.8 修复：设置初始高度为 60px（合理的最小值）
        self.message_text.setMinimumHeight(60)
        self.message_text.setMaximumHeight(60)
        self.message_text.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.message_text.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.message_text.setFrameStyle(0)  # 移除边框
        # QTextEdit 使用透明背景，让容器的背景显示出来
        self.message_text.setStyleSheet(f"""
            QTextEdit {{
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

        container_layout.addWidget(self.message_text)
        bubble_layout.addWidget(self.bubble_container)

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

    def setup_animations(self):
        """设置动画 - v2.48.6 优化：添加入场动画

        流式消息气泡的入场动画：
        1. 淡入动画 (250ms) - 透明度从 0 到 1
        2. 缩放动画 (250ms) - 从 0.9 缩放到 1.0（更subtle）
        3. 滑入动画 (250ms) - 从左侧滑入 30px

        使用更快的动画时长（250ms），符合 MD3 规范
        """
        pass  # 动画在 show_with_animation 中按需创建

    def show_with_animation(self):
        """显示时带 Material Design 3 入场动画 - v2.48.6 新增

        组合动画效果：
        1. 淡入动画 (250ms) - 透明度从 0 到 1
        2. 缩放动画 (250ms) - 从 0.9 缩放到 1.0
        3. 滑入动画 (250ms) - 从左侧滑入 30px

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

        # 2. Material Design 3 缩放动画 - 使用 OutCubic 缓动
        self.scale_anim = QPropertyAnimation(self, b"scale")
        self.scale_anim.setDuration(250)  # 250ms 快速响应
        self.scale_anim.setStartValue(0.9)  # 从 90% 尺寸开始（更subtle）
        self.scale_anim.setEndValue(1.0)
        self.scale_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # 3. Material Design 3 滑入动画 - 使用 OutCubic 缓动
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
        self.animation_group.addAnimation(self.scale_anim)
        self.animation_group.addAnimation(self.slide_in)

        # 动画完成后清理资源
        self.animation_group.finished.connect(self._on_animation_finished)
        self.animation_group.start()

    def _on_animation_finished(self):
        """动画完成后清理资源 - v2.48.6 新增

        移除图形效果以减少 GPU 负担，提升渲染性能
        """
        # 移除透明度效果，减少 GPU 渲染负担
        self.setGraphicsEffect(None)

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

        # v2.21.5 优化：暂时禁用更新，减少重绘
        self.message_text.setUpdatesEnabled(False)

        # 批量更新文本，减少重绘次数
        cursor = self.message_text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(text)
        self.message_text.setTextCursor(cursor)

        # v2.21.5 优化：重新启用更新
        self.message_text.setUpdatesEnabled(True)

        # v2.48.9 修复：减少延迟到 20ms，提升高度自适应响应速度
        # 20ms 是最佳平衡点：
        # - 足够批量更新多个字符（流式输出通常每次 1-5 个字符）
        # - 及时响应换行导致的高度变化
        # - 避免新内容挤压上一行
        if not hasattr(self, '_resize_timer'):
            self._resize_timer = QTimer()
            self._resize_timer.setSingleShot(True)
            self._resize_timer.timeout.connect(self._adjust_height_smooth)

        self._resize_timer.start(20)  # v2.48.9: 20ms 延迟，及时响应高度变化

    def _adjust_height(self):
        """根据内容自动调整高度 - 性能优化版

        调整策略：
        1. 计算文档实际高度
        2. 添加内边距（24px = 12px top + 12px bottom）
        3. 限制在最小高度（40px）和最大高度（600px）之间
        4. 同时设置 min 和 max 高度，让容器自动适应
        """
        # 获取文档实际高度
        doc_height = self.message_text.document().size().height()
        # 添加内边距（QTextEdit 的 padding: 12px 18px）
        padding = 24  # 12px top + 12px bottom
        # 设置最小和最大高度限制
        min_height = 40
        max_height = 600
        # 计算最终高度
        new_height = int(max(min_height, min(doc_height + padding, max_height)))
        # 设置 QTextEdit 的高度
        self.message_text.setMinimumHeight(new_height)
        self.message_text.setMaximumHeight(new_height)
        # 容器会自动调整大小

    def _adjust_height_smooth(self):
        """平滑调整高度 - v2.48.9 修复：优化动画时长和响应速度

        使用动画平滑调整气泡高度，避免突然跳动
        """
        # v2.48.8 修复：检查文档是否有效
        if not self.message_text.document():
            return

        # 获取文档实际高度
        doc_height = self.message_text.document().size().height()

        # v2.48.8 修复：检查文档高度是否有效（避免异常值）
        if doc_height <= 0 or doc_height > 10000:
            return

        padding = 24
        min_height = 60  # v2.48.8: 提高最小高度到 60px
        max_height = 600
        new_height = int(max(min_height, min(doc_height + padding, max_height)))

        # 获取当前高度
        current_height = self.message_text.minimumHeight()

        # v2.48.8 修复：如果是首次调整（从初始 60px 开始），直接设置，避免动画
        if current_height == 60 and not hasattr(self, '_height_adjusted_once'):
            self._height_adjusted_once = True
            self.message_text.setMinimumHeight(new_height)
            self.message_text.setMaximumHeight(new_height)
            return

        # v2.48.9 优化：降低直接设置的阈值到 5px，让更多情况使用动画
        # 但对于极小的变化（<5px）仍然直接设置，避免不必要的动画
        if abs(new_height - current_height) < 5:
            self.message_text.setMinimumHeight(new_height)
            self.message_text.setMaximumHeight(new_height)
            return

        # v2.48.9 修复：缩短动画时长到 80ms，提升响应速度
        # 80ms 是最佳平衡点：
        # - 足够平滑，不会有突兀感
        # - 足够快速，及时跟随流式输出
        # - 避免动画累积导致的延迟
        if not hasattr(self, '_height_anim'):
            self._height_anim = QPropertyAnimation(self.message_text, b"minimumHeight")
            self._height_anim.setDuration(80)  # v2.48.9: 80ms 快速平滑过渡
            self._height_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            # 动画完成后同步设置最大高度
            self._height_anim.finished.connect(
                lambda: self.message_text.setMaximumHeight(self.message_text.minimumHeight())
            )

        self._height_anim.setStartValue(current_height)
        self._height_anim.setEndValue(new_height)
        self._height_anim.start()

    def finish(self):
        """完成流式输出 - 清理资源

        在流式输出完成后调用，执行最终的高度调整并清理定时器
        """
        # 最终调整高度到准确值
        self._adjust_height()
        # 清理定时器，释放资源
        if hasattr(self, '_resize_timer'):
            self._resize_timer.stop()
            del self._resize_timer

    def cleanup(self):
        """清理资源 - v2.19.2 新增：停止定时器，释放资源"""
        # 停止定时器
        if hasattr(self, '_resize_timer') and self._resize_timer:
            self._resize_timer.stop()

        # 移除图形效果
        self.setGraphicsEffect(None)


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
            int(MD3_ENHANCED_SPACING["lg"].replace("px", "")),
            int(MD3_ENHANCED_SPACING["sm"].replace("px", "")),
            int(MD3_ENHANCED_SPACING["lg"].replace("px", "")),
            int(MD3_ENHANCED_SPACING["sm"].replace("px", ""))
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

    def __init__(self, image_path: str, is_user: bool = True, is_sticker: bool = False, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.is_user = is_user
        self.is_sticker = is_sticker  # 是否为表情包
        self.movie = None  # 用于播放动画

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
            int(MD3_ENHANCED_SPACING["lg"].replace("px", "")),
            int(MD3_ENHANCED_SPACING["sm"].replace("px", "")),
            int(MD3_ENHANCED_SPACING["lg"].replace("px", "")),
            int(MD3_ENHANCED_SPACING["sm"].replace("px", ""))
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
            avatar_label = QLabel(avatar_text)
            avatar_label.setFixedSize(40, 40)
            avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            avatar_label.setStyleSheet(f"""
                QLabel {{
                    background: qlineargradient(
                        x1:0, y1:0, x2:1, y2:1,
                        stop:0 {MD3_ENHANCED_COLORS['tertiary_40']},
                        stop:1 {MD3_ENHANCED_COLORS['primary_40']}
                    );
                    border-radius: 20px;
                    font-size: 20px;
                    border: 2px solid {MD3_ENHANCED_COLORS['surface_bright']};
                }}
            """)
            main_layout.addWidget(avatar_label, alignment=Qt.AlignmentFlag.AlignTop)

        if self.is_user:
            main_layout.addStretch()

        # 气泡容器
        bubble_layout = QVBoxLayout()
        bubble_layout.setSpacing(int(MD3_ENHANCED_SPACING["1"].replace("px", "")))

        # 图片标签
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setScaledContents(False)

        # 尝试加载图片
        try:
            path = Path(self.image_path)

            # 检查是否为动画格式
            if path.suffix.lower() in ['.gif', '.webp']:
                # 使用 QMovie 播放动画
                self.movie = QMovie(str(path))

                # 设置尺寸
                if self.is_sticker:
                    max_size = 200  # 表情包较小
                else:
                    max_size = 400  # 普通图片较大

                self.movie.setScaledSize(QSize(max_size, max_size))
                self.movie.frameChanged.connect(self.update_frame)
                self.image_label.setMovie(self.movie)
                self.movie.start()

                # 获取第一帧来设置大小
                first_frame = self.movie.currentPixmap()
                if not first_frame.isNull():
                    self.image_label.setFixedSize(first_frame.size())
                else:
                    self.image_label.setFixedSize(max_size, max_size)
            else:
                # 静态图片
                pixmap = QPixmap(str(path))
                if pixmap.isNull():
                    raise ValueError("无法加载图片")

                # 缩放图片到合适尺寸
                if self.is_sticker:
                    max_size = 200  # 表情包较小
                else:
                    max_size = 400  # 普通图片较大

                if pixmap.width() > max_size or pixmap.height() > max_size:
                    pixmap = pixmap.scaled(
                        max_size, max_size,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )

                self.image_label.setPixmap(pixmap)
                self.image_label.setFixedSize(pixmap.size())

            # 设置样式 - MD3 圆角边框 + Elevation Level 2
            self.image_label.setStyleSheet(f"""
                QLabel {{
                    background: {MD3_ENHANCED_COLORS['surface_bright']};
                    border-radius: 16px;
                    padding: 4px;
                    border: 1px solid {MD3_ENHANCED_COLORS['outline_variant']};
                }}
            """)

            # 添加 MD3 Elevation Level 2 阴影效果（图片需要更明显的阴影）
            # MD3 Level 2: 0px 2px 6px 2px rgba(0,0,0,0.15)
            shadow = QGraphicsDropShadowEffect(self.image_label)
            shadow.setBlurRadius(6)  # MD3 Level 2
            shadow.setXOffset(0)
            shadow.setYOffset(2)  # MD3 Level 2
            shadow.setColor(QColor(0, 0, 0, 38))  # 0.15 * 255
            self.image_label.setGraphicsEffect(shadow)

        except Exception as e:
            # 图片加载失败，显示错误提示
            self.image_label.setText("❌ 图片加载失败")
            self.image_label.setStyleSheet(f"""
                QLabel {{
                    background: {MD3_ENHANCED_COLORS['error_container']};
                    color: {MD3_ENHANCED_COLORS['on_error_container']};
                    border-radius: 16px;
                    padding: 20px 30px;
                    {get_typography_css('body_large')}
                }}
            """)
            print(f"图片加载失败: {e}")

        bubble_layout.addWidget(self.image_label)

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
        """设置动画 - 淡入 + 缩放"""
        # 透明度动画
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0.0)

        self.opacity_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.opacity_animation.setDuration(MD3_ENHANCED_DURATION["medium2"])
        self.opacity_animation.setStartValue(0.0)
        self.opacity_animation.setEndValue(1.0)
        self.opacity_animation.setEasingCurve(MD3_ENHANCED_EASING["emphasized_decelerate"])

        # 缩放动画（通过 scale 属性）
        self.scale_animation = QPropertyAnimation(self, b"scale")
        self.scale_animation.setDuration(MD3_ENHANCED_DURATION["medium4"])
        self.scale_animation.setStartValue(0.85)
        self.scale_animation.setEndValue(1.0)
        self.scale_animation.setEasingCurve(MD3_ENHANCED_EASING["emphasized_decelerate"])

        # 并行动画组
        self.animation_group = QParallelAnimationGroup()
        self.animation_group.addAnimation(self.opacity_animation)
        self.animation_group.addAnimation(self.scale_animation)

        # 动画完成后移除图形效果（性能优化）
        self.animation_group.finished.connect(lambda: self.setGraphicsEffect(None))

        # 启动动画
        QTimer.singleShot(50, self.animation_group.start)

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

    def update_frame(self):
        """更新动画帧 - v2.19.0 新增"""
        if self.movie:
            # QMovie 会自动更新 QLabel，这里不需要额外操作
            pass

    def cleanup(self):
        """清理资源 - v2.19.0 新增"""
        if self.movie:
            self.movie.stop()
            self.movie.deleteLater()
            self.movie = None

    def hideEvent(self, event):
        """隐藏事件 - 清理动画资源"""
        super().hideEvent(event)
        self.cleanup()
