"""浅色主题聊天窗口（Material Design 3、流式输出、自定义头像、性能优化、QQ风格界面）"""

from collections import deque
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QMainWindow,
    QDockWidget,
    QAbstractScrollArea,
    QScrollArea,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QStackedWidget,
    QGraphicsOpacityEffect,
    QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import (
    Qt,
    QThreadPool,
    pyqtSignal,
    pyqtProperty,
    QPropertyAnimation,
    QVariantAnimation,
    QEasingCurve,
    QTimer,
    QPoint,
    QRect,
    QRectF,
    QEvent,
)
from PyQt6.QtGui import QFont, QColor, QLinearGradient, QPixmap, QPainter, QPen, QBrush, QFontMetrics
from pathlib import Path
from functools import lru_cache
from typing import Any, Optional
import re
import time
import os
import weakref

STICKER_PATTERN = re.compile(r"\[STICKER:([^\]]+)\]")
IMAGE_PATTERN = re.compile(r"\[IMAGE:([^\]]+)\]")
_STICKER_EMOTION_KEYWORDS = {
    "开心": ["happy", "smile", "laugh", "joy", "开心", "笑", "哈哈", "嘻嘻"],
    "难过": ["sad", "cry", "tear", "难过", "哭", "伤心", "泪"],
    "生气": ["angry", "mad", "rage", "生气", "愤怒", "火"],
    "惊讶": ["surprise", "shock", "wow", "惊讶", "震惊", "哇"],
    "害羞": ["shy", "blush", "embarrass", "害羞", "脸红", "羞"],
    "可爱": ["cute", "kawaii", "adorable", "可爱", "萌", "卡哇伊"],
    "爱心": ["love", "heart", "kiss", "爱", "心", "亲"],
    "疑问": ["question", "confused", "wonder", "疑问", "困惑", "问"],
    "赞": ["thumbs", "good", "nice", "赞", "棒", "好"],
    "无语": ["speechless", "无语", "无奈", "汗"],
}


@lru_cache(maxsize=512)
def _guess_sticker_emotion(sticker_path: str) -> str:
    try:
        sticker_name = Path(sticker_path).stem.lower()
    except Exception:
        sticker_name = (sticker_path or "").lower()

    for emotion, keywords in _STICKER_EMOTION_KEYWORDS.items():
        if any(keyword in sticker_name for keyword in keywords):
            return emotion
    return "表情"
# 流式渲染：固定帧率小步追加（更像 ChatGPT 网页端，且避免一次性塞入大段文本导致“段落跳动”）
# 兼容：历史环境变量 MINTCHAT_GUI_STREAM_FLUSH_MS 仍可作为渲染间隔的兜底值。
STREAM_RENDER_INTERVAL_MS = max(
    0,
    int(
        os.getenv(
            "MINTCHAT_GUI_STREAM_RENDER_MS",
            os.getenv("MINTCHAT_GUI_STREAM_FLUSH_MS", "33"),
        )
    ),
)
STREAM_RENDER_TYPEWRITER = os.getenv("MINTCHAT_GUI_STREAM_TYPEWRITER", "1").lower() not in {
    "0",
    "false",
    "no",
    "off",
}
STREAM_RENDER_TYPEWRITER_MAX_BACKLOG = max(
    0, int(os.getenv("MINTCHAT_GUI_STREAM_TYPEWRITER_MAX_BACKLOG", "512"))
)
STREAM_RENDER_BASE_CHARS = max(1, int(os.getenv("MINTCHAT_GUI_STREAM_RENDER_CHARS", "16")))
STREAM_RENDER_MAX_CHARS = max(
    STREAM_RENDER_BASE_CHARS, int(os.getenv("MINTCHAT_GUI_STREAM_RENDER_MAX_CHARS", "256"))
)
CHATTHREAD_EMIT_INTERVAL_MS = max(0, int(os.getenv("MINTCHAT_GUI_STREAM_EMIT_MS", "33")))
CHATTHREAD_EMIT_THRESHOLD = max(256, int(os.getenv("MINTCHAT_GUI_STREAM_EMIT_THRESHOLD", "2048")))
STREAM_SCROLL_INTERVAL_MS = max(
    0, int(os.getenv("MINTCHAT_GUI_STREAM_SCROLL_MS", str(STREAM_RENDER_INTERVAL_MS)))
)
# 长对话性能保护：限制一次性渲染的消息气泡数量，避免 widget 数量过多导致滚动掉帧。
# 为 0 表示禁用（保持旧行为）。
MAX_RENDERED_MESSAGES = max(0, int(os.getenv("MINTCHAT_GUI_MAX_RENDERED_MESSAGES", "400")))
TRIM_RENDERED_MESSAGES_BATCH = max(1, int(os.getenv("MINTCHAT_GUI_TRIM_RENDERED_BATCH", "50")))
AUTO_SCROLL_BOTTOM_THRESHOLD_PX = max(0, int(os.getenv("MINTCHAT_GUI_AUTO_SCROLL_BOTTOM_PX", "80")))
SMOOTH_SCROLL_ENABLED = os.getenv("MINTCHAT_GUI_SMOOTH_SCROLL", "0").lower() not in {
    "0",
    "false",
    "no",
    "off",
}
FPS_OVERLAY_ENABLED = os.getenv("MINTCHAT_GUI_FPS_OVERLAY", "0").lower() not in {"0", "false", "no", "off"}
SHADOW_BUDGET = max(0, int(os.getenv("MINTCHAT_GUI_SHADOW_BUDGET", "24")))
ANIMATED_IMAGE_VISIBLE_ONLY = os.getenv("MINTCHAT_GUI_ANIMATED_IMAGE_VISIBLE_ONLY", "1").lower() not in {
    "0",
    "false",
    "no",
    "off",
}
# 0 表示不限制可见区域内的动图数量；仍可结合 ANIMATED_IMAGE_VISIBLE_ONLY 停止屏幕外动画。
ANIMATED_IMAGE_BUDGET = max(0, int(os.getenv("MINTCHAT_GUI_ANIMATED_IMAGE_BUDGET", "8")))
ANIMATED_IMAGE_DEBOUNCE_MS = max(0, int(os.getenv("MINTCHAT_GUI_ANIMATED_IMAGE_DEBOUNCE_MS", "80")))
GUI_ANIMATIONS_ENABLED = os.getenv(
    "MINTCHAT_GUI_ANIMATIONS",
    os.getenv("MINTCHAT_GUI_ENTRY_ANIMATIONS", "0"),  # 兼容旧变量名
).lower() not in {
    "0",
    "false",
    "no",
    "off",
}

from .light_frameless_window import LightFramelessWindow
from .light_sidebar import LightIconSidebar
from .light_message_bubble import (
    LightMessageBubble,
    LightStreamingMessageBubble,
    LightTypingIndicator,
    LightImageMessageBubble,
)
from .material_design_enhanced import (
    MD3_ENHANCED_COLORS,
    MD3_ENHANCED_RADIUS,
    get_typography_css,
)
from .qss_utils import qss_rgba
from .enhanced_rich_input import EnhancedInputWidget, ChatComposerIconButton
from .notifications import show_toast, Toast
from .contacts_panel import ContactsPanel
from src.utils.logger import get_logger
from src.auth.user_session import user_session
from src.auth.session_store import delete_session_token_file, write_session_token_file
from src.utils.gui_optimizer import throttle
from .chat_window_optimizer import ChatWindowOptimizer
from .workers.chat_history_loader import ChatHistoryLoaderThread, ChatHistoryLoadRequest
from .workers.agent_chat import AgentInitThread, ChatThread
from .workers.tts_synthesis import TTSSynthesisTask
from .workers.vision_analysis import VisionAnalyzeTask
from .workers.vision_batch import BatchImageRecognitionThread

logger = get_logger(__name__)


@lru_cache(maxsize=32)
def _load_rounded_header_avatar_pixmap(image_path: str, size: int, mtime_ns: int) -> QPixmap:
    """加载并裁剪为圆形头像（用于聊天窗口头部，带缓存）。"""
    _ = mtime_ns  # 仅用于缓存键，文件变更时自动失效

    pixmap = QPixmap(image_path)
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

    from PyQt6.QtGui import QPainter, QPainterPath

    rounded_pixmap = QPixmap(size, size)
    rounded_pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(rounded_pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    path = QPainterPath()
    path.addEllipse(0, 0, size, size)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, scaled_pixmap)
    painter.end()

    return rounded_pixmap


def _create_avatar_label_for_header(avatar_text: str, size: int) -> QLabel:
    """创建聊天窗口头部的头像标签（支持emoji和图片路径）"""
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

        rounded_pixmap = _load_rounded_header_avatar_pixmap(str(avatar_path), size, mtime_ns)
        if not rounded_pixmap.isNull():
            avatar_label.setPixmap(rounded_pixmap)
            avatar_label.setScaledContents(False)
        else:
            avatar_label.setText("🐱")
    else:
        # emoji 或无效路径：直接显示文本
        avatar_label.setText(avatar_text if avatar_text else "🐱")

    # 设置样式（AI头像）
    avatar_label.setStyleSheet(
        f"""
        QLabel {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 {MD3_ENHANCED_COLORS['primary_40']},
                stop:1 {MD3_ENHANCED_COLORS['secondary_40']}
            );
            border-radius: {size // 2}px;
            font-size: {size // 2}px;
            border: 3px solid {MD3_ENHANCED_COLORS['surface_bright']};
        }}
    """
    )

    return avatar_label


class CharacterStatusIsland(QWidget):
    """角色状态“原子岛”栏：悬停展开显示心情与好感度。"""

    COLLAPSED_HEIGHT = 56
    EXPANDED_HEIGHT = 140

    def __init__(
        self,
        avatar_text: str,
        name: str,
        *,
        max_width: int = 820,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._agent: object | None = None
        self._expanded = False
        self._collapsed_height = int(self.COLLAPSED_HEIGHT)
        self._expanded_height = int(self.EXPANDED_HEIGHT)
        self._radius_px = 28
        self._bg_color = QColor(255, 255, 255, 235)
        self._border_color = QColor(0, 0, 0, 30)
        self._details_target_height = 0

        self.setObjectName("characterStatusIsland")
        try:
            self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        except Exception:
            pass
        try:
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        except Exception:
            pass
        self.setMouseTracking(True)
        try:
            self.setFixedHeight(self._collapsed_height)
        except Exception:
            pass
        try:
            if int(max_width) > 0:
                self.setMaximumWidth(int(max_width))
        except Exception:
            pass

        root = QVBoxLayout(self)
        # Slightly larger horizontal padding so the content doesn't "stick" to the pill edges.
        root.setContentsMargins(16, 8, 16, 8)
        root.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(12)

        self.avatar_label = _create_avatar_label_for_header(avatar_text, 40)
        top_row.addWidget(self.avatar_label)

        texts = QVBoxLayout()
        texts.setContentsMargins(0, 0, 0, 0)
        texts.setSpacing(2)

        self.name_label = QLabel(str(name or ""))
        self.name_label.setStyleSheet(
            f"""
            QLabel {{
                color: {MD3_ENHANCED_COLORS['on_surface']};
                {get_typography_css('title_medium')}
                background: transparent;
                font-weight: 650;
            }}
            """
        )
        texts.addWidget(self.name_label)

        self.status_label = QLabel("● 离线")
        self.status_label.setStyleSheet(
            f"""
            QLabel {{
                color: {MD3_ENHANCED_COLORS['primary_60']};
                {get_typography_css('body_small')}
                background: transparent;
                font-weight: 600;
            }}
            """
        )
        texts.addWidget(self.status_label)

        top_row.addLayout(texts, 1)
        self.more_btn = ChatComposerIconButton(
            "more_vert",
            "更多",
            size=40,
            icon_size=20,
            variant=ChatComposerIconButton.VARIANT_GHOST,
            parent=self,
        )
        top_row.addWidget(self.more_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(top_row)

        self.details = QWidget()
        self.details.setVisible(False)
        details_layout = QVBoxLayout(self.details)
        # Extra inner padding so the bars/texts don't feel "too long" edge-to-edge.
        details_layout.setContentsMargins(14, 0, 14, 0)
        details_layout.setSpacing(10)

        self._metric_icon_font = QFont("Material Symbols Outlined")
        self._metric_icon_font.setPixelSize(18)

        mood_row = QHBoxLayout()
        mood_row.setContentsMargins(0, 0, 0, 0)
        mood_row.setSpacing(10)
        self.mood_icon = self._create_metric_icon("masks", tooltip="心情", accent="primary")
        mood_row.addWidget(self.mood_icon, 0, Qt.AlignmentFlag.AlignVCenter)
        self.mood_bar = QProgressBar()
        self._style_progress(self.mood_bar, MD3_ENHANCED_COLORS["gradient_primary"], height=18)
        self.mood_bar.setFormat("— 0%")
        mood_row.addWidget(self.mood_bar, 1)
        details_layout.addLayout(mood_row)

        divider = QWidget()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background: {qss_rgba(MD3_ENHANCED_COLORS['outline_variant'], 0.9)};")
        details_layout.addWidget(divider)
        self._details_divider = divider

        affection_row = QHBoxLayout()
        affection_row.setContentsMargins(0, 0, 0, 0)
        affection_row.setSpacing(10)
        self.affection_icon = self._create_metric_icon("favorite", tooltip="好感度", accent="secondary")
        affection_row.addWidget(self.affection_icon, 0, Qt.AlignmentFlag.AlignVCenter)
        self.affection_bar = QProgressBar()
        self._style_progress(self.affection_bar, MD3_ENHANCED_COLORS["gradient_secondary"], height=18)
        self.affection_bar.setFormat("— 0%")
        affection_row.addWidget(self.affection_bar, 1)
        details_layout.addLayout(affection_row)

        try:
            self._details_target_height = max(0, int(details_layout.sizeHint().height()))
            self._expanded_height = max(
                self._collapsed_height,
                self._collapsed_height + int(root.spacing()) + int(self._details_target_height) + 9,
            )
        except Exception:
            pass
        try:
            self.details.setMaximumHeight(0)
        except Exception:
            pass

        root.addWidget(self.details)

        effect = QGraphicsOpacityEffect(self.details)
        effect.setOpacity(0.0)
        self.details.setGraphicsEffect(effect)
        self._details_effect = effect

        self._height_anim = QPropertyAnimation(self, b"island_height", self)
        self._height_anim.setDuration(240)
        self._height_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

        self._details_height_anim = QPropertyAnimation(self.details, b"maximumHeight", self)
        self._details_height_anim.setDuration(220)
        self._details_height_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

        self._details_opacity_anim = QPropertyAnimation(effect, b"opacity", self)
        self._details_opacity_anim.setDuration(180)
        self._details_opacity_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._details_opacity_anim.finished.connect(self._maybe_hide_details)

        self._details_fade_timer = QTimer(self)
        self._details_fade_timer.setSingleShot(True)
        self._details_fade_timer.setInterval(80)
        self._details_fade_timer.timeout.connect(self._start_details_fade_in)

        self._collapse_timer = QTimer(self)
        self._collapse_timer.setSingleShot(True)
        self._collapse_timer.setInterval(140)
        self._collapse_timer.timeout.connect(lambda: self._set_expanded(False))

        self.setStyleSheet(
            """
            #characterStatusIsland {
                background: transparent;
                border: none;
            }
            """
        )
        self._apply_style(hovered=False)

    @pyqtProperty(int)
    def island_height(self) -> int:
        return int(self.height())

    @island_height.setter
    def island_height(self, value: int) -> None:
        try:
            height = int(value)
        except Exception:
            height = self._collapsed_height
        height = max(self._collapsed_height, min(self._expanded_height, height))
        try:
            self.setFixedHeight(height)
        except Exception:
            pass

    def _create_metric_icon(self, icon_name: str, *, tooltip: str, accent: str) -> QLabel:
        label = QLabel(str(icon_name or ""))
        label.setFixedSize(24, 24)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setToolTip(str(tooltip or ""))
        try:
            label.setFont(self._metric_icon_font)
        except Exception:
            pass

        try:
            accent_color = MD3_ENHANCED_COLORS.get(str(accent), MD3_ENHANCED_COLORS["primary"])
        except Exception:
            accent_color = MD3_ENHANCED_COLORS["primary"]
        label.setStyleSheet(
            f"""
            QLabel {{
                background: {qss_rgba(accent_color, 0.10)};
                border: 1px solid {qss_rgba(accent_color, 0.28)};
                border-radius: 12px;
                color: {accent_color};
            }}
            """
        )
        return label

    def _style_progress(self, bar: QProgressBar, chunk_bg: str, *, height: int) -> None:
        bar.setRange(0, 100)
        bar.setTextVisible(True)
        bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bar.setFixedHeight(int(height))
        radius = max(4, int(round(int(height) / 2)))
        bar.setStyleSheet(
            f"""
            QProgressBar {{
                background: {qss_rgba(MD3_ENHANCED_COLORS['outline_variant'], 0.75)};
                border: none;
                border-radius: {radius}px;
                text-align: center;
                color: {MD3_ENHANCED_COLORS['on_surface']};
                {get_typography_css('label_medium')}
                font-weight: 650;
            }}
            QProgressBar::chunk {{
                background: {chunk_bg};
                border-radius: {radius}px;
            }}
            """
        )

    _RGBA_RE = re.compile(
        r"rgba?\\(\\s*(\\d+)\\s*,\\s*(\\d+)\\s*,\\s*(\\d+)(?:\\s*,\\s*([0-9.]+))?\\s*\\)"
    )

    def _parse_qcolor(self, value: str) -> QColor:
        raw = str(value or "").strip()
        match = self._RGBA_RE.fullmatch(raw)
        if match:
            r = int(match.group(1))
            g = int(match.group(2))
            b = int(match.group(3))
            a = match.group(4)
            if a is None:
                alpha = 255
            else:
                try:
                    af = float(a)
                    alpha = int(round(af * 255.0)) if af <= 1.0 else int(round(af))
                except Exception:
                    alpha = 255
            return QColor(r, g, b, max(0, min(255, alpha)))

        color = QColor(raw)
        if color.isValid():
            return color
        return QColor(255, 255, 255, 235)

    def _apply_style(self, *, hovered: bool) -> None:
        radius = str(MD3_ENHANCED_RADIUS.get("extra_large", "28px"))
        try:
            self._radius_px = int(radius.replace("px", "").strip() or 0)
        except Exception:
            self._radius_px = 28

        if hovered:
            bg = MD3_ENHANCED_COLORS.get("frosted_glass_medium", "#FFFFFF")
            border_base = QColor(MD3_ENHANCED_COLORS.get("primary", "#000000"))
            border_base.setAlpha(int(0.85 * 255))
        else:
            bg = MD3_ENHANCED_COLORS.get("frosted_glass_light", "#FFFFFF")
            border_base = QColor(MD3_ENHANCED_COLORS.get("outline_variant", "#000000"))
            border_base.setAlpha(int(0.90 * 255))

        self._bg_color = self._parse_qcolor(bg)
        self._border_color = border_base
        try:
            self.update()
        except Exception:
            pass

    def paintEvent(self, _event):  # noqa: N802 - Qt API naming
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            rect = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
            radius = max(8, int(self._radius_px))

            # Subtle depth: a soft inner shadow near the bottom edge.
            try:
                shadow_rect = QRectF(rect)
                shadow_rect.translate(0.0, 1.6)
                shadow_rect.adjust(1.4, 1.4, -1.4, -1.4)
                shadow_color = QColor(0, 0, 0, 16 if self._expanded else 10)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(shadow_color))
                painter.drawRoundedRect(shadow_rect, max(6, radius - 2), max(6, radius - 2))
            except Exception:
                pass

            # Background gradient for a more "island" feel.
            try:
                base = QColor(self._bg_color)
                top = QColor(base)
                bottom = QColor(base)
                top = top.lighter(106 if self._expanded else 103)
                bottom = bottom.darker(102 if self._expanded else 100)
                grad = QLinearGradient(0.0, 0.0, 0.0, float(max(1, self.height())))
                grad.setColorAt(0.0, top)
                grad.setColorAt(1.0, bottom)
                painter.setBrush(QBrush(grad))
            except Exception:
                painter.setBrush(QBrush(self._bg_color))

            painter.setPen(QPen(self._border_color, 1.0))
            painter.drawRoundedRect(rect, radius, radius)

            # A tiny top highlight line (gives a glassy pill vibe).
            try:
                highlight = QColor(255, 255, 255, 120 if self._expanded else 90)
                painter.setPen(QPen(highlight, 1.0))
                hi_rect = QRectF(rect)
                hi_rect.adjust(1.6, 1.6, -1.6, -1.6)
                painter.drawRoundedRect(hi_rect, max(6, radius - 2), max(6, radius - 2))
            except Exception:
                pass
        except Exception:
            pass

    def set_agent(self, agent: object | None) -> None:
        self._agent = agent
        self._refresh_details()

    def _format_bar_text(self, bar: QProgressBar, left: str, percent: int) -> str:
        left = str(left or "—").strip()
        percent_text = f"{int(percent)}%"
        try:
            fm = QFontMetrics(bar.font())
            width = int(bar.width() or 0)
            if width <= 0:
                if len(left) > 16:
                    left = left[:15] + "…"
                return f"{left} {percent_text}"
            padding = 18
            available = max(0, width - padding)
            reserve = fm.horizontalAdvance(" " + percent_text)
            left_max = max(0, available - reserve)
            if left_max <= 0:
                return percent_text
            left_elided = fm.elidedText(left, Qt.TextElideMode.ElideRight, left_max)
            if left_elided:
                return f"{left_elided} {percent_text}"
            return percent_text
        except Exception:
            if len(left) > 16:
                left = left[:15] + "…"
            return f"{left} {percent_text}"

    def _refresh_details(self) -> None:
        mood_state = "—"
        mood_value = 0.0
        relationship_level = 0.5
        relationship_desc = ""

        agent = getattr(self, "_agent", None)
        if agent is not None:
            try:
                mood_system = getattr(agent, "mood_system", None)
                if mood_system is not None and bool(getattr(mood_system, "enabled", False)):
                    mood_state = str(mood_system.get_mood_state())
                    mood_value = float(getattr(mood_system, "mood_value", 0.0) or 0.0)
            except Exception:
                pass

            try:
                emotion_engine = getattr(agent, "emotion_engine", None)
                if emotion_engine is not None:
                    user_profile = getattr(emotion_engine, "user_profile", None)
                    relationship_level = float(getattr(user_profile, "relationship_level", relationship_level) or 0.0)
                    relationship_desc = str(emotion_engine.get_relationship_description() or "")
            except Exception:
                pass

        mood_pct = int(max(0, min(100, round((mood_value + 1.0) * 50.0))))
        affection_pct = int(max(0, min(100, round(relationship_level * 100.0))))

        try:
            self.mood_bar.setValue(mood_pct)
            left = str(mood_state) if mood_state else "—"
            self.mood_bar.setFormat(self._format_bar_text(self.mood_bar, left, mood_pct))
        except Exception:
            pass

        try:
            self.affection_bar.setValue(affection_pct)
            left = str(relationship_desc) if relationship_desc else "—"
            self.affection_bar.setFormat(self._format_bar_text(self.affection_bar, left, affection_pct))
        except Exception:
            pass

    def _start_details_fade_in(self) -> None:
        if not self._expanded:
            return

        try:
            if not self.details.isVisible():
                self.details.setVisible(True)
        except Exception:
            pass

        try:
            self._details_height_anim.stop()
            start_h = int(self.details.maximumHeight() or 0)
            if start_h <= 0:
                try:
                    self.details.setMaximumHeight(0)
                except Exception:
                    pass
                start_h = 0
            self._details_height_anim.setStartValue(start_h)
            target = int(getattr(self, "_details_target_height", 0) or 0)
            if target <= 0:
                target = max(0, int(self._expanded_height - self._collapsed_height))
            self._details_height_anim.setEndValue(target)
            self._details_height_anim.start()
        except Exception:
            pass
        try:
            self._details_opacity_anim.stop()
            self._details_opacity_anim.setDuration(160)
            self._details_opacity_anim.setStartValue(float(self._details_effect.opacity()))
            self._details_opacity_anim.setEndValue(1.0)
            self._details_opacity_anim.start()
        except Exception:
            pass

    def _set_expanded(self, expanded: bool) -> None:
        expanded = bool(expanded)
        if expanded == self._expanded:
            return
        self._expanded = expanded

        try:
            self._details_fade_timer.stop()
        except Exception:
            pass
        try:
            self._details_height_anim.stop()
        except Exception:
            pass
        try:
            self._details_opacity_anim.stop()
        except Exception:
            pass

        if expanded:
            self._refresh_details()
            self._apply_style(hovered=True)

            try:
                self._details_effect.setOpacity(0.0)
            except Exception:
                pass
            try:
                # Delay showing details until the island has grown a bit; avoids layout jitter at start.
                self.details.setMaximumHeight(0)
                self.details.setVisible(False)
            except Exception:
                pass

            try:
                self._height_anim.stop()
                self._height_anim.setStartValue(int(self.height() or self._collapsed_height))
                self._height_anim.setEndValue(self._expanded_height)
                self._height_anim.start()
            except Exception:
                try:
                    self.setFixedHeight(self._expanded_height)
                except Exception:
                    pass

            try:
                self._details_fade_timer.start()
            except Exception:
                self._start_details_fade_in()
            return

        # Collapse
        self._apply_style(hovered=False)

        # Shrink immediately while the details fade out; feels more "dynamic island".
        try:
            self._height_anim.stop()
            self._height_anim.setStartValue(int(self.height() or self._expanded_height))
            self._height_anim.setEndValue(self._collapsed_height)
            self._height_anim.start()
        except Exception:
            try:
                self.setFixedHeight(self._collapsed_height)
            except Exception:
                pass

        try:
            details_visible = bool(self.details.isVisible())
        except Exception:
            details_visible = True
        try:
            opacity = float(self._details_effect.opacity())
        except Exception:
            opacity = 1.0

        if not details_visible or opacity <= 0.01:
            self._maybe_hide_details()
            return

        try:
            # Fade out while shrinking; also collapse the bar region to avoid content jitter.
            try:
                self._details_height_anim.stop()
                start_h = int(self.details.maximumHeight() or 0)
                self._details_height_anim.setStartValue(start_h)
                self._details_height_anim.setEndValue(0)
                self._details_height_anim.start()
            except Exception:
                pass

            self._details_opacity_anim.setDuration(160)
            self._details_opacity_anim.setStartValue(opacity)
            self._details_opacity_anim.setEndValue(0.0)
            self._details_opacity_anim.start()
        except Exception:
            self._maybe_hide_details()

    def _maybe_hide_details(self) -> None:
        if not self._expanded:
            try:
                self.details.setVisible(False)
            except Exception:
                pass
            try:
                self._details_height_anim.stop()
            except Exception:
                pass
            try:
                self.details.setMaximumHeight(0)
            except Exception:
                pass

    def enterEvent(self, event):  # noqa: N802 - Qt API naming
        super().enterEvent(event)
        try:
            self._collapse_timer.stop()
        except Exception:
            pass
        self._set_expanded(True)

    def leaveEvent(self, event):  # noqa: N802 - Qt API naming
        super().leaveEvent(event)
        try:
            self._collapse_timer.start()
        except Exception:
            self._set_expanded(False)


class LightChatWindow(LightFramelessWindow):
    """浅色主题聊天窗口 - v2.15.0 优化版"""

    lipsync_playback_started = pyqtSignal(object, float, float)

    def __init__(self):
        super().__init__("MintChat - 猫娘女仆智能体")
        try:
            self.lipsync_playback_started.connect(self._on_lipsync_playback_started)
        except Exception:
            pass

        # Agent：惰性/后台初始化（避免启动阻塞 GUI 主线程）
        self.agent = None
        self._agent_user_id = None
        self._agent_username = None
        self._agent_initializing = True
        self._agent_init_failed = False
        self._agent_init_thread = None
        self._tool_filter_func = None

        try:
            self._agent_user_id = user_session.get_user_id()
            self._agent_username = user_session.get_username()
        except Exception:
            self._agent_user_id = None
            self._agent_username = None

        logger.info(
            "准备初始化 Agent: user=%s (ID=%s), logged_in=%s",
            self._agent_username,
            self._agent_user_id,
            user_session.is_logged_in(),
        )

        # 当前流式消息气泡
        self.current_streaming_bubble = None
        self._stream_model_done = False

        # 自动滚动锁：用户上滑查看历史时不强制拉回底部
        self._auto_scroll_enabled = True

        # Live2D: debounce lightweight reactions to avoid spamming motions during rapid UI updates.
        self._live2d_last_react_ms = 0.0

        # 表情选择器
        self.emoji_picker = None

        # 动图气泡索引（WeakSet 避免反向引用导致泄漏）：用于滚动时预算控制，避免 findChildren 全树扫描
        self._animated_image_bubbles: "weakref.WeakSet[LightImageMessageBubble]" = weakref.WeakSet()

        # 线程池 - 优化多线程性能
        # 使用独立线程池，避免修改 globalInstance() 的全局配置影响其他模块
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(4)  # 最多4个线程
        # 线程池任务引用：防止 QRunnable 被 GC 导致崩溃
        self._vision_tasks: list[object] = []

        # 当前聊天线程
        self.current_chat_thread = None
        # 仍在运行/等待回收的 ChatThread 引用，避免 QThread 被 GC 导致崩溃
        self._live_chat_threads: list[ChatThread] = []

        # 当前联系人
        self.current_contact = "小雪糕"  # 默认联系人

        # v2.30.14: 统一消息缓存格式 - 使用消息ID作为键
        # 格式: {contact_name: {msg_id: msg}}
        self._message_cache = {}  # 消息缓存（性能优化：避免重复查询数据库）
        self._loaded_message_count = {}  # 已加载消息数量
        self._total_message_count = {}  # 消息总数
        # 聊天历史后台加载：将 DB 查询移出 UI 线程，避免切换联系人/上滑加载卡顿
        self._history_load_seq = 0
        self._active_initial_history_request_id = 0
        self._active_more_history_request_id = 0
        self._active_initial_history_thread: Optional[ChatHistoryLoaderThread] = None
        self._active_more_history_thread: Optional[ChatHistoryLoaderThread] = None
        self._pending_history_load_state: dict[int, dict[str, Any]] = {}
        self._live_history_threads: list[ChatHistoryLoaderThread] = []
        self._history_loading_widget: Optional[QWidget] = None

        # v2.30.0: 图片分析相关
        self.current_image_analysis = None  # 当前图片分析结果
        self.current_image_path = None  # 当前图片路径
        self.image_recognition_thread = None  # 图片识别线程

        # v2.30.2: 待发送图片列表（支持多图片上传）
        self.pending_images = []  # 存储待发送的图片路径列表

        # v2.32.0: 性能优化器（延迟初始化，在setup_ui后）
        self.performance_optimizer = None

        # v2.48.13: TTS 相关变量（参考 MoeChat 逻辑，统一由多模态模块管理）
        self.tts_enabled = False  # TTS 是否启用
        self.tts_manager = None  # TTS 管理器
        self.audio_player = None  # 音频播放器
        self.tts_stream_processor = None  # 流式文本处理器
        self.tts_workers = []  # TTS 工作线程列表（防止被垃圾回收）
        self.tts_queue = []  # 待合成的句子队列（顺序播放）
        self.tts_busy = False  # 是否有 TTS 任务正在执行

        # 设置窗口大小
        self.resize(1200, 800)

        # 页面切换动画
        self.page_fade_animation = None

        # 设置内容
        self.setup_content()

        # 初始状态：Agent 未就绪前禁用发送，并显示“初始化中”
        self._update_agent_status_label()
        self._set_send_enabled(True)
        QTimer.singleShot(0, self._init_agent_async)

        # 窗口启动动画（默认关闭，避免影响启动与滚动帧率）
        if GUI_ANIMATIONS_ENABLED:
            self.setup_window_animation()

        # v2.48.12: 延迟初始化 TTS（避免阻塞 GUI 启动）
        QTimer.singleShot(1000, self._init_tts_system)

    def setup_content(self):
        """设置内容"""
        # 主布局
        main_layout = QHBoxLayout(self.content_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 左侧图标导航栏
        self.icon_sidebar = LightIconSidebar()
        self.icon_sidebar.chat_clicked.connect(self._on_chat_clicked)
        self.icon_sidebar.settings_clicked.connect(self._on_settings_clicked)
        self.icon_sidebar.contacts_clicked.connect(self._on_contacts_clicked)
        self.icon_sidebar.logout_clicked.connect(self._on_logout_clicked)
        main_layout.addWidget(self.icon_sidebar)

        # 联系人面板（初始折叠）
        self.contacts_panel = ContactsPanel()
        self.contacts_panel.contact_selected.connect(self._on_contact_selected)
        main_layout.addWidget(self.contacts_panel)

        # 使用 QStackedWidget 来切换聊天区域和设置面板
        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget)

        # 聊天区域
        chat_area = QWidget()
        chat_main_layout = QHBoxLayout(chat_area)
        chat_main_layout.setContentsMargins(0, 0, 0, 0)
        chat_main_layout.setSpacing(0)

        # 聊天内容区域
        chat_content = QWidget()
        chat_content.setObjectName("chatContentSurface")
        chat_content.setStyleSheet(
            f"""
            QWidget#chatContentSurface {{
                background: {MD3_ENHANCED_COLORS['surface']};
            }}
            """
        )
        chat_layout = QVBoxLayout(chat_content)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(0)

        chat_main_layout.addWidget(chat_content)

        # 聊天头部：使用消息区 overlay 的“原子岛”（避免展开推挤布局）

        # 消息区域 - MD3 Surface + 简洁设计
        # 添加圆角，与输入框上方圆角呼应
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        # 性能：减少滚动/内容变化时的无效重绘（不同 PyQt 版本可能不提供该 API，需兼容）
        try:
            if hasattr(self.scroll_area, "setViewportUpdateMode"):
                self.scroll_area.setViewportUpdateMode(
                    QAbstractScrollArea.ViewportUpdateMode.MinimalViewportUpdate
                )
        except Exception:
            pass
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet(
            f"""
            QScrollArea {{
                background: {MD3_ENHANCED_COLORS['surface']};
                border: none;
                border-top-left-radius: 16px;
                border-top-right-radius: 16px;
                border-bottom-left-radius: 0px;
                border-bottom-right-radius: 0px;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 8px;
                margin: 4px 2px;
            }}
            QScrollBar::handle:vertical {{
                background: {MD3_ENHANCED_COLORS['outline_variant']};
                border-radius: 4px;
                min-height: 40px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {MD3_ENHANCED_COLORS['outline']};
            }}
            QScrollBar::handle:vertical:pressed {{
                background: {MD3_ENHANCED_COLORS['primary']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """
        )

        # 消息容器（居中列：更像 ChatGPT 的阅读宽度）
        self.messages_widget = QWidget()
        try:
            self.messages_widget.setObjectName("messagesColumn")
            self._messages_column_max_width = 820
            self.messages_widget.setMaximumWidth(int(self._messages_column_max_width))
        except Exception:
            pass

        self.messages_layout = QVBoxLayout(self.messages_widget)
        # 顶部预留空间给“原子岛”悬浮层（不占布局高度）
        self.messages_layout.setContentsMargins(0, CharacterStatusIsland.COLLAPSED_HEIGHT + 20, 0, 16)
        self.messages_layout.setSpacing(8)
        self.messages_layout.addStretch()

        self.messages_outer_widget = QWidget()
        try:
            self.messages_outer_widget.setObjectName("messagesOuter")
        except Exception:
            pass
        outer_layout = QHBoxLayout(self.messages_outer_widget)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        outer_layout.addStretch(1)
        outer_layout.addWidget(self.messages_widget, 0)
        outer_layout.addStretch(1)

        self.scroll_area.setWidget(self.messages_outer_widget)

        # 原子岛：固定在消息显示框（viewport）内，展开不再推挤下方消息区域
        ai_avatar = user_session.get_ai_avatar() if user_session.is_logged_in() else "🐱"
        self.character_island = CharacterStatusIsland(
            ai_avatar,
            "小雪糕",
            max_width=420,
            parent=self.scroll_area.viewport(),
        )
        try:
            self.character_island.set_agent(getattr(self, "agent", None))
        except Exception:
            pass

        self.avatar_label = self.character_island.avatar_label
        self.name_label = self.character_island.name_label
        self.status_label = self.character_island.status_label

        # 更多菜单（放入“原子岛”右侧，避免悬停收起影响点击）
        self.more_btn = self.character_island.more_btn
        self.more_btn.clicked.connect(self._show_header_menu)

        # 轻量在线状态脉冲（绑定 status_label）
        self._setup_avatar_pulse_animation()

        # 可选：FPS 监控（用于定位卡顿/验证优化效果）
        if FPS_OVERLAY_ENABLED:
            self._fps_label = QLabel("FPS --", parent=self.scroll_area.viewport())
            self._fps_label.setStyleSheet(
                f"""
                QLabel {{
                    color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                    background: transparent;
                    font-size: 12px;
                    font-weight: 600;
                }}
            """
            )
            self._setup_fps_overlay()

        # overlay 定位（窗口 resize 时保持居中）
        self._overlay_viewport = self.scroll_area.viewport()
        try:
            self._overlay_viewport.installEventFilter(self)
        except Exception:
            pass
        QTimer.singleShot(0, self._position_message_overlays)
        QTimer.singleShot(0, self._update_messages_column_width)

        # v2.30.12: 监听滚动事件，实现滚动到顶部自动加载更多
        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar.valueChanged.connect(self._on_scroll_changed)
        # 内容高度变化时（尤其是流式气泡逐步扩张）用 rangeChanged 驱动一次“跟随到底部”调度，
        # 比在每个 chunk 都主动滚动更稳定且更省资源。
        scrollbar.rangeChanged.connect(self._on_scroll_range_changed)
        self._is_loading_more = False  # 防止重复加载

        # Soft edge blur while scrolling: makes bubbles fade/blur at viewport boundaries.
        self._edge_blur_overlay = None
        try:
            from .scroll_edge_blur_overlay import ScrollEdgeBlurOverlay

            self._edge_blur_overlay = ScrollEdgeBlurOverlay(
                scroll_area=self.scroll_area, parent=self.scroll_area.viewport()
            )
            try:
                self._edge_blur_overlay.setGeometry(self.scroll_area.viewport().rect())
            except Exception:
                pass
            self._edge_blur_overlay.show()
        except Exception:
            self._edge_blur_overlay = None

        # 输入区域 - ChatGPT Web 风格输入卡片（按钮与预览内聚到 EnhancedInputWidget）
        input_area = QWidget()
        input_area.setStyleSheet("background: transparent;")
        try:
            input_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        except Exception:
            pass

        input_layout = QHBoxLayout(input_area)
        input_layout.setContentsMargins(14, 12, 14, 16)
        input_layout.setSpacing(0)

        # 保留 input_area 引用（用于后续布局/状态控制）
        self.input_area = input_area

        self.enhanced_input = EnhancedInputWidget()
        try:
            self.enhanced_input.setMaximumWidth(int(getattr(self, "_messages_column_max_width", 820)))
        except Exception:
            pass
        self.enhanced_input.send_requested.connect(self._on_enhanced_send)
        try:
            # 输入内容变化时，刷新发送按钮可用性（需要同时满足：有内容 + Agent 就绪）
            self.enhanced_input.content_changed.connect(lambda: self._set_send_enabled(True))
        except Exception:
            pass
        try:
            self.enhanced_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        except Exception:
            pass
        input_layout.addWidget(self.enhanced_input, 1, Qt.AlignmentFlag.AlignHCenter)

        # 向后兼容引用
        self.input_text = self.enhanced_input.input_text

        # 复用增强输入框内部按钮（统一由 ChatWindow 控制 enable/disable）
        self.send_btn = self.enhanced_input.send_btn
        self.composer_plus_btn = self.enhanced_input.plus_btn
        self.composer_mic_btn = self.enhanced_input.mic_btn

        try:
            self.composer_plus_btn.clicked.connect(self._show_composer_tools_menu)
        except Exception:
            pass
        try:
            self.composer_mic_btn.clicked.connect(self._on_composer_mic_clicked)
        except Exception:
            pass

        # Center column: messages (top) + input (bottom) share the same parent,
        # and sit between sidebar and Live2D.
        center_column = QWidget()
        center_column.setObjectName("chatCenterColumn")
        center_column.setStyleSheet("background: transparent;")
        center_layout = QVBoxLayout(center_column)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        center_layout.addWidget(self.scroll_area, 1)
        center_layout.addWidget(input_area, 0)

        # Dock-hosted layout: center column (left) + Live2D (right).
        self.live2d_panel = None
        try:
            dock_host = QMainWindow(chat_content)
            # IMPORTANT: QMainWindow tends to keep `Qt.Window` flags even when parented in PyQt.
            # Force it to behave like a normal child widget so it can be managed by layouts.
            dock_host.setWindowFlags(Qt.WindowType.Widget)
            dock_host.setObjectName("messagesDockHost")
            dock_host.setDockNestingEnabled(False)
            dock_host.setStyleSheet(
                """
                QMainWindow#messagesDockHost { background: transparent; }
                QDockWidget { background: transparent; border: none; }
                QMainWindow::separator {
                    background: transparent;
                    width: 18px;
                }
                QMainWindow::separator:hover {
                    background: rgba(255, 105, 180, 0.10);
                }
                """
            )
            dock_host.setCentralWidget(center_column)

            # Live2D panel is optional, but if initialization fails we still show a placeholder
            # (instead of silently hiding it) so users can see the actionable error.
            try:
                try:
                    project_root = Path(__file__).resolve().parents[2]
                except Exception:
                    project_root = Path.cwd()

                # Use the original model3.json; Live2D widget will generate an ASCII-only
                # cache wrapper if the model folder contains non-ASCII expressions/motions.
                raw_model = project_root / "live2d" / "Blue_cat" / "Blue cat.model3.json"
                model_path = raw_model if raw_model.exists() else None
                if model_path is None:
                    try:
                        candidates = list((project_root / "live2d").rglob("*.model3.json"))
                        model_path = candidates[0] if candidates else None
                    except Exception:
                        model_path = None

                logger.info("Initializing Live2D panel (model=%s)", model_path)

                try:
                    from .live2d_panel import Live2DPanel

                    self.live2d_panel = Live2DPanel(model_path=model_path)
                except Exception as exc:
                    logger.error("Live2D panel init failed: %s", exc, exc_info=True)
                    fallback = QWidget()
                    fallback.setObjectName("live2dFallbackPanel")
                    try:
                        # Match Live2DPanel sizing so the dock never collapses to "nothing".
                        fallback.setMinimumWidth(320)
                        fallback.setMaximumWidth(560)
                    except Exception:
                        pass
                    fallback.setStyleSheet(
                        f"""
                        QWidget#live2dFallbackPanel {{
                            background: {MD3_ENHANCED_COLORS.get('surface_container_low', '#FFF7FB')};
                            border: 1px solid {MD3_ENHANCED_COLORS['outline_variant']};
                            border-radius: {MD3_ENHANCED_RADIUS['extra_large']};
                        }}
                        """
                    )
                    fb_layout = QVBoxLayout(fallback)
                    fb_layout.setContentsMargins(14, 14, 14, 14)
                    fb_layout.setSpacing(10)
                    title = QLabel("Live2D")
                    title.setStyleSheet(
                        f"""
                        QLabel {{
                            color: {MD3_ENHANCED_COLORS['on_surface']};
                            {get_typography_css('title_medium')}
                            font-weight: 760;
                            background: transparent;
                        }}
                        """
                    )
                    msg = QLabel(f"Live2D 初始化失败，请查看日志。\n\n{type(exc).__name__}: {exc}")
                    msg.setWordWrap(True)
                    msg.setStyleSheet(
                        f"""
                        QLabel {{
                            color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                            {get_typography_css('body_small')}
                            background: transparent;
                        }}
                        """
                    )
                    fb_layout.addWidget(title, 0)
                    fb_layout.addWidget(msg, 1)
                    self.live2d_panel = fallback

                dock = QDockWidget("", dock_host)
                dock.setObjectName("live2dDock")
                dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
                dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
                dock.setTitleBarWidget(QWidget())
                dock.setWidget(self.live2d_panel)
                dock_host.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
                self._messages_dock_host = dock_host
                self._live2d_dock = dock
                try:
                    sig = getattr(self.live2d_panel, "collapse_requested", None)
                    if sig is not None:
                        sig.connect(self._on_live2d_collapse_requested)
                except Exception:
                    pass
                # A slightly wider default looks much better for Live2D.
                try:
                    dock_host.resizeDocks([dock], [420], Qt.Orientation.Horizontal)
                except Exception:
                    pass
            except Exception as exc:
                logger.error("Live2D dock host init failed: %s", exc, exc_info=True)
                self.live2d_panel = None

            chat_layout.addWidget(dock_host, 1)
        except Exception:
            # Fallback layout: no dock host; still keep the 3-column structure.
            fallback = QWidget()
            fallback.setStyleSheet("background: transparent;")
            fb_layout = QHBoxLayout(fallback)
            fb_layout.setContentsMargins(0, 0, 0, 0)
            fb_layout.setSpacing(0)
            fb_layout.addWidget(center_column, 1)
            if self.live2d_panel is not None:
                fb_layout.addWidget(self.live2d_panel, 0)
            chat_layout.addWidget(fallback, 1)

        # 将聊天区域添加到 StackedWidget
        self.stacked_widget.addWidget(chat_area)

        # 设置面板改为懒加载：避免启动即构建大体量 UI（roleplay_settings_panel.py）
        self.settings_panel = None

        # 默认显示聊天区域
        self.stacked_widget.setCurrentIndex(0)

        # ==================== GUI 性能优化集成 v2.32.0 ====================
        try:
            # v2.32.0: 性能优化器已在__init__中导入
            # 初始化性能优化器
            self.performance_optimizer = ChatWindowOptimizer(
                scroll_area=self.scroll_area,
                enable_gpu=True,
                enable_memory_management=True,
                max_messages=200,
            )

            # 应用优化到现有窗口
            self.performance_optimizer.optimize_existing_window(self)

            logger.info("GUI 性能优化已启用（v2.32.0）")
        except Exception as e:
            logger.warning("GUI 性能优化启用失败: %s", e)
            self.performance_optimizer = None
        # ==================== 集成完成 ====================

    def showEvent(self, event):
        """窗口显示事件 - 同步发送按钮状态。"""
        super().showEvent(event)
        try:
            self._set_send_enabled(True)
        except Exception:
            pass

    def _set_send_enabled(self, enabled: bool) -> None:
        """统一管理发送按钮状态，避免在 Agent 未就绪时误启用。"""
        try:
            has_content = True
            try:
                if hasattr(self, "enhanced_input") and self.enhanced_input is not None:
                    has_content = bool(self.enhanced_input.has_content())
                elif hasattr(self, "input_text") and self.input_text is not None:
                    has_content = bool(self.input_text.toPlainText().strip())
            except Exception:
                has_content = True

            is_sending = False
            try:
                thread = getattr(self, "current_chat_thread", None)
                is_sending = bool(thread is not None and thread.isRunning())
            except Exception:
                is_sending = False

            asr_listening = bool(getattr(self, "_asr_listening", False))
            agent_ready = (self.agent is not None) and not bool(getattr(self, "_agent_initializing", False))
            can_send = bool(enabled) and agent_ready and has_content and not is_sending and not asr_listening
            self.send_btn.setEnabled(can_send)
        except Exception:
            pass

    def _update_agent_status_label(self) -> None:
        """根据 Agent 状态刷新头部状态文本。"""
        try:
            if not hasattr(self, "status_label") or self.status_label is None:
                return
            if bool(getattr(self, "_agent_initializing", False)):
                color = MD3_ENHANCED_COLORS["warning"]
                self.status_label.setText("● 初始化中")
                self.status_label.setStyleSheet(
                    f"""
                    QLabel {{
                        color: {color};
                        {get_typography_css('body_small')}
                        background: transparent;
                        font-weight: 600;
                    }}
                    """
                )
                return
            if self.agent is None or bool(getattr(self, "_agent_init_failed", False)):
                color = MD3_ENHANCED_COLORS["outline"]
                self.status_label.setText("● 离线")
                self.status_label.setStyleSheet(
                    f"""
                    QLabel {{
                        color: {color};
                        {get_typography_css('body_small')}
                        background: transparent;
                        font-weight: 600;
                    }}
                    """
                )
                return
            color = MD3_ENHANCED_COLORS["success"]
            self.status_label.setText("● 在线")
            self.status_label.setStyleSheet(
                f"""
                QLabel {{
                    color: {color};
                    {get_typography_css('body_small')}
                    background: transparent;
                    font-weight: 600;
                }}
                """
            )
        except Exception:
            pass

    def _init_agent_async(self) -> None:
        """后台初始化 Agent，避免启动卡顿；初始化完成后再允许发送。"""
        try:
            thread = getattr(self, "_agent_init_thread", None)
            if thread is not None and thread.isRunning():
                return
        except Exception:
            pass

        self._agent_initializing = True
        self._agent_init_failed = False
        self._update_agent_status_label()
        try:
            island = getattr(self, "character_island", None)
            if island is not None:
                island.set_agent(None)
        except Exception:
            pass
        self._set_send_enabled(True)

        thread = AgentInitThread(user_id=getattr(self, "_agent_user_id", None))
        thread.agent_ready.connect(self._on_agent_ready)
        thread.error.connect(self._on_agent_init_failed)
        self._agent_init_thread = thread
        thread.start()

    def _cleanup_agent_init_thread(self) -> None:
        thread = getattr(self, "_agent_init_thread", None)
        self._agent_init_thread = None
        if thread is None:
            return
        try:
            thread.deleteLater()
        except Exception:
            pass

    def _on_agent_ready(self, agent: object) -> None:
        self.agent = agent
        self._agent_initializing = False
        self._agent_init_failed = False
        self._cleanup_agent_init_thread()

        # 让设置面板（若已创建）获取到最新 agent
        try:
            if getattr(self, "settings_panel", None) is not None:
                self.settings_panel.agent = self.agent
        except Exception:
            pass

        self._update_agent_status_label()
        try:
            island = getattr(self, "character_island", None)
            if island is not None:
                island.set_agent(self.agent)
        except Exception:
            pass
        self._set_send_enabled(True)
        try:
            show_toast(self, "AI 助手已就绪", Toast.TYPE_SUCCESS, duration=1500)
        except Exception:
            pass

    def _on_agent_init_failed(self, error: str) -> None:
        self.agent = None
        self._agent_initializing = False
        self._agent_init_failed = True
        self._cleanup_agent_init_thread()

        self._update_agent_status_label()
        try:
            island = getattr(self, "character_island", None)
            if island is not None:
                island.set_agent(None)
        except Exception:
            pass
        self._set_send_enabled(True)

        logger.error("Agent 初始化失败: %s", error)
        try:
            msg = (error or "").splitlines()[0] if error else "未知错误"
            show_toast(self, f"AI 初始化失败: {msg}", Toast.TYPE_ERROR, duration=3000)
        except Exception:
            pass

    def _send_message(self):
        """发送消息 - v2.30.7: 统一走增强输入框（支持内联表情包/附件）。"""
        try:
            # 通过 RichTextInput 的 send_requested 信号复用 EnhancedInputWidget 的采集逻辑
            if getattr(self, "input_text", None) is not None:
                self.input_text.send_requested.emit()
                return
        except Exception:
            pass

    def _add_message(
        self,
        message: str,
        is_user: bool = True,
        save_to_db: bool = True,
        with_animation: bool = True,
    ):
        """添加消息 - v2.29.10 优化：使用预编译正则表达式

        Args:
            message: 消息内容（可能包含 [STICKER:path] 标记）
            is_user: 是否为用户消息
            save_to_db: 是否保存到数据库（加载历史消息时设为False）
            with_animation: 是否显示入场动画（加载历史消息时设为False以避免闪烁）
        """
        bulk_loading = bool(getattr(self, "_bulk_loading_messages", False))

        # v2.30.8: 防止添加空消息
        if not message or not message.strip():
            logger.warning("尝试添加空消息，已忽略: is_user=%s", is_user)
            return

        enable_entry_animation = bool(with_animation and GUI_ANIMATIONS_ENABLED)
        message_stripped = message.strip()

        # v2.29.10: 使用预编译的正则表达式，提升性能
        sticker_only = STICKER_PATTERN.fullmatch(message_stripped)
        image_only = IMAGE_PATTERN.fullmatch(message_stripped)
        if sticker_only:
            # 纯表情包消息：避免额外容器 widget，减少布局与重绘成本
            sticker_path = sticker_only.group(1)
            bubble = LightImageMessageBubble(
                sticker_path,
                is_user,
                is_sticker=True,
                with_animation=enable_entry_animation,
                enable_shadow=with_animation,
                autoplay=not bulk_loading,
            )
            self._register_animated_image_bubble(bubble)
            self.messages_layout.insertWidget(self.messages_layout.count() - 1, bubble)

            if not bulk_loading:
                # v2.30.8: 强制显示气泡
                bubble.show()
                self.messages_layout.update()
                self._schedule_messages_geometry_update()
        elif image_only:
            image_path = image_only.group(1)
            bubble = LightImageMessageBubble(
                image_path,
                is_user,
                is_sticker=False,
                with_animation=enable_entry_animation,
                enable_shadow=with_animation,
                autoplay=not bulk_loading,
            )
            self._register_animated_image_bubble(bubble)
            self.messages_layout.insertWidget(self.messages_layout.count() - 1, bubble)

            if not bulk_loading:
                bubble.show()
                self.messages_layout.update()
                self._schedule_messages_geometry_update()
        elif STICKER_PATTERN.search(message):
            # 混合消息：需要分段处理
            self._add_mixed_message(message, is_user, with_animation)
        else:
            # 纯文本消息
            bubble = LightMessageBubble(message, is_user, enable_shadow=with_animation)

            # v2.30.8: 计算插入位置 - 总是插入到最后（stretch之前）
            insert_position = self.messages_layout.count() - 1

            self.messages_layout.insertWidget(insert_position, bubble)

            if not bulk_loading:
                # v2.30.8: 强制显示气泡
                bubble.show()  # 确保气泡可见

                # v2.30.13: 立即更新布局，避免错位
                self.messages_layout.update()
                self._schedule_messages_geometry_update()
                if enable_entry_animation:
                    bubble.show_with_animation()

        # Live2D: subtle reaction on message add (skip bulk/history loads).
        if not bulk_loading:
            try:
                self._maybe_live2d_react("user_send" if is_user else "assistant_reply")
            except Exception:
                pass

        # 保存到数据库和缓存
        if save_to_db:
            if user_session.is_logged_in():
                try:
                    role = "user" if is_user else "assistant"
                    saved = user_session.add_message(self.current_contact, role, message)
                    logger.debug("消息已保存: %s - %s", self.current_contact, role)

                    # v2.30.14: 更新缓存（注意：这里没有msg_id，因为是新消息）
                    # 缓存将在下次加载历史消息时更新
                    # 这里不再维护缓存，避免不一致
                    if saved:
                        contact = self.current_contact
                        if contact:
                            if not hasattr(self, "_loaded_message_count"):
                                self._loaded_message_count = {}
                            if not hasattr(self, "_total_message_count"):
                                self._total_message_count = {}
                            self._loaded_message_count[contact] = self._loaded_message_count.get(contact, 0) + 1
                            self._total_message_count[contact] = self._total_message_count.get(contact, 0) + 1
                except Exception as e:
                    from src.utils.exceptions import handle_exception

                    handle_exception(e, logger, "保存消息到数据库失败")

        if not bulk_loading:
            self._enforce_shadow_budget()
            self._schedule_animated_image_budget()
            # 长对话保护：只在用户位于底部（允许自动滚动）时裁剪旧消息，避免影响用户阅读历史
            self._schedule_trim_rendered_messages(force=False)

        if bulk_loading:
            return

        # 滚动策略：用户消息强制到底部；助手消息仅在接近底部时自动跟随（避免用户上滑时被拉回）
        if is_user:
            self._ensure_scroll_to_bottom()
        else:
            self._scroll_to_bottom()

    def _disable_shadow_recursive(self, widget) -> None:
        """递归关闭旧消息的阴影效果，降低大量消息时的渲染开销。"""
        if widget is None:
            return

        # 兜底：如果某个 widget 直接挂了 DropShadowEffect，但没有实现 disable_shadow，也能被预算机制关闭。
        try:
            effect = widget.graphicsEffect() if hasattr(widget, "graphicsEffect") else None
            if isinstance(effect, QGraphicsDropShadowEffect):
                widget.setGraphicsEffect(None)
        except Exception:
            pass

        if hasattr(widget, "disable_shadow"):
            try:
                widget.disable_shadow()
                return
            except Exception:
                pass

        # 容器（混合消息）
        layout = widget.layout() if hasattr(widget, "layout") else None
        if layout is None:
            return

        for i in range(layout.count()):
            item = layout.itemAt(i)
            child = item.widget() if item else None
            if child is not None:
                self._disable_shadow_recursive(child)

    def _enforce_shadow_budget(self) -> None:
        """
        限制带阴影的消息数量（保留最新 N 条的阴影），避免长对话导致 GPU/CPU 开销线性增长。
        """
        shadow_budget = SHADOW_BUDGET
        # layout 的最后一个是 stretch
        message_count = self.messages_layout.count() - 1
        if message_count <= shadow_budget:
            return

        index_to_disable = message_count - shadow_budget - 1
        if index_to_disable < 0:
            return

        item = self.messages_layout.itemAt(index_to_disable)
        widget = item.widget() if item else None
        if widget is None:
            return

        self._disable_shadow_recursive(widget)

    def _register_animated_image_bubble(self, bubble: LightImageMessageBubble) -> None:
        """登记可播放动图的图片气泡，供滚动预算控制使用。"""
        try:
            if bubble is None:
                return
            if not bubble.supports_animation():
                return
        except Exception:
            return

        try:
            animated_set = getattr(self, "_animated_image_bubbles", None)
            if animated_set is None:
                self._animated_image_bubbles = weakref.WeakSet()
                animated_set = self._animated_image_bubbles
            animated_set.add(bubble)
        except Exception:
            pass

    def _schedule_animated_image_budget(self) -> None:
        """调度动图预算更新（去抖）。"""
        if not ANIMATED_IMAGE_VISIBLE_ONLY and ANIMATED_IMAGE_BUDGET <= 0:
            return

        if not hasattr(self, "_animated_image_budget_timer"):
            self._animated_image_budget_timer = QTimer(self)
            self._animated_image_budget_timer.setSingleShot(True)
            self._animated_image_budget_timer.timeout.connect(self._enforce_animated_image_budget)

        timer = getattr(self, "_animated_image_budget_timer", None)
        if timer is None or timer.isActive():
            return

        timer.start(int(ANIMATED_IMAGE_DEBOUNCE_MS))

    def _enforce_animated_image_budget(self) -> None:
        """限制可见区域动图播放数量，并停止屏幕外动画（长对话性能保护）。"""
        if not ANIMATED_IMAGE_VISIBLE_ONLY and ANIMATED_IMAGE_BUDGET <= 0:
            return

        messages_widget = getattr(self, "messages_widget", None)
        if messages_widget is None:
            return

        animated_set = getattr(self, "_animated_image_bubbles", None)
        if animated_set is None:
            # 兼容兜底：极端情况下索引未初始化，退回全树扫描（更慢，但保证功能可用）。
            try:
                bubbles = messages_widget.findChildren(LightImageMessageBubble)
            except Exception:
                bubbles = []

            animated: list[LightImageMessageBubble] = []
            for bubble in bubbles:
                try:
                    if bubble is not None and bubble.supports_animation():
                        animated.append(bubble)
                except Exception:
                    continue
        else:
            # 正常路径：只处理登记过的动图气泡（避免滚动时全树扫描导致掉帧）。
            try:
                animated = [b for b in list(animated_set) if b is not None]
            except Exception:
                animated = []

        if not animated:
            return

        scroll_area = getattr(self, "scroll_area", None)
        viewport = scroll_area.viewport() if scroll_area is not None else None
        if viewport is None:
            return

        try:
            vp_rect = viewport.rect()
            tl = viewport.mapTo(messages_widget, vp_rect.topLeft())
            br = viewport.mapTo(messages_widget, vp_rect.bottomRight())
            visible_rect = QRect(tl, br).normalized()
        except Exception:
            visible_rect = None

        visible_items: list[tuple[LightImageMessageBubble, Optional[QRect]]] = []
        offscreen: list[LightImageMessageBubble] = []

        if visible_rect is not None:
            for bubble in animated:
                try:
                    pos = bubble.mapTo(messages_widget, QPoint(0, 0))
                    rect = QRect(pos, bubble.size())
                except Exception:
                    continue

                if rect.intersects(visible_rect):
                    visible_items.append((bubble, rect))
                else:
                    offscreen.append(bubble)
        else:
            visible_items = [(bubble, None) for bubble in animated]

        if ANIMATED_IMAGE_VISIBLE_ONLY:
            for bubble in offscreen:
                try:
                    bubble.set_animation_enabled(False)
                except Exception:
                    pass

        budget = int(ANIMATED_IMAGE_BUDGET)
        if budget <= 0:
            # 无数量预算时，仅确保“配置为自动播放”的可见动图恢复播放
            for bubble, _rect in visible_items:
                try:
                    if bubble.wants_autoplay() and not bubble.is_animation_enabled():
                        bubble.set_animation_enabled(True)
                except Exception:
                    pass
            return

        if visible_rect is None:
            ref_y = 0
        else:
            # 用户在底部时优先保留最新（更靠近底部）的动图播放；否则以视窗中心为参考。
            if getattr(self, "_auto_scroll_enabled", True):
                ref_y = visible_rect.bottom()
            else:
                ref_y = visible_rect.center().y()

        def _rank(item: tuple[LightImageMessageBubble, Optional[QRect]]) -> tuple[int, int]:
            bubble, rect = item
            try:
                enabled = bubble.is_animation_enabled()
            except Exception:
                enabled = False
            try:
                autoplay = bubble.wants_autoplay()
            except Exception:
                autoplay = False

            # 0: 已在播放（尽量保持稳定），1: 可自动播放（允许启动），2: 其余（不主动启动）
            tier = 0 if enabled else (1 if autoplay else 2)

            if rect is None:
                dist = 0
            else:
                dist = abs(int(rect.center().y()) - int(ref_y))
            return tier, dist

        ranked = sorted(visible_items, key=_rank)
        allowed = {bubble for bubble, _rect in ranked[:budget]}

        for bubble, _rect in visible_items:
            try:
                if bubble in allowed:
                    if bubble.wants_autoplay() and not bubble.is_animation_enabled():
                        bubble.set_animation_enabled(True)
                else:
                    if bubble.is_animation_enabled():
                        bubble.set_animation_enabled(False)
            except Exception:
                continue

    def _schedule_trim_rendered_messages(self, *, force: bool = False) -> None:
        """调度裁剪渲染消息（批量执行，避免一次性删除大量 widget 卡顿）。"""
        if MAX_RENDERED_MESSAGES <= 0:
            return
        if getattr(self, "_bulk_loading_messages", False):
            return
        if not force and not getattr(self, "_auto_scroll_enabled", True):
            return

        # 阈值未触发时不必调度（避免每条消息都排队一个 singleShot）
        if not force:
            try:
                message_count = self.messages_layout.count() - 1  # 末尾是 stretch
            except Exception:
                message_count = 0
            if message_count <= (MAX_RENDERED_MESSAGES + TRIM_RENDERED_MESSAGES_BATCH - 1):
                return

        if getattr(self, "_trim_messages_pending", False):
            if force:
                self._trim_messages_force = True
            return

        self._trim_messages_pending = True
        self._trim_messages_force = bool(force)
        QTimer.singleShot(0, self._trim_rendered_messages_batch)

    def _trim_rendered_messages_batch(self) -> None:
        """裁剪旧消息（移除顶部最旧的若干条），保持滚动流畅。"""
        pending = bool(getattr(self, "_trim_messages_pending", False))
        if pending:
            self._trim_messages_pending = False

        force = bool(getattr(self, "_trim_messages_force", False))
        self._trim_messages_force = False

        max_messages = int(MAX_RENDERED_MESSAGES)
        if max_messages <= 0:
            return
        if getattr(self, "_bulk_loading_messages", False):
            return
        if not force and not getattr(self, "_auto_scroll_enabled", True):
            return

        message_count = self.messages_layout.count() - 1  # 末尾是 stretch
        over = message_count - max_messages
        if over <= 0:
            return

        batch_size = int(TRIM_RENDERED_MESSAGES_BATCH)
        # 频率控制：允许消息数量在 [max, max+batch) 之间小幅波动，减少频繁删 widget 导致的抖动
        if not force and over < batch_size:
            return

        remove_target = min(int(over), batch_size)
        removed = 0

        scrollbar = self.scroll_area.verticalScrollBar()
        scroll_widget = self.scroll_area.widget()
        old_scrollbar_signals = False
        try:
            try:
                old_scrollbar_signals = scrollbar.blockSignals(True)
            except Exception:
                old_scrollbar_signals = False

            # 删除期间禁用更新，避免频繁重绘
            self.scroll_area.setUpdatesEnabled(False)
            if scroll_widget is not None:
                scroll_widget.setUpdatesEnabled(False)

            while removed < remove_target and self.messages_layout.count() > 1:
                item = self.messages_layout.takeAt(0)
                widget = item.widget() if item else None
                if widget is None:
                    continue
                # 极端兜底：避免误删正在流式的气泡
                if widget is getattr(self, "current_streaming_bubble", None):
                    self.messages_layout.insertWidget(self.messages_layout.count() - 1, widget)
                    break
                try:
                    if hasattr(widget, "cleanup"):
                        widget.cleanup()
                except Exception:
                    pass
                try:
                    widget.setParent(None)
                except Exception:
                    pass
                widget.deleteLater()
                removed += 1
        finally:
            if scroll_widget is not None:
                scroll_widget.setUpdatesEnabled(True)
            self.scroll_area.setUpdatesEnabled(True)
            try:
                scrollbar.blockSignals(old_scrollbar_signals)
            except Exception:
                pass

        if removed <= 0:
            return

        # 裁剪属于“UI 侧卸载旧消息”，loaded_count 需要同步减少，否则分页 offset 会跳过缺失段
        contact = getattr(self, "current_contact", None)
        if contact and hasattr(self, "_loaded_message_count"):
            try:
                current_loaded = int(self._loaded_message_count.get(contact, 0))
                self._loaded_message_count[contact] = max(0, current_loaded - removed)
            except Exception:
                pass

        self.messages_layout.update()
        self._schedule_messages_geometry_update()
        if getattr(self, "_auto_scroll_enabled", True):
            self._ensure_scroll_to_bottom()
        self._schedule_animated_image_budget()

        # 如果仍超出预算，继续分批裁剪（下一轮事件循环执行）
        if (self.messages_layout.count() - 1) > max_messages:
            self._schedule_trim_rendered_messages(force=force)

    def _add_mixed_message(self, message: str, is_user: bool, with_animation: bool):
        """添加混合消息（文字+表情包）- v2.29.9 优化：性能和内存优化

        Args:
            message: 混合消息内容
            is_user: 是否为用户消息
            with_animation: 是否显示动画
        """
        from PyQt6.QtWidgets import QWidget, QHBoxLayout
        try:
            bulk_loading = bool(getattr(self, "_bulk_loading_messages", False))
            # 创建容器
            container = QWidget()
            layout = QHBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)

            enable_entry_animation = bool(with_animation and GUI_ANIMATIONS_ENABLED)

            # v2.29.10: 使用预编译的正则表达式，提升性能
            parts = STICKER_PATTERN.split(message)

            # v2.29.9: 批量创建组件，减少布局更新
            widgets = []
            for i, part in enumerate(parts):
                if not part:
                    continue

                if i % 2 == 0:
                    # 文字部分
                    if part.strip():
                        text_bubble = LightMessageBubble(part, is_user, enable_shadow=with_animation)
                        if enable_entry_animation:
                            text_bubble.show_with_animation()
                        widgets.append(text_bubble)
                else:
                    # 表情包部分（part 是路径）
                    sticker_bubble = LightImageMessageBubble(
                        part,
                        is_user,
                        is_sticker=True,
                        with_animation=enable_entry_animation,
                        enable_shadow=with_animation,
                        autoplay=not bulk_loading,
                    )
                    self._register_animated_image_bubble(sticker_bubble)
                    widgets.append(sticker_bubble)

            # v2.29.9: 批量添加组件，减少重绘
            container.setUpdatesEnabled(False)
            for widget in widgets:
                layout.addWidget(widget)
            layout.addStretch()
            container.setUpdatesEnabled(True)

            # 添加到消息列表
            self.messages_layout.insertWidget(self.messages_layout.count() - 1, container)

        except Exception as e:
            logger.error("添加混合消息失败: %s", e, exc_info=True)
            # 降级处理：作为纯文本消息添加
            enable_entry_animation = bool(with_animation and GUI_ANIMATIONS_ENABLED)
            bubble = LightMessageBubble(message, is_user, enable_shadow=with_animation)
            if enable_entry_animation:
                bubble.show_with_animation()
            self.messages_layout.insertWidget(self.messages_layout.count() - 1, bubble)

    def _add_image_message(self, image_path: str, is_user: bool = True):
        """添加图片消息 - v2.18.1 新增

        Args:
            image_path: 图片文件路径
            is_user: 是否为用户消息
        """
        bulk_loading = bool(getattr(self, "_bulk_loading_messages", False))
        enable_entry_animation = bool(GUI_ANIMATIONS_ENABLED)
        bubble = LightImageMessageBubble(
            image_path,
            is_user,
            with_animation=enable_entry_animation,
            enable_shadow=True,
            autoplay=not bulk_loading,
        )
        self._register_animated_image_bubble(bubble)
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, bubble)
        if not bulk_loading:
            self._schedule_animated_image_budget()
        # 动画会持续触发重绘；默认禁用入场动画时，直接滚动到底部即可
        if enable_entry_animation:
            QTimer.singleShot(200, self._ensure_scroll_to_bottom)
        else:
            self._ensure_scroll_to_bottom()

    @throttle(150)
    def _scroll_to_bottom(self):
        """滚动到底部（节流优化，最多每150ms滚动一次）- v2.48.6 优化：添加平滑滚动"""
        if not getattr(self, "_auto_scroll_enabled", True):
            return
        self._smooth_scroll_to_bottom()

    def _ensure_scroll_to_bottom(self):
        """确保滚动到底部（绕过节流限制）- v2.48.6 优化：添加平滑滚动"""
        try:
            # 优先走性能优化器的批量滚动（更省资源，避免频繁创建滚动动画）
            if getattr(self, "performance_optimizer", None) is not None:
                self.performance_optimizer.schedule_scroll(force=True)
                return
        except Exception:
            # 性能优化器异常不应影响正常滚动
            pass

        self._smooth_scroll_to_bottom()

    def _smooth_scroll_to_bottom(self):
        """平滑滚动到底部 - v2.48.6 新增

        使用动画平滑滚动到底部，提升用户体验
        """
        scrollbar = self.scroll_area.verticalScrollBar()
        current_value = scrollbar.value()
        target_value = scrollbar.maximum()

        # 性能优先：默认禁用平滑滚动（会持续触发重绘，长对话很容易掉帧）
        if not SMOOTH_SCROLL_ENABLED:
            scrollbar.setValue(target_value)
            return

        # 如果已经在底部或距离很近（<20px），直接跳转
        if abs(target_value - current_value) < 20:
            scrollbar.setValue(target_value)
            return

        # 创建平滑滚动动画
        if not hasattr(self, '_scroll_animation'):
            self._scroll_animation = QPropertyAnimation(scrollbar, b"value")
            self._scroll_animation.setDuration(200)  # 200ms 平滑滚动
            self._scroll_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._scroll_animation.setStartValue(current_value)
        self._scroll_animation.setEndValue(target_value)
        self._scroll_animation.start()

    def _schedule_messages_geometry_update(self) -> None:
        """合并消息区的 updateGeometry 调用，避免触发同步布局抖动。"""
        if getattr(self, "_messages_geometry_update_pending", False):
            return
        self._messages_geometry_update_pending = True

        def do_update() -> None:
            self._messages_geometry_update_pending = False
            try:
                widget = self.scroll_area.widget() if hasattr(self, "scroll_area") else None
                if widget is not None:
                    widget.updateGeometry()
            except Exception:
                pass

        # 延迟到下一轮事件循环，让 Qt 先完成插入/尺寸 hint 计算
        QTimer.singleShot(0, do_update)

    def _show_typing_indicator(self):
        """显示打字指示器 - v2.30.8 修复：确保插入到正确位置"""
        # 先移除旧的打字指示器（如果存在）
        if hasattr(self, "typing_indicator") and self.typing_indicator is not None:
            self._hide_typing_indicator()

        self.typing_indicator = LightTypingIndicator()
        # v2.30.8: 插入到最后（stretch之前）
        insert_position = self.messages_layout.count() - 1
        logger.debug("显示打字指示器: position=%s, total_count=%s", insert_position, self.messages_layout.count())
        self.messages_layout.insertWidget(insert_position, self.typing_indicator)

        # v2.30.8: 强制显示和更新
        self.typing_indicator.show()
        self.messages_layout.update()
        self._schedule_messages_geometry_update()

    def _ensure_stream_render_state(self) -> None:
        """初始化流式渲染队列与定时器（用于更丝滑的“逐步显示”效果）。"""
        if not hasattr(self, "_stream_render_queue"):
            self._stream_render_queue = deque()
            self._stream_render_pending = ""
            self._stream_render_pending_pos = 0
            self._stream_render_remaining = 0

        if not hasattr(self, "_stream_render_timer"):
            self._stream_render_timer = QTimer(self)
            self._stream_render_timer.setInterval(STREAM_RENDER_INTERVAL_MS)
            self._stream_render_timer.timeout.connect(self._drain_stream_render_queue)

    def _reset_stream_render_state(self) -> None:
        """停止流式渲染并清空队列（用于结束/错误/切换对话时）。"""
        timer = getattr(self, "_stream_render_timer", None)
        if timer is not None and timer.isActive():
            timer.stop()

        if hasattr(self, "_stream_render_queue"):
            try:
                self._stream_render_queue.clear()
            except Exception:
                self._stream_render_queue = deque()

        self._stream_render_pending = ""
        self._stream_render_pending_pos = 0
        self._stream_render_remaining = 0

    def _schedule_stream_scroll(self) -> None:
        """轻量调度滚动到底部（保持视图跟随，但避免信号风暴）。"""
        if not getattr(self, "_auto_scroll_enabled", True):
            return
        if getattr(self, "performance_optimizer", None) is not None:
            try:
                self.performance_optimizer.schedule_scroll()
                return
            except Exception:
                pass

        if not hasattr(self, "_scroll_timer"):
            self._scroll_timer = QTimer(self)
            self._scroll_timer.setSingleShot(True)
            # 流式期间更强调“跟随”，这里绕过 _scroll_to_bottom 的节流限制
            self._scroll_timer.timeout.connect(self._ensure_scroll_to_bottom)

        # 关键：不要在高频调用下重复 start()（会不断重置计时器，导致滚动延迟到“最后才跳一下”）
        if self._scroll_timer.isActive():
            return
        self._scroll_timer.start(STREAM_SCROLL_INTERVAL_MS)

    def _get_stream_render_budget(self) -> int:
        """根据积压量动态调整每帧输出量：小积压更细腻，大积压自动加速追赶。"""
        backlog = int(getattr(self, "_stream_render_remaining", 0))
        if STREAM_RENDER_TYPEWRITER and not getattr(self, "_stream_model_done", False):
            if STREAM_RENDER_TYPEWRITER_MAX_BACKLOG <= 0 or backlog <= STREAM_RENDER_TYPEWRITER_MAX_BACKLOG:
                return 1
        base = int(STREAM_RENDER_BASE_CHARS)
        max_chars = int(STREAM_RENDER_MAX_CHARS)
        # 平滑加速：积压越大，每帧输出越多；积压较小时保持“ChatGPT 风格”的细粒度流式观感。
        budget = max(base, backlog // 50)
        return max(1, min(max_chars, budget))

    def _enqueue_stream_render_text(self, text: str) -> None:
        """将文本入队，交由渲染定时器按帧追加到气泡。"""
        text = text or ""
        if not text:
            return
        self._ensure_stream_render_state()

        queue = getattr(self, "_stream_render_queue", None)
        if queue is None:
            self._stream_render_queue = deque()
            queue = self._stream_render_queue

        for segment in self._split_large_text(text, max_len=2048):
            if not segment:
                continue
            queue.append(segment)
            self._stream_render_remaining += len(segment)

        timer = getattr(self, "_stream_render_timer", None)
        if timer is not None and not timer.isActive():
            timer.start()

    def _take_stream_render_text(self, max_chars: int) -> str:
        """从队列中取出最多 max_chars 字符，并维护 remaining 计数。"""
        if max_chars <= 0 or int(getattr(self, "_stream_render_remaining", 0)) <= 0:
            return ""

        queue = getattr(self, "_stream_render_queue", None)
        if queue is None:
            return ""

        pending = str(getattr(self, "_stream_render_pending", ""))
        pos = int(getattr(self, "_stream_render_pending_pos", 0))

        out_parts: list[str] = []
        budget = int(max_chars)
        while budget > 0 and int(getattr(self, "_stream_render_remaining", 0)) > 0:
            if not pending:
                if not queue:
                    break
                pending = queue.popleft()
                pos = 0

            available = len(pending) - pos
            if available <= 0:
                pending = ""
                pos = 0
                continue

            take = min(budget, available)
            out_parts.append(pending[pos : pos + take])
            pos += take
            budget -= take
            self._stream_render_remaining -= take

            if pos >= len(pending):
                pending = ""
                pos = 0

        self._stream_render_pending = pending
        self._stream_render_pending_pos = pos
        return "".join(out_parts)

    def _drain_stream_render_queue(self) -> None:
        """按帧把队列里的文本追加到气泡（默认 30fps），实现更自然的流式观感。"""
        if self.current_streaming_bubble is None:
            self._reset_stream_render_state()
            return

        text = self._take_stream_render_text(self._get_stream_render_budget())
        if text:
            self.current_streaming_bubble.append_text(text)
            self._schedule_stream_scroll()

        if int(getattr(self, "_stream_render_remaining", 0)) <= 0:
            timer = getattr(self, "_stream_render_timer", None)
            if timer is not None and timer.isActive():
                timer.stop()
            if getattr(self, "_stream_model_done", False):
                QTimer.singleShot(0, self._finalize_stream_response)

    def _drain_stream_render_all(self) -> None:
        """在收尾阶段一次性排空渲染队列，确保保存/落库的文本完整一致。"""
        timer = getattr(self, "_stream_render_timer", None)
        if timer is not None and timer.isActive():
            timer.stop()

        if self.current_streaming_bubble is None:
            self._reset_stream_render_state()
            return

        while int(getattr(self, "_stream_render_remaining", 0)) > 0:
            text = self._take_stream_render_text(4096)
            if not text:
                break
            self.current_streaming_bubble.append_text(text)

        self._schedule_stream_scroll()

    def _finalize_stream_response(self) -> None:
        """当模型完成且渲染队列已清空后，执行最终收尾（finish/落库/解锁输入）。"""
        # 兼容：若模型未输出任何 chunk，打字指示器可能仍在
        try:
            self._hide_typing_indicator()
        except Exception:
            pass

        if self.current_streaming_bubble is None:
            # 语音输入模式：若期间缓存了输出，则此处一次性落入普通气泡
            try:
                buf = getattr(self, "_asr_non_stream_buffer", None)
            except Exception:
                buf = None
            if buf:
                try:
                    full_response = "".join(buf).strip()
                    self._asr_non_stream_buffer = None
                except Exception:
                    full_response = ""
                    self._asr_non_stream_buffer = None

                if full_response and self._needs_tool_filter(full_response):
                    try:
                        full_response = self._filter_tool_info_safe(full_response)
                    except Exception:
                        pass

                if full_response and full_response.strip():
                    try:
                        self._add_message(full_response, is_user=False)
                    except Exception:
                        pass

            self._reset_stream_render_state()
            self._stream_model_done = False
            self._set_send_enabled(True)
            return

        full_response = self.current_streaming_bubble.message_text.toPlainText()

        # 最终过滤工具信息（确保保存到数据库的内容也是干净的）
        if full_response and self._needs_tool_filter(full_response):
            filtered_response = self._filter_tool_info_safe(full_response)
            if filtered_response != full_response:
                full_response = filtered_response
                try:
                    self.current_streaming_bubble.message_text.setPlainText(full_response)
                except Exception:
                    pass

        # 完成流式输出（停止 caret、补齐阴影、最终高度）
        try:
            self.current_streaming_bubble.finish()
        except Exception:
            pass
        self.current_streaming_bubble = None
        self._reset_stream_render_state()
        self._stream_model_done = False

        # v2.49.0: 流式气泡也是“新增消息”，需要纳入阴影预算管理，否则长对话会持续掉帧
        try:
            self._enforce_shadow_budget()
        except Exception:
            pass
        try:
            self._schedule_trim_rendered_messages(force=False)
        except Exception:
            pass

        # 保存AI回复到数据库
        if user_session.is_logged_in() and full_response.strip():
            try:
                saved = user_session.add_message(self.current_contact, "assistant", full_response)
                logger.debug("AI回复已保存: %s - assistant", self.current_contact)
                if saved:
                    contact = self.current_contact
                    if contact:
                        if not hasattr(self, "_loaded_message_count"):
                            self._loaded_message_count = {}
                        if not hasattr(self, "_total_message_count"):
                            self._total_message_count = {}
                        self._loaded_message_count[contact] = self._loaded_message_count.get(contact, 0) + 1
                        self._total_message_count[contact] = self._total_message_count.get(contact, 0) + 1
            except Exception as e:
                logger.error("保存AI回复失败: %s", e)

        # 解锁输入
        self._set_send_enabled(True)

        # Live2D: react once per completed assistant response.
        try:
            self._maybe_live2d_react("assistant_reply")
        except Exception:
            pass

        # 清理滚动定时器
        if hasattr(self, "_scroll_timer"):
            try:
                self._scroll_timer.stop()
            except Exception:
                pass
            del self._scroll_timer

        # 最终滚动到底部
        QTimer.singleShot(100, self._scroll_to_bottom)

    def _maybe_live2d_react(self, kind: str) -> None:
        """Trigger a light Live2D reaction if the panel is available and visible."""
        panel = getattr(self, "live2d_panel", None)
        if panel is None:
            return
        try:
            if bool(getattr(panel, "is_collapsed", False)):
                return
        except Exception:
            pass

        gl = None
        try:
            gl = getattr(panel, "gl", None)
        except Exception:
            gl = None
        if gl is None:
            return

        try:
            if not panel.isVisible():
                return
        except Exception:
            pass

        # Simple debounce: avoid firing too many reactions during rapid message operations.
        try:
            now_ms = time.time() * 1000.0
            last = float(getattr(self, "_live2d_last_react_ms", 0.0) or 0.0)
            if now_ms - last < 650.0:
                return
            self._live2d_last_react_ms = now_ms
        except Exception:
            pass

        try:
            gl.trigger_reaction(str(kind or "manual"))
        except Exception:
            pass

    def _handle_stream_chunk(self, chunk: str) -> None:
        """处理流式输出块：过滤、创建气泡、入队渲染、TTS。"""
        chunk = chunk or ""
        if not chunk:
            return

        # 过滤工具信息（热路径：仅在看起来包含工具信息时执行，避免无谓开销）
        if self._needs_tool_filter(chunk):
            chunk = self._filter_tool_info_safe(chunk)
            if not chunk:
                return

        # 隐藏打字指示器（只在第一次）
        if hasattr(self, "typing_indicator") and self.typing_indicator is not None:
            self._hide_typing_indicator()
            if (
                hasattr(self, "tts_enabled")
                and self.tts_enabled
                and hasattr(self, "tts_stream_processor")
                and self.tts_stream_processor
            ):
                self.tts_stream_processor.reset()

        # 语音输入模式：消息区作为历史查看，禁用流式渲染（只缓存，结束后一次性落入普通气泡）
        if bool(getattr(self, "_asr_force_non_stream", False)):
            try:
                buf = getattr(self, "_asr_non_stream_buffer", None)
                if buf is None:
                    buf = []
                    self._asr_non_stream_buffer = buf
                buf.append(chunk)
            except Exception:
                pass
            return

        # 创建或更新流式消息气泡
        if self.current_streaming_bubble is None:
            self.current_streaming_bubble = LightStreamingMessageBubble()
            self._stream_model_done = False
            self.messages_layout.insertWidget(
                self.messages_layout.count() - 1, self.current_streaming_bubble
            )
            self.messages_layout.update()
            self._schedule_messages_geometry_update()

        # 入队：由渲染定时器分帧追加，避免“大段跳动”
        self._enqueue_stream_render_text(chunk)

        # 流式TTS处理
        if (
            hasattr(self, "tts_enabled")
            and self.tts_enabled
            and hasattr(self, "tts_stream_processor")
            and self.tts_stream_processor
        ):
            for sentence in self.tts_stream_processor.process_chunk(chunk):
                if not sentence or not sentence.strip():
                    continue
                filtered_sentence = (
                    self._filter_tool_info_safe(sentence)
                    if self._needs_tool_filter(sentence)
                    else sentence
                )
                if not filtered_sentence or not filtered_sentence.strip():
                    continue
                self._synthesize_tts_async(filtered_sentence)

    def _get_tool_filter_func(self):
        func = getattr(self, "_tool_filter_func", None)
        if func is not None:
            return func

        try:
            from src.agent.core import MintChatAgent

            func = MintChatAgent._filter_tool_info
        except Exception:
            func = None

        self._tool_filter_func = func
        return func

    def _filter_tool_info_safe(self, text: str) -> str:
        """过滤工具选择/调用信息（惰性加载，避免 import 阶段引入重依赖）。"""
        if not text:
            return text
        func = self._get_tool_filter_func()
        if func is None:
            return text
        try:
            return func(text)
        except Exception:
            return text

    @staticmethod
    def _needs_tool_filter(text: str) -> bool:
        """快速判断是否可能包含工具选择/调用信息，避免在热路径无谓调用过滤器。"""
        if not text:
            return False
        stripped = text.lstrip()
        if stripped.startswith("{") or stripped.startswith("["):
            return True
        if "```" in text:
            return True
        if "ToolSelectionResponse" in text:
            return True
        # 路由标签数组（例如：["local_search","map_guide"]}）通常不含 "tool" 字样
        # 这里用非常轻量的启发式触发过滤器，避免流式过程中“先看到脏文本，最后才被收尾过滤”。
        if '["' in text and "]" in text and "_" in text:
            return True
        return ("tool" in text) or ("Tool" in text)

    def _split_large_text(self, text: str, max_len: int = 1024):
        """将过长文本切分为小段以降低单次渲染压力。"""
        if not text or len(text) <= max_len:
            return [text]
        return [text[i:i + max_len] for i in range(0, len(text), max_len)]

    def _hide_typing_indicator(self):
        """隐藏打字指示器"""
        if hasattr(self, "typing_indicator") and self.typing_indicator is not None:
            self.typing_indicator.stop_animation()
            self.messages_layout.removeWidget(self.typing_indicator)
            self.typing_indicator.deleteLater()
            self.typing_indicator = None

    def _register_live_chat_thread(self, thread: Optional["ChatThread"]) -> None:
        if thread is None:
            return
        try:
            if thread not in self._live_chat_threads:
                self._live_chat_threads.append(thread)
        except Exception:
            self._live_chat_threads.append(thread)

    def _register_vision_task(self, task: object) -> None:
        """保留线程池任务引用，避免 QRunnable 被 GC 导致崩溃。"""
        if task is None:
            return
        try:
            if task not in self._vision_tasks:
                self._vision_tasks.append(task)
        except Exception:
            self._vision_tasks.append(task)

    def _cleanup_finished_vision_task(self, task: object) -> None:
        if task is None:
            return
        try:
            if task in self._vision_tasks:
                self._vision_tasks.remove(task)
        except Exception:
            pass

    def _cancel_chat_thread(self, thread: Optional["ChatThread"]) -> None:
        if thread is None:
            return
        self._register_live_chat_thread(thread)
        try:
            if thread.isRunning():
                thread.stop()
        except Exception as exc:
            logger.debug("停止 ChatThread 失败: %s", exc)

    def _cleanup_finished_chat_thread(self, thread: Optional["ChatThread"]) -> None:
        if thread is None:
            return
        try:
            try:
                thread.chunk_received.disconnect()
                thread.finished.disconnect()
                thread.error.disconnect()
            except TypeError:
                pass
        except Exception:
            pass

        try:
            thread.cleanup()
        except Exception:
            pass

        try:
            thread.deleteLater()
        except Exception:
            pass

        try:
            if thread in self._live_chat_threads:
                self._live_chat_threads.remove(thread)
        except Exception:
            pass

    def _on_chunk_received(self, chunk: str):
        """接收到流式输出块 - v2.48.12 修复：添加 TTS 流式处理"""
        sender = self.sender()
        if sender is not None and sender is not self.current_chat_thread:
            return
        self._handle_stream_chunk(chunk)

    def _on_chat_finished(self):
        """聊天完成：模型已结束，逐字渲染继续直到队列耗尽后再收尾。"""
        thread = self.sender()
        if thread is None or not isinstance(thread, ChatThread):
            thread = self.current_chat_thread
        if thread is None:
            return
        if thread is not self.current_chat_thread:
            self._cleanup_finished_chat_thread(thread)
            return
        if bool(getattr(thread, "_had_error", False)):
            self._cleanup_finished_chat_thread(thread)
            self.current_chat_thread = None
            return

        self._stream_model_done = True

        # v2.48.12: 处理 TTS 剩余文本（模型已结束即可 flush，不必等待 UI 完成逐字渲染）
        if (
            hasattr(self, "tts_enabled")
            and self.tts_enabled
            and hasattr(self, "tts_stream_processor")
            and self.tts_stream_processor
        ):
            remaining = self.tts_stream_processor.flush()
            if remaining:
                filtered_remaining = (
                    self._filter_tool_info_safe(remaining)
                    if self._needs_tool_filter(remaining)
                    else remaining
                )
                if not filtered_remaining or not filtered_remaining.strip():
                    logger.debug("TTS 跳过空剩余文本（过滤后）: %s...", remaining[:30])
                else:
                    self._synthesize_tts_async(filtered_remaining)
                    logger.debug("TTS 发送剩余文本: %s...", filtered_remaining[:30])

        # v2.30.14: 清理聊天线程，防止内存泄漏
        try:
            self._cleanup_finished_chat_thread(thread)
        finally:
            self.current_chat_thread = None

        # 若渲染队列已空（或没有气泡），立即收尾；否则由渲染定时器在耗尽时触发收尾。
        remaining = int(getattr(self, "_stream_render_remaining", 0))
        if remaining <= 0:
            QTimer.singleShot(0, self._finalize_stream_response)
            return

        timer = getattr(self, "_stream_render_timer", None)
        if timer is not None and not timer.isActive():
            timer.start()

    def _on_chat_error(self, error: str):
        """聊天错误 - v2.30.14 增强资源清理"""
        thread = self.sender()
        if thread is None or not isinstance(thread, ChatThread):
            thread = self.current_chat_thread
        if thread is None:
            return
        if thread is not self.current_chat_thread:
            # 旧线程的错误：忽略 UI，只做取消请求，等待 finished 时统一回收
            self._cancel_chat_thread(thread)
            return

        self._hide_typing_indicator()
        self._add_message(f"错误: {error}", is_user=False)
        self._stream_model_done = False
        # 标记为非当前线程，避免 finished 回调触发“正常完成”逻辑
        self.current_chat_thread = None

        # 请求取消：实际回收在 finished 信号中统一进行
        self._cancel_chat_thread(thread)

        # 清理流式气泡
        if self.current_streaming_bubble is not None:
            try:
                if hasattr(self.current_streaming_bubble, "cleanup"):
                    self.current_streaming_bubble.cleanup()
                self.messages_layout.removeWidget(self.current_streaming_bubble)
                self.current_streaming_bubble.deleteLater()
            except Exception:
                pass
            self.current_streaming_bubble = None

        # 清理流式渲染队列，避免残留内容在错误后继续输出
        try:
            self._reset_stream_render_state()
        except Exception:
            pass

        self._set_send_enabled(True)

    def _on_enhanced_send(self, text: str, sticker_paths: list, file_paths: list):
        """增强输入框发送处理 - v2.30.7 新增

        Args:
            text: 纯文本内容
            sticker_paths: 表情包路径列表
            file_paths: 文件路径列表
        """
        try:
            text = text or ""
            sticker_paths = [p for p in (sticker_paths or []) if p]
            file_paths = [p for p in (file_paths or []) if p]

            text_clean = text.strip()

            # v2.46.x: 发送侧防御性日志（不影响行为）。
            # 若仍出现“一张变两张”，优先看这里的计数与重复项（仅输出文件名，避免泄露路径）。
            try:
                logger.debug(
                    "enhanced_send collected: text_chars=%s, stickers=%s, files=%s",
                    len(text_clean),
                    len(sticker_paths),
                    len(file_paths),
                )
                seen: set[str] = set()
                dup_names: list[str] = []
                for p in sticker_paths:
                    key = os.path.normcase(os.path.normpath(str(p)))
                    if key in seen:
                        dup_names.append(Path(str(p)).name or str(p))
                    else:
                        seen.add(key)
                if dup_names:
                    logger.warning("检测到重复表情包路径（可能导致重复发送）: %s", dup_names)
            except Exception:
                pass
            if not (text_clean or sticker_paths or file_paths):
                return

            # 语音输入模式下禁用发送：避免边录音边触发对话与流式刷新
            if bool(getattr(self, "_asr_listening", False)):
                show_toast(self, "语音输入中：请先停止语音输入再发送", Toast.TYPE_INFO, duration=1600)
                return

            # Agent 未就绪时不允许发送：避免输入被清空/消息被写入历史后又失败
            if self.agent is None or bool(getattr(self, "_agent_initializing", False)):
                if bool(getattr(self, "_agent_initializing", False)):
                    show_toast(self, "AI 正在初始化，请稍候…", Toast.TYPE_INFO, duration=1500)
                else:
                    show_toast(self, "AI 未就绪，请检查配置后重试", Toast.TYPE_ERROR, duration=2500)
                self._set_send_enabled(True)
                return

            # 输入框清空由 ChatWindow 决定（EnhancedInputWidget 不再自动 clear）
            try:
                self.enhanced_input.clear_all()
            except Exception:
                pass
            # 兼容：旧的 pending_images 列表也需要清空，避免残留导致下次发送重复
            try:
                if hasattr(self, "pending_images"):
                    self.pending_images.clear()
            except Exception:
                pass

            # 1) UI/历史：先把用户本次发送的内容写入消息区（表情包/图片用 marker 表示）
            outgoing_messages: list[str] = []
            outgoing_messages.extend([f"[STICKER:{p}]" for p in sticker_paths])
            outgoing_messages.extend([f"[IMAGE:{p}]" for p in file_paths])
            if text_clean:
                outgoing_messages.append(text_clean)

            if outgoing_messages:
                if len(outgoing_messages) == 1:
                    self._add_message(outgoing_messages[0], is_user=True)
                    self._ensure_scroll_to_bottom()
                else:
                    scrollbar = self.scroll_area.verticalScrollBar()
                    scroll_widget = self.scroll_area.widget()
                    old_bulk_loading = getattr(self, "_bulk_loading_messages", False)
                    old_scrollbar_signals = False
                    try:
                        self._bulk_loading_messages = True
                        try:
                            old_scrollbar_signals = scrollbar.blockSignals(True)
                        except Exception:
                            old_scrollbar_signals = False
                        self.scroll_area.setUpdatesEnabled(False)
                        if scroll_widget is not None:
                            scroll_widget.setUpdatesEnabled(False)

                        for msg in outgoing_messages:
                            self._add_message(msg, is_user=True)
                    finally:
                        if scroll_widget is not None:
                            scroll_widget.setUpdatesEnabled(True)
                        self.scroll_area.setUpdatesEnabled(True)
                        try:
                            scrollbar.blockSignals(old_scrollbar_signals)
                        except Exception:
                            pass
                        self._bulk_loading_messages = old_bulk_loading

                    self.messages_layout.update()
                    self._schedule_messages_geometry_update()
                    self._enforce_shadow_budget()
                    self._schedule_animated_image_budget()
                    self._schedule_trim_rendered_messages(force=False)
                    self._ensure_scroll_to_bottom()

            # 2) 供 AI 理解：把“表情包信息”拼到用户文本后（并在启动线程前转成描述文本）
            ai_message_raw = text_clean
            if sticker_paths:
                stickers_raw = " ".join(f"[STICKER:{p}]" for p in sticker_paths)
                ai_message_raw = f"{ai_message_raw}\n{stickers_raw}" if ai_message_raw else stickers_raw

            # 3) 图片识别：该路径由图片识别流程接管（识别完成后再启动 ChatThread）
            if file_paths:
                if len(file_paths) > 1:
                    self._process_multiple_images(file_paths, ai_message_raw)
                    return

                self._recognize_and_send_image(file_paths[0], ai_message_raw)
                return

            if not ai_message_raw:
                return

            # 停止当前正在运行的聊天线程
            if self.current_chat_thread is not None and self.current_chat_thread.isRunning():
                self._cancel_chat_thread(self.current_chat_thread)

            # 移除旧的打字指示器（如果存在）
            if hasattr(self, "typing_indicator") and self.typing_indicator is not None:
                self._hide_typing_indicator()

            # 重置流式渲染状态（上一轮残留会影响逐字显示/动画）
            try:
                self._reset_stream_render_state()
            except Exception:
                pass
            self._stream_model_done = False

            # 显示打字指示器
            self._show_typing_indicator()

            ai_message = self._convert_stickers_to_description(ai_message_raw)

            # v2.30.0: 获取图片分析结果（如果有）
            image_analysis = self.current_image_analysis
            image_path = self.current_image_path
            self.current_image_analysis = None
            self.current_image_path = None

            # 创建并启动聊天线程（传递图片上下文，若有）
            self.current_chat_thread = ChatThread(
                self.agent,
                ai_message,
                image_path=image_path,
                image_analysis=image_analysis,
                emit_interval_ms=CHATTHREAD_EMIT_INTERVAL_MS,
                emit_threshold=CHATTHREAD_EMIT_THRESHOLD,
            )
            self._register_live_chat_thread(self.current_chat_thread)
            self.current_chat_thread.chunk_received.connect(self._on_chunk_received)
            self.current_chat_thread.finished.connect(self._on_chat_finished)
            self.current_chat_thread.error.connect(self._on_chat_error)
            self.current_chat_thread.start()

            # 禁用发送按钮
            self.send_btn.setEnabled(False)

        except Exception as e:
            logger.error("发送消息失败: %s", e, exc_info=True)
            show_toast(self, f"发送失败: {e}", Toast.TYPE_ERROR)

    def _show_composer_tools_menu(self) -> None:
        """显示输入框“+”菜单（附件、表情等）。"""
        from PyQt6.QtWidgets import QMenu

        anchor = getattr(self, "composer_plus_btn", None)
        if anchor is None:
            return

        menu = QMenu(self)
        menu_selected = qss_rgba(MD3_ENHANCED_COLORS["primary"], 0.08)
        menu.setStyleSheet(
            f"""
            QMenu {{
                background: {MD3_ENHANCED_COLORS['surface_container']};
                border: 1px solid {MD3_ENHANCED_COLORS['outline_variant']};
                border-radius: {MD3_ENHANCED_RADIUS['xl']};
                padding: 6px;
            }}
            QMenu::item {{
                padding: 8px 12px;
                border-radius: {MD3_ENHANCED_RADIUS['lg']};
                color: {MD3_ENHANCED_COLORS['on_surface']};
            }}
            QMenu::item:selected {{
                background: {menu_selected};
            }}
        """
        )

        attach_action = menu.addAction("添加图片/附件…")
        emoji_action = menu.addAction("表情/表情包…")
        menu.addSeparator()
        clear_action = menu.addAction("清空输入")

        action = menu.exec(anchor.mapToGlobal(QPoint(0, anchor.height())))
        if action is None:
            return
        if action == attach_action:
            self._on_attach_clicked()
        elif action == emoji_action:
            self._on_emoji_clicked()
        elif action == clear_action:
            try:
                self.enhanced_input.clear_all()
            except Exception:
                pass

    def _on_composer_mic_clicked(self) -> None:
        """输入框语音按钮点击：切换 ASR 语音输入模式。"""
        try:
            listening = bool(getattr(self, "_asr_listening", False))
        except Exception:
            listening = False

        if listening:
            self._stop_asr_listening()
            return

        self._start_asr_listening()

    def _start_asr_listening(self) -> None:
        """进入语音输入模式：启动 ASR 监听线程，并临时禁用发送/流式显示。"""
        try:
            from src.config.settings import settings
        except Exception:
            settings = None

        try:
            if settings is None or not hasattr(settings, "asr") or not settings.asr or not settings.asr.enabled:
                show_toast(self, "语音输入未启用，请在设置中开启 ASR 后重启", Toast.TYPE_INFO, duration=2200)
                return
        except Exception:
            show_toast(self, "语音输入配置不可用，请检查设置", Toast.TYPE_ERROR, duration=2200)
            return

        # FunASR 依赖/模型加载由启动预热完成；这里做一次兜底检测
        try:
            from src.multimodal import is_asr_available

            if callable(is_asr_available) and not is_asr_available():
                show_toast(
                    self,
                    "ASR 模型未就绪（请确认已安装 funasr 并重启预加载）",
                    Toast.TYPE_ERROR,
                    duration=2600,
                )
                return
        except Exception:
            show_toast(
                self,
                "ASR 不可用（缺少 funasr 或初始化失败）",
                Toast.TYPE_ERROR,
                duration=2600,
            )
            return

        # 启动监听线程
        try:
            from src.gui.workers.asr_listen import ASRListenThread
        except Exception as exc:
            show_toast(self, f"导入 ASR 线程失败：{exc}", Toast.TYPE_ERROR, duration=2400)
            return

        try:
            thread = getattr(self, "_asr_thread", None)
            if thread is not None and getattr(thread, "isRunning", lambda: False)():
                show_toast(self, "语音输入已在进行中", Toast.TYPE_INFO, duration=1200)
                return
        except Exception:
            pass

        try:
            sample_rate = int(getattr(settings.asr, "sample_rate", 16000))
            partial_interval_ms = int(getattr(settings.asr, "partial_interval_ms", 260))
            partial_window_s = float(getattr(settings.asr, "partial_window_s", 6.0))
        except Exception:
            sample_rate, partial_interval_ms, partial_window_s = 16000, 260, 6.0

        asr_thread = ASRListenThread(
            sample_rate=sample_rate,
            partial_interval_ms=partial_interval_ms,
            partial_window_s=partial_window_s,
            parent=self,
        )
        asr_thread.partial_text.connect(self._on_asr_partial_text)
        asr_thread.final_text.connect(self._on_asr_final_text)
        asr_thread.error.connect(self._on_asr_error)
        asr_thread.finished.connect(self._on_asr_finished)

        self._asr_thread = asr_thread
        self._asr_listening = True
        self._asr_force_non_stream = True

        try:
            if hasattr(self, "composer_mic_btn") and self.composer_mic_btn is not None:
                self.composer_mic_btn.set_active(True)
                self.composer_mic_btn.setToolTip("停止语音输入")
        except Exception:
            pass

        # 语音模式：禁用发送（Enter/按钮都会被拦截），消息区改为“历史查看”（暂不流式渲染）
        try:
            self._set_send_enabled(False)
        except Exception:
            pass
        try:
            msg = "开始语音输入…再次点击麦克风停止"
            try:
                endpoint_ms = int(getattr(getattr(settings, "asr", None), "endpoint_silence_ms", 0) or 0)
                if endpoint_ms > 0:
                    msg = "开始语音输入…再次点击麦克风停止，或停顿自动完成"
            except Exception:
                pass
            show_toast(self, msg, Toast.TYPE_INFO, duration=1600)
        except Exception:
            pass

        try:
            asr_thread.start()
        except Exception as exc:
            self._asr_listening = False
            self._asr_force_non_stream = False
            show_toast(self, f"启动语音输入失败：{exc}", Toast.TYPE_ERROR, duration=2400)

    def _stop_asr_listening(self) -> None:
        """退出语音输入模式：停止线程并恢复默认 UI 行为。"""
        try:
            thread = getattr(self, "_asr_thread", None)
        except Exception:
            thread = None

        try:
            self._asr_listening = False
            self._asr_force_non_stream = False
        except Exception:
            pass

        if thread is not None:
            try:
                thread.stop()
            except Exception:
                pass
            try:
                if thread.isRunning():
                    thread.wait(1500)
            except Exception:
                pass
            try:
                thread.deleteLater()
            except Exception:
                pass
            self._asr_thread = None

        try:
            if hasattr(self, "composer_mic_btn") and self.composer_mic_btn is not None:
                self.composer_mic_btn.set_active(False)
                self.composer_mic_btn.setToolTip("语音输入")
        except Exception:
            pass

        try:
            self._set_send_enabled(True)
        except Exception:
            pass

    def _on_asr_partial_text(self, text: str) -> None:
        if not bool(getattr(self, "_asr_listening", False)):
            return
        self._apply_asr_text_to_composer(text, final=False)

    def _on_asr_final_text(self, text: str) -> None:
        self._apply_asr_text_to_composer(text, final=True)

    def _on_asr_error(self, error: str) -> None:
        try:
            show_toast(self, f"语音输入失败：{error}", Toast.TYPE_ERROR, duration=2600)
        except Exception:
            pass
        self._stop_asr_listening()

    def _on_asr_finished(self) -> None:
        # 线程自然结束时，确保 UI 状态恢复
        try:
            if bool(getattr(self, "_asr_listening", False)):
                self._stop_asr_listening()
        except Exception:
            pass

    def _apply_asr_text_to_composer(self, text: str, *, final: bool) -> None:
        """把 ASR 文本写入输入框，尽量保持光标在末尾。"""
        text = (text or "").strip()
        if not text:
            return
        if getattr(self, "_asr_last_text", None) == text and not final:
            return
        self._asr_last_text = text

        editor = getattr(self, "input_text", None)
        if editor is None:
            return

        try:
            editor.setPlainText(text)
            try:
                from PyQt6.QtGui import QTextCursor

                cursor = editor.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                editor.setTextCursor(cursor)
                editor.ensureCursorVisible()
            except Exception:
                pass
        except Exception:
            pass

    def _on_emoji_clicked(self):
        """表情按钮点击 - v2.19.0 升级版"""
        # 创建表情选择器（如果还没有）
        if self.emoji_picker is None:
            from .emoji_picker import EmojiPicker

            # 获取当前用户ID
            user_id = user_session.get_user_id() if user_session.is_logged_in() else None

            self.emoji_picker = EmojiPicker(user_id=user_id, parent=self)
            self.emoji_picker.emoji_selected.connect(self._on_emoji_selected)
            self.emoji_picker.sticker_selected.connect(self._on_sticker_selected)

        # 显示表情选择器
        anchor = getattr(self, "composer_plus_btn", None) or getattr(self, "more_btn", None)
        if anchor is not None:
            self.emoji_picker.show_at_button(anchor)
        else:
            self.emoji_picker.show()

    def _on_emoji_selected(self, emoji: str):
        """表情选中 - 插入到输入框 - v2.30.7 优化"""
        self.enhanced_input.insert_emoji(emoji)

    def _analyze_sticker_emotion(self, sticker_path: str) -> str:
        """分析表情包情绪 - v2.29.8 新增

        Args:
            sticker_path: 表情包路径

        Returns:
            情绪描述，如 "开心"、"难过" 等
        """
        return _guess_sticker_emotion(sticker_path)

    def _convert_stickers_to_description(self, message: str) -> str:
        """将消息中的表情包标记转换为描述性文本 - v2.29.10 优化：使用预编译正则表达式

        Args:
            message: 原始消息，可能包含 [STICKER:path] 标记

        Returns:
            转换后的消息，表情包标记被替换为描述性文本
        """
        count = 0

        caption_map: dict[str, str] = {}
        if user_session.is_logged_in():
            try:
                user_id = user_session.get_user_id()
                stickers = user_session.data_manager.get_custom_stickers(user_id) if user_id else []
                for sticker in stickers:
                    try:
                        file_path = str(sticker.get("file_path") or "").strip()
                        caption = str(sticker.get("caption") or "").strip()
                    except Exception:
                        continue
                    if not (file_path and caption):
                        continue
                    key = os.path.normcase(os.path.normpath(file_path))
                    caption_map[key] = caption
            except Exception:
                caption_map = {}

        def _repl(match: re.Match) -> str:
            nonlocal count
            sticker_path = match.group(1)
            count += 1
            caption = ""
            try:
                caption = caption_map.get(os.path.normcase(os.path.normpath(sticker_path)), "") or ""
            except Exception:
                caption = ""
            if caption:
                return f"[表情包{count}:{caption}]"

            emotion = self._analyze_sticker_emotion(sticker_path)
            if emotion != "表情":
                return f"[表情包{count}:{emotion}]"
            return f"[表情包{count}]"

        result = STICKER_PATTERN.sub(_repl, message)
        if count:
            logger.debug("消息表情包标记已转换: count=%s", count)
        return result

    def _on_sticker_selected(self, sticker_path: str):
        """自定义表情包选中 - v2.30.7 优化：使用富文本内联显示

        优化内容：
        1. 使用富文本内联显示表情包图片
        2. 可以与文字一起发送
        3. 更直观的视觉效果
        """
        try:
            if not sticker_path:
                return

            # v2.46.x: 去抖 - 避免一次点击/焦点抖动导致重复触发，从而出现“一张变两张”。
            try:
                now = time.time()
                norm = os.path.normcase(os.path.normpath(str(sticker_path)))
                last_path = getattr(self, "_last_sticker_selected_path", None)
                last_at = float(getattr(self, "_last_sticker_selected_at", 0.0) or 0.0)
                if last_path == norm and (now - last_at) < 0.25:
                    logger.debug("忽略重复表情包选择（debounce）: %s", Path(str(sticker_path)).name)
                    return
                self._last_sticker_selected_path = norm
                self._last_sticker_selected_at = now
            except Exception:
                pass

            logger.debug("选中表情包: %s", sticker_path)

            # v2.30.7: 使用增强输入框插入表情包（内联显示）
            self.enhanced_input.insert_sticker(sticker_path)

            logger.debug("表情包已插入到输入框（内联显示）")

        except Exception as e:
            logger.error("插入表情包失败: %s", e, exc_info=True)

    def _on_attach_clicked(self):
        """附件按钮点击 - v2.30.7 优化：使用增强输入框"""
        from PyQt6.QtWidgets import QFileDialog, QMessageBox

        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "选择图片（可多选）", "", "图片文件 (*.png *.jpg *.jpeg *.gif *.bmp *.webp);;所有文件 (*)"
        )

        if file_paths:
            # 检查并添加图片文件
            image_extensions = [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"]
            for file_path in file_paths:
                file_ext = Path(file_path).suffix.lower()
                if file_ext in image_extensions:
                    # v2.30.7: 使用增强输入框添加文件
                    self.enhanced_input.add_file(file_path)
                    # 保持兼容性
                    if file_path not in self.pending_images:
                        self.pending_images.append(file_path)
                else:
                    # 其他文件类型，显示提示
                    QMessageBox.warning(
                        self,
                        "不支持的文件类型",
                        f"文件 {Path(file_path).name} 不是图片格式，已跳过。"
                    )
                    logger.warning("不支持的文件类型: %s", file_path)

    def _add_pending_image(self, image_path: str):
        """添加待发送图片到输入框内的预览区域（兼容旧接口）。"""
        if not image_path:
            return
        try:
            self.enhanced_input.add_file(image_path)
        except Exception:
            pass
        try:
            if image_path not in self.pending_images:
                self.pending_images.append(image_path)
        except Exception:
            pass

    def _remove_pending_image(self, image_path: str, preview_item: QWidget):
        """从待发送列表中移除图片（兼容旧接口）。"""
        _ = preview_item
        try:
            self.enhanced_input.remove_file(image_path)
        except Exception:
            pass
        try:
            if image_path in self.pending_images:
                self.pending_images.remove(image_path)
        except Exception:
            pass

    def _process_multiple_images(self, image_paths: list, user_message: str = ""):
        """处理多张图片的识别 (v2.30.2 新增)"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QRadioButton, QButtonGroup
        from src.gui.material_design_light import MD3_LIGHT_COLORS

        # 创建识别模式选择对话框
        dialog = QDialog(self)
        dialog.setWindowTitle("图片识别")
        dialog.setFixedWidth(400)
        dialog.setStyleSheet(f"""
            QDialog {{
                background: {MD3_LIGHT_COLORS['surface']};
            }}
            QLabel {{
                color: {MD3_LIGHT_COLORS['on_surface']};
                font-size: 14px;
            }}
            QRadioButton {{
                color: {MD3_LIGHT_COLORS['on_surface']};
                font-size: 13px;
                padding: 8px;
            }}
            QPushButton {{
                background: {MD3_LIGHT_COLORS['primary']};
                color: {MD3_LIGHT_COLORS['on_primary']};
                border: none;
                border-radius: 20px;
                padding: 10px 24px;
                font-size: 14px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: {MD3_LIGHT_COLORS['primary_light']};
            }}
            QPushButton#cancelBtn {{
                background: {MD3_LIGHT_COLORS['surface_container']};
                color: {MD3_LIGHT_COLORS['on_surface_variant']};
            }}
            QPushButton#cancelBtn:hover {{
                background: {MD3_LIGHT_COLORS['surface_container_high']};
            }}
        """)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # 标题
        title = QLabel(f"请选择图片识别模式（共{len(image_paths)}张图片）：")
        title.setStyleSheet("font-size: 16px; font-weight: 500;")
        layout.addWidget(title)

        # 识别模式选项
        mode_group = QButtonGroup(dialog)

        auto_radio = QRadioButton("🤖 智能识别（自动判断）")
        auto_radio.setChecked(True)
        mode_group.addButton(auto_radio, 0)
        layout.addWidget(auto_radio)

        describe_radio = QRadioButton("🖼️ 图片描述（描述图片内容）")
        mode_group.addButton(describe_radio, 1)
        layout.addWidget(describe_radio)

        ocr_radio = QRadioButton("📝 文字提取（OCR识别文字）")
        mode_group.addButton(ocr_radio, 2)
        layout.addWidget(ocr_radio)

        both_radio = QRadioButton("🔍 全面分析（描述+OCR）")
        mode_group.addButton(both_radio, 3)
        layout.addWidget(both_radio)

        # 按钮区域
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.setFixedWidth(100)
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        confirm_btn = QPushButton("开始识别")
        confirm_btn.setFixedWidth(120)
        confirm_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(confirm_btn)

        layout.addLayout(button_layout)

        # 显示对话框
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 获取选择的模式
            mode_map = {0: "auto", 1: "describe", 2: "ocr", 3: "both"}
            selected_mode = mode_map[mode_group.checkedId()]

            # 开始批量识别
            self._batch_recognize_images(image_paths, selected_mode, user_message)
        else:
            # 用户取消：不在聊天区插入过程消息（按需求仅终端日志/Toast）
            try:
                show_toast(self, "已取消图片识别", Toast.TYPE_INFO, duration=1500)
            except Exception:
                pass

    def _batch_recognize_images(self, image_paths: list, mode: str, user_message: str = ""):
        """批量识别图片 (v2.30.2 新增)"""
        # 批量识别线程已抽离到 workers 模块（仍使用线程内有限并发）

        # 不在聊天区插入“正在识别/识别完成”等过程消息（按需求仅终端日志）
        logger.info("开始批量识别图片: count=%s, mode=%s", len(image_paths), mode)
        try:
            # 清理可能残留的图片上下文，避免污染本轮识别
            self.current_image_analysis = None
            self.current_image_path = None
        except Exception:
            pass
        try:
            self._reset_stream_render_state()
        except Exception:
            pass
        self._stream_model_done = False
        self._show_typing_indicator()
        self.send_btn.setEnabled(False)

        # 创建并启动线程
        from src.llm.factory import get_vision_llm
        vision_llm = get_vision_llm()
        self.batch_recognition_thread = BatchImageRecognitionThread(
            image_paths, mode, vision_llm
        )
        self.batch_recognition_thread.progress.connect(
            lambda idx, total, result: logger.debug("图片识别进度: %s/%s", idx, total)
        )
        self.batch_recognition_thread.finished.connect(
            lambda results: self._on_batch_recognition_finished(results, user_message)
        )
        self.batch_recognition_thread.error.connect(
            lambda error: self._on_batch_recognition_error(error, image_paths=image_paths, mode=mode, user_message=user_message)
        )
        self.batch_recognition_thread.start()

    def _on_batch_recognition_error(self, error: str, *, image_paths: list, mode: str, user_message: str = "") -> None:
        """批量识别失败：不展示过程消息，仅给出最终回复/提示。"""
        logger.error("批量识别失败: %s", error)
        try:
            self._hide_typing_indicator()
        except Exception:
            pass
        # 以“助手回复”的形式给出失败说明（避免在 GUI 上展示识别过程）
        self._add_message(f"抱歉主人，图片识别失败了：{error} 喵~", is_user=False)
        self._set_send_enabled(True)

    def _on_batch_recognition_finished(self, results: list, user_message: str = ""):
        """批量识别完成回调 (v2.30.2 新增)"""
        # 不在聊天区插入识别结果过程消息；仅用于终端日志
        logger.info("批量识别完成: count=%s", len(results))

        # 合并所有图片分析结果
        first_image_path = results[0].get('image_path') if results else None
        combined_analysis = {
            "mode": results[0].get("mode", "auto"),
            "description": "\n\n".join([f"图片{i+1}: {r.get('description', '')}" for i, r in enumerate(results) if r.get('description')]),
            "text": "\n\n".join([f"图片{i+1}: {r.get('text', '')}" for i, r in enumerate(results) if r.get('text')]),
            "success": all(r.get("success", False) for r in results),
            "image_count": len(results)
        }
        try:
            logger.debug(
                "批量识别汇总: mode=%s, success=%s, desc_chars=%s, text_chars=%s",
                combined_analysis.get("mode"),
                combined_analysis.get("success"),
                len(combined_analysis.get("description") or ""),
                len(combined_analysis.get("text") or ""),
            )
        except Exception:
            pass

        # 如果有用户消息，自动发送给AI
        if user_message or combined_analysis.get("description") or combined_analysis.get("text"):
            # 构建AI消息
            if user_message:
                ai_message = user_message
            else:
                ai_message = "请帮我分析这些图片。"

            # 停止当前正在运行的聊天线程
            if self.current_chat_thread is not None and self.current_chat_thread.isRunning():
                self._cancel_chat_thread(self.current_chat_thread)

            # 重置流式渲染状态（上一轮残留会影响逐字显示/动画）
            try:
                self._reset_stream_render_state()
            except Exception:
                pass
            self._stream_model_done = False

            # 打字指示器：识别阶段已显示，继续沿用
            self._show_typing_indicator()

            # 创建并启动聊天线程
            self.current_chat_thread = ChatThread(
                self.agent,
                self._convert_stickers_to_description(ai_message),
                image_path=first_image_path,
                image_analysis=combined_analysis,
                emit_interval_ms=CHATTHREAD_EMIT_INTERVAL_MS,
                emit_threshold=CHATTHREAD_EMIT_THRESHOLD,
            )
            self._register_live_chat_thread(self.current_chat_thread)
            self.current_chat_thread.chunk_received.connect(self._on_chunk_received)
            self.current_chat_thread.finished.connect(self._on_chat_finished)
            self.current_chat_thread.error.connect(self._on_chat_error)
            self.current_chat_thread.start()

            # 禁用发送按钮
            self.send_btn.setEnabled(False)

    def _recognize_and_send_image(self, image_path: str, user_message: str = ""):
        """识别单张图片并在需要时自动发送给 AI（增强输入框用）。"""
        user_message = (user_message or "").strip()

        if self.agent is None or bool(getattr(self, "_agent_initializing", False)):
            if bool(getattr(self, "_agent_initializing", False)):
                show_toast(self, "AI 正在初始化，请稍候…", Toast.TYPE_INFO, duration=1500)
            else:
                show_toast(self, "AI 未就绪，请检查配置后重试", Toast.TYPE_ERROR, duration=2500)
            self._set_send_enabled(True)
            return

        # 不在聊天区插入识别过程消息；仅终端日志 + 打字指示器
        logger.info("开始识别图片: %s", image_path)
        try:
            self.current_image_analysis = None
            self.current_image_path = None
        except Exception:
            pass
        try:
            self._reset_stream_render_state()
        except Exception:
            pass
        self._stream_model_done = False
        self._show_typing_indicator()
        self.send_btn.setEnabled(False)

        from src.llm.factory import get_vision_llm
        vision_llm = get_vision_llm()

        task = VisionAnalyzeTask(image_path, mode="auto", llm=vision_llm)
        self._register_vision_task(task)

        def _on_result(result: dict, p=image_path, um=user_message) -> None:
            if bool(getattr(self, "_closing", False)):
                return
            self._on_single_image_recognition_finished(result, p, um)

        def _on_error(payload: dict, p=image_path) -> None:
            if bool(getattr(self, "_closing", False)):
                return
            try:
                error_msg = str(payload.get("error") or "")
            except Exception:
                error_msg = ""
            self._on_single_image_recognition_error(error_msg or "图片识别失败", image_path=p)

        task.signals.result_ready.connect(_on_result)
        task.signals.error.connect(_on_error)
        task.signals.finished.connect(lambda t=task: self._cleanup_finished_vision_task(t))

        self.thread_pool.start(task)

    def _on_single_image_recognition_error(self, error: str, *, image_path: str) -> None:
        logger.error("图片识别失败: %s (%s)", error, image_path)
        try:
            self._hide_typing_indicator()
        except Exception:
            pass
        self._add_message(f"抱歉主人，图片识别失败了：{error} 喵~", is_user=False)
        self._set_send_enabled(True)

    def _on_single_image_recognition_finished(self, result: dict, image_path: str, user_message: str = ""):
        """单张图片识别完成回调（增强输入框用）。"""
        logger.info("图片识别完成: %s, mode=%s, success=%s", image_path, result.get("mode"), result.get("success"))
        try:
            logger.debug(
                "图片识别结果: desc_chars=%s, text_chars=%s",
                len(result.get("description") or ""),
                len(result.get("text") or ""),
            )
        except Exception:
            pass

        # 如果有用户消息，自动发送给AI
        if user_message or result.get("description") or result.get("text"):
            ai_message = user_message if user_message else "请帮我分析这张图片。"

            # 停止当前正在运行的聊天线程
            if self.current_chat_thread is not None and self.current_chat_thread.isRunning():
                self._cancel_chat_thread(self.current_chat_thread)

            # 重置流式渲染状态（上一轮残留会影响逐字显示/动画）
            try:
                self._reset_stream_render_state()
            except Exception:
                pass
            self._stream_model_done = False

            # 显示打字指示器
            self._show_typing_indicator()

            self.current_chat_thread = ChatThread(
                self.agent,
                self._convert_stickers_to_description(ai_message),
                image_path=image_path,
                image_analysis=result,
                emit_interval_ms=CHATTHREAD_EMIT_INTERVAL_MS,
                emit_threshold=CHATTHREAD_EMIT_THRESHOLD,
            )
            self._register_live_chat_thread(self.current_chat_thread)
            self.current_chat_thread.chunk_received.connect(self._on_chunk_received)
            self.current_chat_thread.finished.connect(self._on_chat_finished)
            self.current_chat_thread.error.connect(self._on_chat_error)
            self.current_chat_thread.start()
            self.send_btn.setEnabled(False)

    def _handle_image_upload(self, image_path: str):
        """处理图片上传和识别 (v2.30.0 新增，v2.30.2 已弃用，保留用于兼容)"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QRadioButton, QButtonGroup
        from src.gui.material_design_light import MD3_LIGHT_COLORS

        # 显示图片消息气泡
        self._add_image_message(image_path, is_user=True)
        logger.debug("发送图片: %s", image_path)

        # 创建识别模式选择对话框
        dialog = QDialog(self)
        dialog.setWindowTitle("图片识别")
        dialog.setFixedWidth(400)
        dialog.setStyleSheet(f"""
            QDialog {{
                background: {MD3_LIGHT_COLORS['surface']};
            }}
            QLabel {{
                color: {MD3_LIGHT_COLORS['on_surface']};
                font-size: 14px;
            }}
            QRadioButton {{
                color: {MD3_LIGHT_COLORS['on_surface']};
                font-size: 13px;
                padding: 8px;
            }}
            QPushButton {{
                background: {MD3_LIGHT_COLORS['primary']};
                color: {MD3_LIGHT_COLORS['on_primary']};
                border: none;
                border-radius: 20px;
                padding: 10px 24px;
                font-size: 14px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: {MD3_LIGHT_COLORS['primary_light']};
            }}
            QPushButton#cancelBtn {{
                background: {MD3_LIGHT_COLORS['surface_container']};
                color: {MD3_LIGHT_COLORS['on_surface_variant']};
            }}
            QPushButton#cancelBtn:hover {{
                background: {MD3_LIGHT_COLORS['surface_container_high']};
            }}
        """)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # 标题
        title = QLabel("请选择图片识别模式：")
        title.setStyleSheet("font-size: 16px; font-weight: 500;")
        layout.addWidget(title)

        # 识别模式选项
        mode_group = QButtonGroup(dialog)

        auto_radio = QRadioButton("🤖 智能识别（自动判断）")
        auto_radio.setChecked(True)
        mode_group.addButton(auto_radio, 0)
        layout.addWidget(auto_radio)

        describe_radio = QRadioButton("🖼️ 图片描述（描述图片内容）")
        mode_group.addButton(describe_radio, 1)
        layout.addWidget(describe_radio)

        ocr_radio = QRadioButton("📝 文字提取（OCR识别文字）")
        mode_group.addButton(ocr_radio, 2)
        layout.addWidget(ocr_radio)

        both_radio = QRadioButton("🔍 全面分析（描述+OCR）")
        mode_group.addButton(both_radio, 3)
        layout.addWidget(both_radio)

        # 按钮区域
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.setFixedWidth(100)
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        confirm_btn = QPushButton("开始识别")
        confirm_btn.setFixedWidth(120)
        confirm_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(confirm_btn)

        layout.addLayout(button_layout)

        # 显示对话框
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 获取选择的模式
            mode_map = {0: "auto", 1: "describe", 2: "ocr", 3: "both"}
            selected_mode = mode_map[mode_group.checkedId()]

            # 开始识别
            self._process_image_recognition(image_path, selected_mode)

    def _process_image_recognition(self, image_path: str, mode: str):
        """处理图片识别 (v2.30.0 新增)"""
        # 显示处理中的消息
        logger.info("开始图片识别(手动模式): %s, mode=%s", image_path, mode)
        try:
            self._reset_stream_render_state()
        except Exception:
            pass
        self._stream_model_done = False
        self._show_typing_indicator()
        self.send_btn.setEnabled(False)

        from src.llm.factory import get_vision_llm
        vision_llm = get_vision_llm()

        task = VisionAnalyzeTask(image_path, mode=mode, llm=vision_llm)
        self._register_vision_task(task)

        def _on_result(result: dict, p=image_path) -> None:
            if bool(getattr(self, "_closing", False)):
                return
            self._on_image_recognition_finished(result, p)

        def _on_error(payload: dict, p=image_path) -> None:
            if bool(getattr(self, "_closing", False)):
                return
            try:
                error_msg = str(payload.get("error") or "")
            except Exception:
                error_msg = ""
            self._on_single_image_recognition_error(error_msg or "图片识别失败", image_path=p)

        task.signals.result_ready.connect(_on_result)
        task.signals.error.connect(_on_error)
        task.signals.finished.connect(lambda t=task: self._cleanup_finished_vision_task(t))

        self.thread_pool.start(task)

    def _on_image_recognition_finished(self, result: dict, image_path: str):
        """图片识别完成回调 (v2.30.0 新增)"""
        logger.info("图片识别完成(手动模式): %s, mode=%s, success=%s", image_path, result.get("mode"), result.get("success"))
        # 直接触发一次 AI 回复：不在聊天区展示识别过程/识别结果明细
        ai_message = "请帮我分析这张图片。"

        # 停止当前正在运行的聊天线程
        if self.current_chat_thread is not None and self.current_chat_thread.isRunning():
            self._cancel_chat_thread(self.current_chat_thread)

        # 重置流式渲染状态（上一轮残留会影响逐字显示/动画）
        try:
            self._reset_stream_render_state()
        except Exception:
            pass
        self._stream_model_done = False

        # 显示打字指示器
        self._show_typing_indicator()

        # 创建并启动聊天线程（传递图片上下文）
        self.current_chat_thread = ChatThread(
            self.agent,
            self._convert_stickers_to_description(ai_message),
            image_path=image_path,
            image_analysis=result,
            emit_interval_ms=CHATTHREAD_EMIT_INTERVAL_MS,
            emit_threshold=CHATTHREAD_EMIT_THRESHOLD,
        )
        self._register_live_chat_thread(self.current_chat_thread)
        self.current_chat_thread.chunk_received.connect(self._on_chunk_received)
        self.current_chat_thread.finished.connect(self._on_chat_finished)
        self.current_chat_thread.error.connect(self._on_chat_error)
        self.current_chat_thread.start()
        self.send_btn.setEnabled(False)

    def _on_chat_clicked(self):
        """聊天按钮点击 - 返回聊天界面"""
        # 切换回聊天区域
        self.stacked_widget.setCurrentIndex(0)
        # 显示提示
        show_toast(self, "已返回聊天界面", Toast.TYPE_INFO, duration=1500)

    def _on_settings_clicked(self):
        """设置按钮点击"""
        # 懒加载设置面板：首次打开时才创建，减少启动时的 UI 构建开销
        if self.settings_panel is None:
            from .roleplay_settings_panel import SettingsPanel

            self.settings_panel = SettingsPanel(agent=self.agent)
            self.settings_panel.back_clicked.connect(self._on_settings_back)
            self.settings_panel.settings_saved.connect(self._on_settings_saved)
            self.stacked_widget.addWidget(self.settings_panel)

        # 切换到设置面板
        self.stacked_widget.setCurrentWidget(self.settings_panel)
        # 折叠联系人面板
        if self.contacts_panel.is_expanded():
            self.contacts_panel.collapse()

    def _on_settings_back(self):
        """设置面板返回按钮点击"""
        # 切换回聊天区域
        self.stacked_widget.setCurrentIndex(0)

    def _on_contacts_clicked(self):
        """联系人按钮点击 - 切换展开/折叠"""
        # 切换联系人面板
        self.contacts_panel.toggle()

    def _show_header_menu(self) -> None:
        """显示头部“更多”菜单。"""
        from PyQt6.QtWidgets import QMenu

        anchor = getattr(self, "more_btn", None)
        if anchor is None:
            return

        menu = QMenu(self)
        menu_selected = qss_rgba(MD3_ENHANCED_COLORS["primary"], 0.08)
        menu.setStyleSheet(
            f"""
            QMenu {{
                background: {MD3_ENHANCED_COLORS['surface_container']};
                border: 1px solid {MD3_ENHANCED_COLORS['outline_variant']};
                border-radius: {MD3_ENHANCED_RADIUS['xl']};
                padding: 6px;
            }}
            QMenu::item {{
                padding: 8px 12px;
                border-radius: {MD3_ENHANCED_RADIUS['lg']};
                color: {MD3_ENHANCED_COLORS['on_surface']};
            }}
            QMenu::item:selected {{
                background: {menu_selected};
            }}
        """
        )

        settings_action = menu.addAction("设置")
        refresh_action = menu.addAction("刷新当前对话")
        clear_action = menu.addAction("清空当前聊天记录…")
        logout_action = menu.addAction("退出登录")

        action = menu.exec(anchor.mapToGlobal(QPoint(0, anchor.height())))
        if action is None:
            return
        if action == settings_action:
            self._on_settings_clicked()
        elif action == refresh_action:
            self._refresh_current_chat()
        elif action == clear_action:
            self._confirm_and_clear_current_chat_history()
        elif action == logout_action:
            self._on_logout_clicked()

    def _refresh_current_chat(self) -> None:
        """刷新当前对话视图（清空 UI 并重新加载最近消息）。"""
        contact = getattr(self, "current_contact", None)
        if not contact:
            return

        self.scroll_area.setUpdatesEnabled(False)
        self._clear_messages()
        self.scroll_area.setUpdatesEnabled(True)

        if user_session.is_logged_in():
            self._load_chat_history(contact)
            show_toast(self, "正在刷新聊天记录…", Toast.TYPE_INFO, duration=1200)
        else:
            show_toast(self, "未登录，无法加载聊天记录", Toast.TYPE_WARNING, duration=1500)

    def _confirm_and_clear_current_chat_history(self) -> None:
        """确认并清空当前联系人的聊天记录（不可撤销）。"""
        contact = getattr(self, "current_contact", None)
        if not contact:
            return

        if not user_session.is_logged_in():
            show_toast(self, "未登录，无法清空聊天记录", Toast.TYPE_WARNING, duration=1500)
            return

        from PyQt6.QtWidgets import QMessageBox

        answer = QMessageBox.question(
            self,
            "清空聊天记录",
            f"确定要清空与「{contact}」的聊天记录吗？\n该操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            ok = bool(user_session.clear_chat_history(contact))
        except Exception as exc:
            logger.error("清空聊天记录失败: %s", exc, exc_info=True)
            ok = False

        if not ok:
            show_toast(self, "清空失败，请稍后重试", Toast.TYPE_ERROR, duration=1800)
            return

        # 同步 UI 缓存状态（否则分页 offset/keyset 会基于旧计数出现错位）
        try:
            if hasattr(self, "_message_cache"):
                self._message_cache[contact] = {}
            if hasattr(self, "_loaded_message_count"):
                self._loaded_message_count[contact] = 0
            if hasattr(self, "_total_message_count"):
                self._total_message_count[contact] = 0
            if hasattr(self, "_oldest_message_id"):
                self._oldest_message_id[contact] = None
        except Exception:
            pass

        self.scroll_area.setUpdatesEnabled(False)
        self._clear_messages()
        self.scroll_area.setUpdatesEnabled(True)
        show_toast(self, "已清空聊天记录", Toast.TYPE_SUCCESS, duration=1500)

    def _next_history_request_id(self) -> int:
        """生成递增的历史加载请求 ID，用于丢弃过期结果。"""
        try:
            self._history_load_seq += 1
        except Exception:
            self._history_load_seq = int(getattr(self, "_history_load_seq", 0)) + 1
        return int(self._history_load_seq)

    def _register_live_history_thread(self, thread: Optional[ChatHistoryLoaderThread]) -> None:
        """保留历史加载线程引用，避免 QThread 被 GC 导致崩溃。"""
        if thread is None:
            return
        try:
            if thread not in self._live_history_threads:
                self._live_history_threads.append(thread)
        except Exception:
            self._live_history_threads.append(thread)

    def _cleanup_finished_history_thread(self, thread: Optional[ChatHistoryLoaderThread]) -> None:
        """清理已结束的历史加载线程。"""
        if thread is None:
            return
        try:
            if thread is getattr(self, "_active_initial_history_thread", None):
                self._active_initial_history_thread = None
        except Exception:
            pass
        try:
            if thread is getattr(self, "_active_more_history_thread", None):
                self._active_more_history_thread = None
        except Exception:
            pass
        try:
            try:
                thread.result_ready.disconnect()
                thread.error.disconnect()
                thread.finished.disconnect()
            except TypeError:
                pass
        except Exception:
            pass

        try:
            thread.requestInterruption()
        except Exception:
            pass

        try:
            thread.deleteLater()
        except Exception:
            pass

        try:
            if thread in self._live_history_threads:
                self._live_history_threads.remove(thread)
        except Exception:
            pass

    def _cancel_history_thread(self, thread: Optional[ChatHistoryLoaderThread]) -> None:
        if thread is None:
            return
        self._register_live_history_thread(thread)
        try:
            if thread.isRunning():
                try:
                    thread.requestInterruption()
                except Exception:
                    pass
        except Exception:
            pass

    def _show_history_loading_state(self, contact_name: str) -> None:
        """显示历史加载占位，避免切换联系人时界面长时间空白。"""
        self._remove_history_loading_state()
        try:
            from .loading_states import CircularProgress

            container = QWidget()
            layout = QVBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            layout.addStretch(1)

            progress = CircularProgress(size=28)

            title = QLabel("加载中…")
            title.setStyleSheet(
                f"""
                QLabel {{
                    color: {MD3_ENHANCED_COLORS['on_surface']};
                    {get_typography_css('title_medium')}
                    background: transparent;
                    font-weight: 600;
                }}
                """
            )

            subtitle = QLabel(f"正在加载 {contact_name} 的聊天记录")
            subtitle.setStyleSheet(
                f"""
                QLabel {{
                    color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                    {get_typography_css('body_medium')}
                    background: transparent;
                }}
                """
            )
            subtitle.setWordWrap(True)

            layout.addWidget(progress, alignment=Qt.AlignmentFlag.AlignHCenter)
            layout.addSpacing(12)
            layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignHCenter)
            layout.addSpacing(6)
            layout.addWidget(subtitle, alignment=Qt.AlignmentFlag.AlignHCenter)
            layout.addStretch(1)
            self._history_loading_widget = container
            self.messages_layout.insertWidget(0, container)
        except Exception:
            self._history_loading_widget = None

    def _remove_history_loading_state(self) -> None:
        widget = getattr(self, "_history_loading_widget", None)
        self._history_loading_widget = None
        if widget is None:
            return
        try:
            if hasattr(self, "messages_layout") and self.messages_layout is not None:
                self.messages_layout.removeWidget(widget)
        except Exception:
            pass
        try:
            widget.deleteLater()
        except Exception:
            pass

    def _on_history_load_result(self, payload: object) -> None:
        """接收后台线程加载结果并在 UI 线程应用。"""
        if not isinstance(payload, dict):
            return

        mode = payload.get("mode")
        contact_name = payload.get("contact_name")
        request_id = int(payload.get("request_id") or 0)
        if not contact_name:
            return

        if mode == "initial":
            if request_id != int(getattr(self, "_active_initial_history_request_id", 0)):
                return
            if contact_name != getattr(self, "current_contact", None):
                return

            total_count = int(payload.get("total_count") or 0)
            messages = payload.get("messages") or []
            if not isinstance(messages, list):
                messages = []
            self._apply_loaded_chat_history(contact_name, total_count, messages)
            return

        if mode == "more":
            if request_id != int(getattr(self, "_active_more_history_request_id", 0)):
                return
            if contact_name != getattr(self, "current_contact", None):
                # 联系人已切换：释放加载锁，但丢弃结果
                try:
                    self._pending_history_load_state.pop(request_id, None)
                except Exception:
                    pass
                self._is_loading_more = False
                return

            state = self._pending_history_load_state.pop(request_id, {})
            old_value = int(state.get("old_value", 0))
            old_max = int(state.get("old_max", 0))
            prev_loaded = int(state.get("loaded_count", 0))
            total_count = int(state.get("total_count", 0))

            messages = payload.get("messages") or []
            if not isinstance(messages, list):
                messages = []
            self._apply_loaded_more_history(
                contact_name,
                messages,
                old_value=old_value,
                old_max=old_max,
                prev_loaded_count=prev_loaded,
                total_count=total_count,
            )

    def _on_history_load_error(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return

        mode = payload.get("mode")
        contact_name = payload.get("contact_name")
        request_id = int(payload.get("request_id") or 0)
        error_text = payload.get("error") or "加载失败"

        if mode == "initial":
            if request_id != int(getattr(self, "_active_initial_history_request_id", 0)):
                return
            if contact_name != getattr(self, "current_contact", None):
                return
            self._remove_history_loading_state()
            show_toast(self, f"加载历史失败：{error_text}", Toast.TYPE_ERROR, duration=2500)
            return

        if mode == "more":
            if request_id != int(getattr(self, "_active_more_history_request_id", 0)):
                return
            try:
                self._pending_history_load_state.pop(request_id, None)
            except Exception:
                pass
            self._is_loading_more = False
            show_toast(self, f"加载更多失败：{error_text}", Toast.TYPE_ERROR, duration=2500)

    def _apply_loaded_chat_history(
        self,
        contact_name: str,
        total_count: int,
        messages: list[dict],
    ) -> None:
        """将后台加载到的聊天历史应用到界面（批量插入、禁用动画）。"""
        scroll_widget = self.scroll_area.widget()
        scrollbar = self.scroll_area.verticalScrollBar()
        old_bulk_loading = getattr(self, "_bulk_loading_messages", False)
        old_scrollbar_signals = False
        try:
            self._remove_history_loading_state()

            # v2.30.12: 更新消息总数（用于判断是否还有更多消息）
            self._total_message_count[contact_name] = int(total_count)

            # 批量插入：禁用滚动区域更新，避免闪烁/抖动
            self._bulk_loading_messages = True
            try:
                old_scrollbar_signals = scrollbar.blockSignals(True)
            except Exception:
                old_scrollbar_signals = False
            self.scroll_area.setUpdatesEnabled(False)
            if scroll_widget is not None:
                scroll_widget.setUpdatesEnabled(False)

            if not messages:
                self._add_message(
                    f"开始与 {contact_name} 的对话吧！",
                    is_user=False,
                    save_to_db=False,
                    with_animation=False,
                )
            else:
                # 缓存加载的消息（使用消息ID去重）
                contact_cache = self._message_cache.setdefault(contact_name, {})
                for msg in messages:
                    msg_id = msg.get("id")
                    if msg_id:
                        contact_cache[msg_id] = msg

                # 记录最早消息 id，用于后续向上翻页
                oldest = messages[0].get("id") if messages else None
                try:
                    self._oldest_message_id[contact_name] = oldest
                except Exception:
                    pass

                for msg in messages:
                    self._add_message(
                        msg.get("content", ""),
                        is_user=(msg.get("role") == "user"),
                        save_to_db=False,
                        with_animation=False,
                    )

            # 更新已加载消息数量
            self._loaded_message_count[contact_name] = len(messages)

            # 重新启用更新并强制刷新布局
            if scroll_widget is not None:
                scroll_widget.setUpdatesEnabled(True)
            self.scroll_area.setUpdatesEnabled(True)
            self.messages_layout.update()
            self._schedule_messages_geometry_update()
            self._ensure_scroll_to_bottom()

            if total_count > len(messages):
                logger.debug("还有 %s 条历史消息未加载", total_count - len(messages))

            logger.info(
                "已加载 %s/%s 条历史消息（联系人: %s）",
                len(messages),
                total_count,
                contact_name,
            )
        except Exception as e:
            from src.utils.exceptions import handle_exception

            handle_exception(e, logger, "应用聊天历史失败")
        finally:
            # 双保险：避免异常/提前返回导致界面不更新
            if scroll_widget is not None:
                scroll_widget.setUpdatesEnabled(True)
            self.scroll_area.setUpdatesEnabled(True)
            try:
                scrollbar.blockSignals(old_scrollbar_signals)
            except Exception:
                pass
            self._bulk_loading_messages = old_bulk_loading

    def _apply_loaded_more_history(
        self,
        contact_name: str,
        messages: list[dict],
        *,
        old_value: int,
        old_max: int,
        prev_loaded_count: int,
        total_count: int,
    ) -> None:
        """将后台加载到的“更多历史”插入到顶部，并恢复滚动位置。"""
        try:
            if not messages:
                show_toast(self, "没有更多历史消息", Toast.TYPE_INFO, duration=1500)
                return

            # 缓存新加载的消息
            contact_cache = self._message_cache.setdefault(contact_name, {})
            for msg in messages:
                msg_id = msg.get("id")
                if msg_id and msg_id not in contact_cache:
                    contact_cache[msg_id] = msg

            # 更新“最早消息 id”，用于下一次 keyset 翻页
            new_oldest = messages[0].get("id") if messages else None
            if new_oldest:
                try:
                    self._oldest_message_id[contact_name] = new_oldest
                except Exception:
                    pass

            scroll_widget = self.scroll_area.widget()
            scrollbar = self.scroll_area.verticalScrollBar()
            old_bulk_loading = getattr(self, "_bulk_loading_messages", False)
            old_scrollbar_signals = False
            try:
                self._bulk_loading_messages = True
                try:
                    old_scrollbar_signals = scrollbar.blockSignals(True)
                except Exception:
                    old_scrollbar_signals = False
                self.scroll_area.setUpdatesEnabled(False)
                if scroll_widget is not None:
                    scroll_widget.setUpdatesEnabled(False)

                for msg in reversed(messages):  # 反转以保持时间顺序
                    self._insert_message_at_top(
                        msg.get("content", ""),
                        is_user=(msg.get("role") == "user"),
                        with_animation=False,
                    )

                self._loaded_message_count[contact_name] = prev_loaded_count + len(messages)
            finally:
                if scroll_widget is not None:
                    scroll_widget.setUpdatesEnabled(True)
                self.scroll_area.setUpdatesEnabled(True)
                try:
                    scrollbar.blockSignals(old_scrollbar_signals)
                except Exception:
                    pass
                self._bulk_loading_messages = old_bulk_loading

            self.messages_layout.update()
            self._schedule_messages_geometry_update()
            QTimer.singleShot(100, lambda: self._restore_scroll_position(old_value, old_max))

            logger.info(
                "已加载 %s/%s 条历史消息",
                self._loaded_message_count.get(contact_name, 0),
                total_count,
            )
            show_toast(
                self,
                f"已加载更多历史消息 ({self._loaded_message_count.get(contact_name, 0)}/{total_count})",
                Toast.TYPE_SUCCESS,
                duration=1500,
            )
        finally:
            self._is_loading_more = False

    def _on_contact_selected(self, contact_name: str):
        """联系人选中 - 切换到该联系人的消息容器 - v2.21.3 优化：流畅切换，无闪烁"""

        # 停止当前正在运行的聊天线程
        if self.current_chat_thread is not None and self.current_chat_thread.isRunning():
            logger.info("停止当前聊天线程...")
            self._cancel_chat_thread(self.current_chat_thread)
            self.current_chat_thread = None

        # 清理打字指示器
        if hasattr(self, "typing_indicator") and self.typing_indicator is not None:
            self._hide_typing_indicator()

        # 清理流式消息气泡
        if self.current_streaming_bubble is not None:
            if hasattr(self.current_streaming_bubble, "cleanup"):
                self.current_streaming_bubble.cleanup()
            self.current_streaming_bubble = None
        try:
            self._reset_stream_render_state()
        except Exception:
            pass

        # 保存当前联系人的聊天历史
        if self.current_contact and user_session.is_logged_in():
            self._save_current_chat_history()

        # 切换联系人
        self.current_contact = contact_name
        logger.debug("选中联系人: %s", contact_name)

        # v2.21.3 优化：禁用滚动区域更新，避免闪烁
        self.scroll_area.setUpdatesEnabled(False)

        # 清空当前消息
        self._clear_messages()
        # 先恢复更新：历史查询移至后台线程后，不应长时间保持禁用（避免界面空白/无响应）
        self.scroll_area.setUpdatesEnabled(True)

        # 加载该联系人的聊天历史（后台线程查询，UI 线程批量插入）
        if user_session.is_logged_in():
            self._load_chat_history(contact_name)

        # 更新头部显示
        self.name_label.setText(contact_name)

        # 重新启用发送按钮
        self._set_send_enabled(True)

        # 显示提示
        show_toast(self, f"已切换到 {contact_name} 的对话", Toast.TYPE_INFO, duration=2000)

    def _load_chat_history(self, contact_name: str, limit: int = 20):
        """加载聊天历史 - v2.30.12 优化：分页加载，缓存机制，性能提升

        Args:
            contact_name: 联系人名称
            limit: 加载消息数量（默认20条，避免一次加载过多）
        """
        if not user_session.is_logged_in():
            return

        try:
            logger.debug("开始异步加载聊天历史: %s (limit=%s)", contact_name, limit)

            # 初始化消息缓存和分页状态（防御性：兼容旧对象）
            if not hasattr(self, "_message_cache"):
                self._message_cache = {}
            if not hasattr(self, "_loaded_message_count"):
                self._loaded_message_count = {}
            if not hasattr(self, "_total_message_count"):
                self._total_message_count = {}
            if not hasattr(self, "_oldest_message_id"):
                # {contact_name: oldest_loaded_msg_id}; 用于 keyset pagination，避免大 OFFSET 退化
                self._oldest_message_id = {}

            # 重置当前联系人的缓存与计数（结果返回后再写入真实 total_count）
            self._message_cache[contact_name] = {}
            self._loaded_message_count[contact_name] = 0
            self._total_message_count[contact_name] = 0
            self._oldest_message_id[contact_name] = None

            self._show_history_loading_state(contact_name)

            request_id = self._next_history_request_id()
            self._active_initial_history_request_id = request_id

            # 快速切换联系人时，取消上一轮历史加载（避免并发 DB 查询拖慢 UI）
            self._cancel_history_thread(getattr(self, "_active_initial_history_thread", None))

            thread = ChatHistoryLoaderThread(
                ChatHistoryLoadRequest(
                    request_id=request_id,
                    mode="initial",
                    contact_name=contact_name,
                    limit=limit,
                    before_id=None,
                    offset=0,
                    include_total=True,
                )
            )
            thread.result_ready.connect(self._on_history_load_result)
            thread.error.connect(self._on_history_load_error)
            thread.finished.connect(lambda thr=thread: self._cleanup_finished_history_thread(thr))
            self._register_live_history_thread(thread)
            self._active_initial_history_thread = thread
            thread.start()
        except Exception as e:
            from src.utils.exceptions import handle_exception

            handle_exception(e, logger, "加载聊天历史失败")
            self._remove_history_loading_state()

    def _load_more_history(self, contact_name: str, limit: int = 20):
        """加载更多历史消息 (v2.30.12: 新增分页加载功能)

        Args:
            contact_name: 联系人名称
            limit: 每次加载的消息数量
        """
        if not user_session.is_logged_in():
            self._is_loading_more = False
            return

        try:
            if not hasattr(self, "_loaded_message_count"):
                logger.warning("未初始化消息计数器")
                self._is_loading_more = False
                return

            loaded_count = int(self._loaded_message_count.get(contact_name, 0))
            total_count = int(self._total_message_count.get(contact_name, 0))

            if loaded_count >= total_count:
                logger.info("已加载全部 %s 条消息", total_count)
                show_toast(self, "已加载全部历史消息", Toast.TYPE_INFO, duration=2000)
                self._is_loading_more = False
                return

            remaining = total_count - loaded_count
            load_count = min(int(limit), int(remaining))

            before_id = None
            try:
                before_id = getattr(self, "_oldest_message_id", {}).get(contact_name)
            except Exception:
                before_id = None

            logger.debug(
                "异步加载更多历史: loaded=%s, limit=%s, before_id=%s",
                loaded_count,
                load_count,
                before_id,
            )

            scrollbar = self.scroll_area.verticalScrollBar()
            old_value = int(scrollbar.value())
            old_max = int(scrollbar.maximum())

            request_id = self._next_history_request_id()
            self._active_more_history_request_id = request_id
            self._pending_history_load_state[request_id] = {
                "old_value": old_value,
                "old_max": old_max,
                "loaded_count": loaded_count,
                "total_count": total_count,
            }

            self._cancel_history_thread(getattr(self, "_active_more_history_thread", None))

            thread = ChatHistoryLoaderThread(
                ChatHistoryLoadRequest(
                    request_id=request_id,
                    mode="more",
                    contact_name=contact_name,
                    limit=load_count,
                    before_id=int(before_id) if before_id else None,
                    offset=loaded_count,
                    include_total=False,
                )
            )
            thread.result_ready.connect(self._on_history_load_result)
            thread.error.connect(self._on_history_load_error)
            thread.finished.connect(lambda thr=thread: self._cleanup_finished_history_thread(thr))
            self._register_live_history_thread(thread)
            self._active_more_history_thread = thread
            thread.start()
        except Exception as e:
            from src.utils.exceptions import handle_exception

            handle_exception(e, logger, "加载更多历史消息失败")
            self._is_loading_more = False

    def _insert_message_at_top(self, message: str, is_user: bool, with_animation: bool = False):
        """在顶部插入消息 (v2.30.13: 修复导入错误)

        Args:
            message: 消息内容
            is_user: 是否为用户消息
            with_animation: 是否显示动画
        """
        bulk_loading = bool(getattr(self, "_bulk_loading_messages", False))
        enable_entry_animation = bool(with_animation and GUI_ANIMATIONS_ENABLED)

        message_stripped = message.strip()
        sticker_only = STICKER_PATTERN.fullmatch(message_stripped)
        image_only = IMAGE_PATTERN.fullmatch(message_stripped)
        if sticker_only:
            sticker_path = sticker_only.group(1)
            bubble = LightImageMessageBubble(
                sticker_path,
                is_user,
                is_sticker=True,
                with_animation=enable_entry_animation,
                enable_shadow=with_animation,
                autoplay=not bulk_loading,
            )
            self._register_animated_image_bubble(bubble)
            self.messages_layout.insertWidget(0, bubble)
            if not bulk_loading:
                self._schedule_animated_image_budget()
            return

        if image_only:
            image_path = image_only.group(1)
            bubble = LightImageMessageBubble(
                image_path,
                is_user,
                is_sticker=False,
                with_animation=enable_entry_animation,
                enable_shadow=with_animation,
                autoplay=not bulk_loading,
            )
            self._register_animated_image_bubble(bubble)
            self.messages_layout.insertWidget(0, bubble)
            if not bulk_loading:
                self._schedule_animated_image_budget()
            return

        if STICKER_PATTERN.search(message):
            from PyQt6.QtWidgets import QWidget, QHBoxLayout

            container = QWidget()
            layout = QHBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)

            parts = STICKER_PATTERN.split(message)
            widgets = []
            for i, part in enumerate(parts):
                if not part:
                    continue
                if i % 2 == 0:
                    if part.strip():
                        text_bubble = LightMessageBubble(part, is_user, enable_shadow=with_animation)
                        if enable_entry_animation:
                            text_bubble.show_with_animation()
                        widgets.append(text_bubble)
                else:
                    sticker_bubble = LightImageMessageBubble(
                        part,
                        is_user,
                        is_sticker=True,
                        with_animation=enable_entry_animation,
                        enable_shadow=with_animation,
                        autoplay=not bulk_loading,
                    )
                    self._register_animated_image_bubble(sticker_bubble)
                    widgets.append(sticker_bubble)

            container.setUpdatesEnabled(False)
            for widget in widgets:
                layout.addWidget(widget)
            layout.addStretch()
            container.setUpdatesEnabled(True)

            self.messages_layout.insertWidget(0, container)
            if not bulk_loading:
                self._schedule_animated_image_budget()
            return

        # 纯文本消息
        bubble = LightMessageBubble(message, is_user, enable_shadow=with_animation)
        self.messages_layout.insertWidget(0, bubble)
        if enable_entry_animation:
            bubble.show_with_animation()

    def _restore_scroll_position(self, old_value: int, old_max: int):
        """恢复滚动位置 (v2.30.12: 新增，避免加载历史消息时跳动)

        Args:
            old_value: 旧的滚动值
            old_max: 旧的最大滚动值
        """
        scrollbar = self.scroll_area.verticalScrollBar()
        new_max = scrollbar.maximum()

        # 计算新的滚动位置（保持相对位置）
        if old_max > 0:
            new_value = old_value + (new_max - old_max)
        else:
            new_value = new_max

        scrollbar.setValue(new_value)

    def _on_scroll_changed(self, value: int):
        """滚动事件处理 (v2.30.12: 新增，实现滚动到顶部自动加载更多)

        Args:
            value: 当前滚动值
        """
        # 自动滚动锁：只有在接近底部时才允许自动滚动，避免用户上滑时被强制拉回
        try:
            scrollbar = self.scroll_area.verticalScrollBar()
            prev_auto = bool(getattr(self, "_auto_scroll_enabled", True))
            self._auto_scroll_enabled = (scrollbar.maximum() - value) <= AUTO_SCROLL_BOTTOM_THRESHOLD_PX
            # 当用户从“上滑查看历史”回到底部时，裁剪旧消息以恢复滚动性能
            if self._auto_scroll_enabled and not prev_auto:
                self._schedule_trim_rendered_messages(force=False)
        except Exception:
            self._auto_scroll_enabled = True

        self._schedule_animated_image_budget()

        # 如果正在加载，跳过
        if self._is_loading_more:
            return

        # 如果滚动到顶部（阈值：距离顶部小于100像素）
        if value < 100:
            # 检查是否还有更多消息
            if not hasattr(self, '_loaded_message_count') or not self.current_contact:
                return

            loaded_count = self._loaded_message_count.get(self.current_contact, 0)
            total_count = self._total_message_count.get(self.current_contact, 0)

            if loaded_count < total_count:
                logger.debug("滚动到顶部，自动加载更多历史消息")
                self._is_loading_more = True

                # 延迟加载，避免频繁触发
                QTimer.singleShot(200, lambda: self._load_more_with_reset())

    def _on_scroll_range_changed(self, _min: int, _max: int) -> None:
        """滚动范围变化（内容高度变化）时，按需跟随到底部。

        典型场景：流式输出导致气泡持续增高/换行；新消息插入；窗口尺寸变化。
        """
        self._schedule_animated_image_budget()
        if not getattr(self, "_auto_scroll_enabled", True):
            return

        # 优先走批量滚动（更省资源），否则走轻量调度（带去抖）
        if getattr(self, "performance_optimizer", None) is not None:
            try:
                self.performance_optimizer.schedule_scroll()
                return
            except Exception:
                pass

        self._schedule_stream_scroll()

    def _load_more_with_reset(self):
        """加载更多消息（异步查询 + UI 批量插入）。"""
        if not self.current_contact:
            self._is_loading_more = False
            return
        self._load_more_history(self.current_contact, limit=20)

    def _save_current_chat_history(self):
        """保存当前聊天历史（在切换联系人时调用）"""
        # 注意：消息已经在发送时实时保存到数据库，这里不需要额外操作
        pass

    def _deferred_cleanup_widget_tree(self, root: QWidget, *, budget_ms: int = 8) -> None:
        """分帧清理 widget 树，避免一次性遍历大量消息导致 UI 卡顿。"""
        try:
            children = [w for w in root.findChildren(QWidget) if w is not root]
        except Exception:
            try:
                root.deleteLater()
            except Exception:
                pass
            return

        # 反向遍历更符合“先清理叶子节点”的释放顺序
        pending = list(reversed(children))

        def step() -> None:
            try:
                start = time.perf_counter()
                while pending and (time.perf_counter() - start) * 1000.0 < float(budget_ms):
                    w = pending.pop()
                    try:
                        cleanup = getattr(w, "cleanup", None)
                        if callable(cleanup):
                            cleanup()
                    except Exception:
                        pass
            finally:
                if pending:
                    QTimer.singleShot(0, step)
                else:
                    try:
                        root.deleteLater()
                    except Exception:
                        pass

        QTimer.singleShot(0, step)

    def _fast_reset_messages_column(self) -> None:
        """快速重置消息列容器，避免大量 takeAt()/deleteLater() 造成卡顿/未响应。"""
        old_widget = getattr(self, "messages_widget", None)
        outer = getattr(self, "messages_outer_widget", None)
        if old_widget is None or outer is None:
            return

        try:
            old_widget.setParent(None)
            old_widget.hide()
        except Exception:
            pass

        # 创建新的消息列容器（保持与初始化一致的样式与边距）
        new_widget = QWidget()
        try:
            new_widget.setObjectName("messagesColumn")
        except Exception:
            pass
        try:
            max_width = int(getattr(self, "_messages_column_max_width", 820))
            new_widget.setMaximumWidth(max_width)
        except Exception:
            pass

        new_layout = QVBoxLayout(new_widget)
        try:
            new_layout.setContentsMargins(
                0, CharacterStatusIsland.COLLAPSED_HEIGHT + 20, 0, 16
            )
        except Exception:
            new_layout.setContentsMargins(0, 20, 0, 16)
        new_layout.setSpacing(8)
        new_layout.addStretch()

        outer_layout = outer.layout()
        if outer_layout is not None:
            try:
                outer_layout.removeWidget(old_widget)
            except Exception:
                pass
            try:
                # 结构是 stretch - widget - stretch；尽量插回中间位置
                outer_layout.insertWidget(1, new_widget, 0)
            except Exception:
                try:
                    outer_layout.addWidget(new_widget, 0)
                except Exception:
                    pass

        self.messages_widget = new_widget
        self.messages_layout = new_layout
        self._history_loading_widget = None

        # 延迟清理旧树，避免阻塞主线程
        self._deferred_cleanup_widget_tree(old_widget)

    def _clear_messages(self):
        """清空消息区域 - v2.19.2 修复版：正确清理资源"""
        # 快速路径：大量历史消息时，逐个 takeAt() 容易导致窗口“未响应”
        try:
            message_count = max(0, int(self.messages_layout.count()) - 1)
        except Exception:
            message_count = 0

        if message_count >= 120:
            try:
                self._fast_reset_messages_column()
                return
            except Exception:
                # fallback 到原始清理逻辑
                pass

        # 慢路径：消息较少时，逐个清理即可
        while self.messages_layout.count() > 1:  # 保留最后的 stretch
            item = self.messages_layout.takeAt(0)
            if item.widget():
                widget = item.widget()

                # 根据类型清理资源
                if hasattr(widget, "cleanup"):
                    try:
                        widget.cleanup()
                    except Exception as e:
                        logger.warning("清理 widget 资源时出错: %s", e)

                # 删除 widget
                widget.deleteLater()

    def _on_settings_saved(self):
        """设置保存后的回调 - v2.22.0 优化：刷新头像"""
        try:
            logger.info("设置已保存")
        except Exception:
            pass

        # v2.22.0: 刷新头像显示（避免替换 widget 导致嵌套布局结构被破坏）
        try:
            if user_session.is_logged_in():
                ai_avatar = user_session.get_ai_avatar()
                self._update_header_avatar_label(ai_avatar)
                logger.info("AI助手头像已刷新: %s", ai_avatar)
        except Exception:
            pass

        # v2.51.x: 检测“需重启生效”的设置并提供一键重启
        try:
            restart_reasons = self._get_restart_required_reasons()
            agent_reload_reasons = {"LLM 配置已更改", "AI 助手（Agent）参数已更改"}
            needs_agent_reload = any(reason in agent_reload_reasons for reason in restart_reasons)
            if needs_agent_reload:
                try:
                    self._reload_agent_after_settings_saved()
                except Exception:
                    pass
                restart_reasons = [r for r in restart_reasons if r not in agent_reload_reasons]

            if restart_reasons:
                from PyQt6.QtWidgets import QMessageBox

                details = "\n".join(f"• {reason}" for reason in restart_reasons)
                box = QMessageBox(self)
                box.setIcon(QMessageBox.Icon.Information)
                box.setWindowTitle("✅ 设置已保存")
                box.setText("以下设置需要重启应用后生效：\n\n" + details + "\n\n是否立即重启？")
                restart_btn = box.addButton("立即重启", QMessageBox.ButtonRole.AcceptRole)
                later_btn = box.addButton("稍后", QMessageBox.ButtonRole.RejectRole)
                box.setDefaultButton(restart_btn)
                box.exec()

                if box.clickedButton() == restart_btn:
                    self._restart_application()
                    return
                _ = later_btn
        except Exception:
            # 重启提示失败不应影响正常流程
            pass

        # 返回聊天区域
        self._on_settings_back()

    def _reload_agent_after_settings_saved(self) -> None:
        """设置保存后重载 Agent（避免“改了配置但运行态未更新”导致的异常）。"""
        try:
            thread = getattr(self, "current_chat_thread", None)
            if thread is not None and thread.isRunning():
                self._cancel_chat_thread(thread)
        except Exception:
            pass

        try:
            if getattr(self, "typing_indicator", None) is not None:
                self._hide_typing_indicator()
        except Exception:
            pass

        try:
            self._reset_stream_render_state()
        except Exception:
            pass

        try:
            old_agent = getattr(self, "agent", None)
            if old_agent is not None and hasattr(old_agent, "close"):
                old_agent.close()
        except Exception:
            pass

        self.agent = None
        self._agent_init_failed = False
        self._init_agent_async()
        try:
            show_toast(self, "正在应用新配置，重启 AI…", Toast.TYPE_INFO, duration=1500)
        except Exception:
            pass

    def _update_header_avatar_label(self, avatar_text: str) -> None:
        """更新聊天窗口头部头像（不替换 widget，避免破坏嵌套布局结构）。"""
        label = getattr(self, "avatar_label", None)
        if label is None:
            return

        try:
            size = int(label.width() or label.height() or 56)
        except Exception:
            size = 56

        try:
            label.setFixedSize(size, size)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        except Exception:
            pass

        avatar_path = Path(avatar_text) if avatar_text else None
        if avatar_path and avatar_path.is_file():
            try:
                mtime_ns = avatar_path.stat().st_mtime_ns
            except OSError:
                mtime_ns = 0

            rounded = _load_rounded_header_avatar_pixmap(str(avatar_path), size, mtime_ns)
            try:
                if not rounded.isNull():
                    label.setPixmap(rounded)
                    label.setText("")
                else:
                    label.setPixmap(QPixmap())
                    label.setText("🐱")
                label.setScaledContents(False)
            except Exception:
                pass
        else:
            try:
                label.setPixmap(QPixmap())
                label.setText(avatar_text if avatar_text else "🐱")
                label.setScaledContents(False)
            except Exception:
                pass

        # 统一样式（与 _create_avatar_label_for_header 一致）
        try:
            label.setStyleSheet(
                f"""
                QLabel {{
                    background: qlineargradient(
                        x1:0, y1:0, x2:1, y2:1,
                        stop:0 {MD3_ENHANCED_COLORS['primary_40']},
                        stop:1 {MD3_ENHANCED_COLORS['secondary_40']}
                    );
                    border-radius: {size // 2}px;
                    font-size: {size // 2}px;
                    border: 3px solid {MD3_ENHANCED_COLORS['surface_bright']};
                }}
                """
            )
        except Exception:
            pass

    def _get_restart_required_reasons(self) -> list[str]:
        """检测本次保存是否包含“需重启生效”的变更。"""
        reasons: list[str] = []

        def _norm_path(value: object) -> str:
            try:
                from os.path import normcase, normpath

                raw = str(value or "")
                return normcase(normpath(raw)) if raw else ""
            except Exception:
                return str(value or "")

        # 当前运行时配置（以“当前运行 session”视角为准：缓存/常量不变）
        try:
            from src.config.settings import settings as runtime_settings
        except Exception:
            runtime_settings = None

        # 当前主题（theme_manager 内部缓存符合“本次运行不变”的语义）
        try:
            from .theme_manager import get_active_theme_name, normalize_theme_name

            current_theme = normalize_theme_name(get_active_theme_name())
        except Exception:
            current_theme = "mint"

        current_data_dir = _norm_path(getattr(runtime_settings, "data_dir", "./data") if runtime_settings else "./data")

        # 读取最新 config.yaml（保存后文件已更新）
        try:
            import yaml

            config_path = Path("config.yaml")
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
            config = raw if isinstance(raw, dict) else {}
        except Exception:
            config = {}

        gui_section = config.get("GUI") or config.get("gui") or {}
        if not isinstance(gui_section, dict):
            gui_section = {}

        llm_section = config.get("LLM") or config.get("llm") or {}
        if not isinstance(llm_section, dict):
            llm_section = {}

        agent_section = config.get("Agent") or config.get("agent") or {}
        if not isinstance(agent_section, dict):
            agent_section = {}

        tts_section = config.get("TTS") or config.get("tts") or {}
        if not isinstance(tts_section, dict):
            tts_section = {}

        mcp_section = config.get("MCP") or config.get("mcp") or {}
        if not isinstance(mcp_section, dict):
            mcp_section = {}

        try:
            from .theme_manager import normalize_theme_name

            new_theme = normalize_theme_name(gui_section.get("theme"))
        except Exception:
            new_theme = "mint"

        new_data_dir = _norm_path(config.get("data_dir", "./data") or "./data")

        if new_theme != current_theme:
            reasons.append("界面主题已更改")
        if new_data_dir != current_data_dir:
            reasons.append("数据目录已更改")

        if runtime_settings is not None:
            try:
                current_log_level = str(getattr(runtime_settings, "log_level", "INFO") or "INFO").upper()
                new_log_level = str(config.get("log_level", current_log_level) or "INFO").upper()
                current_log_dir = _norm_path(getattr(runtime_settings, "log_dir", "logs") or "logs")
                new_log_dir = _norm_path(config.get("log_dir", current_log_dir) or current_log_dir)
                if new_log_level != current_log_level or new_log_dir != current_log_dir:
                    reasons.append("日志配置已更改")
            except Exception:
                pass

            try:
                current_llm = getattr(runtime_settings, "llm", None)
                current_llm_dict = current_llm.model_dump() if current_llm is not None else {}
                llm_changed = False
                for key in ("api", "model", "key"):
                    if key in llm_section and llm_section.get(key) != current_llm_dict.get(key):
                        llm_changed = True
                        break
                if llm_changed:
                    reasons.append("LLM 配置已更改")
            except Exception:
                pass

            try:
                current_agent = getattr(runtime_settings, "agent", None)
                current_agent_dict = current_agent.model_dump() if current_agent is not None else {}
                for key, value in agent_section.items():
                    if key in current_agent_dict and value != current_agent_dict.get(key):
                        reasons.append("AI 助手（Agent）参数已更改")
                        break
            except Exception:
                pass

            try:
                embedding_keys = (
                    "vector_db_path",
                    "memory_path",
                    "cache_path",
                    "embedding_model",
                    "embedding_api_base",
                    "use_local_embedding",
                    "enable_embedding_cache",
                )
                embedding_changed = False
                for key in embedding_keys:
                    if key not in config:
                        continue
                    new_value = config.get(key)
                    current_value = getattr(runtime_settings, key, None)
                    if key.endswith("_path") or key.endswith("_dir") or key in {"vector_db_path"}:
                        if _norm_path(new_value) != _norm_path(current_value):
                            embedding_changed = True
                            break
                    else:
                        if new_value != current_value:
                            embedding_changed = True
                            break
                if embedding_changed:
                    reasons.append("向量/嵌入配置已更改")
            except Exception:
                pass

            try:
                current_tts = getattr(runtime_settings, "tts", None)
                current_tts_dict = current_tts.model_dump() if current_tts is not None else {}
                for key, value in tts_section.items():
                    if key in current_tts_dict and value != current_tts_dict.get(key):
                        reasons.append("语音（TTS）配置已更改")
                        break
            except Exception:
                pass

            try:
                current_mcp = getattr(runtime_settings, "mcp", None)
                current_mcp_dict = current_mcp.model_dump() if current_mcp is not None else {}
                for key, value in mcp_section.items():
                    if key in current_mcp_dict and value != current_mcp_dict.get(key):
                        reasons.append("工具（MCP）配置已更改")
                        break
            except Exception:
                pass

        return reasons

    def _restart_application(self) -> None:
        """一键重启应用（启动新进程后退出当前进程）。"""
        try:
            import sys

            from PyQt6.QtCore import QCoreApplication, QProcess
            from PyQt6.QtWidgets import QApplication

            program = sys.executable
            args = list(sys.argv[1:]) if getattr(sys, "frozen", False) else list(sys.argv)

            ok, _pid = QProcess.startDetached(program, args, str(Path.cwd()))
            if not ok:
                raise RuntimeError("startDetached() returned False")

            app = QApplication.instance()
            if app is not None:
                app.closeAllWindows()
                app.quit()
                return

            QCoreApplication.quit()
        except Exception as exc:
            try:
                logger.error("重启失败: %s", exc)
            except Exception:
                pass

            try:
                show_toast(self, "重启失败，请手动重启应用", Toast.TYPE_ERROR, duration=2500)
            except Exception:
                pass

    def _on_logout_clicked(self):
        """退出登录按钮点击 - 带平滑动画"""
        from PyQt6.QtWidgets import QMessageBox

        # 确认对话框
        reply = QMessageBox.question(
            self,
            "退出登录",
            "确定要退出登录吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            # 清除会话文件
            try:
                from src.config.settings import settings

                session_file = Path(settings.data_dir) / "session.txt"
            except Exception:
                session_file = Path("data/session.txt")
            try:
                delete_session_token_file(session_file)
                logger.info("会话已清除")
            except Exception as e:
                logger.info("清除会话失败: %s", e)

            # 清除用户会话
            user_session.logout()

            # 显示提示
            show_toast(self, "正在退出登录...", Toast.TYPE_INFO, duration=1500)

            # 延迟关闭窗口并显示登录界面
            QTimer.singleShot(1500, self._perform_logout)

    def _perform_logout(self):
        """执行退出登录 - 带淡出动画"""
        # 创建淡出动画
        self.logout_opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.logout_opacity_effect)

        self.logout_fade_out = QPropertyAnimation(self.logout_opacity_effect, b"opacity")
        self.logout_fade_out.setDuration(400)  # 400ms 淡出
        self.logout_fade_out.setStartValue(1.0)
        self.logout_fade_out.setEndValue(0.0)
        self.logout_fade_out.setEasingCurve(QEasingCurve.Type.InCubic)

        # 动画完成后显示登录窗口
        self.logout_fade_out.finished.connect(self._show_login_window)

        # 开始动画
        self.logout_fade_out.start()

    def _show_login_window(self):
        """显示登录窗口"""
        from .auth_manager import AuthManager

        # 关闭当前窗口
        self.close()

        # 创建并显示登录窗口
        try:
            from src.config.settings import settings

            illustration_path = str(Path(settings.data_dir) / "images" / "login_illustration.png")
        except Exception:
            illustration_path = "data/images/login_illustration.png"

        self.auth_manager = AuthManager(illustration_path=illustration_path)

        # 登录成功后的处理
        def on_login_success(user):

            logger.success(f"登录成功！欢迎，{user['username']}！")

            # 保存会话令牌
            try:
                session_token = user.get("session_token")
                remember_me = user.get("remember_me", False)
                try:
                    from src.config.settings import settings

                    session_file = Path(settings.data_dir) / "session.txt"
                except Exception:
                    session_file = Path("data/session.txt")

                if session_token and remember_me:
                    if write_session_token_file(session_file, session_token):
                        logger.info("会话已保存到: %s", session_file)
                else:
                    delete_session_token_file(session_file)
                    logger.info("已清除保存的会话")

                # 设置用户会话（关键修复：退出登录后再次登录时必须设置）
                if session_token:
                    user_session.login(user, session_token)
                    logger.info("用户会话已设置: %s (ID: %s)", user.get("username"), user.get("id"))
                else:
                    logger.warning("登录成功但缺少会话 token，跳过 user_session.login")
            except Exception as e:
                from src.utils.exceptions import handle_exception

                logger.info("保存会话失败: %s", e)
                handle_exception(e, logger, "保存会话失败")

            # 关闭登录窗口
            self.auth_manager.close()

            # 创建并显示新的聊天窗口
            try:
                new_window = LightChatWindow()
                new_window.show()
                logger.info("新聊天窗口已创建并显示")
            except Exception as e:
                from src.utils.exceptions import handle_exception

                logger.info("创建聊天窗口失败: %s", e)
                handle_exception(e, logger, "创建聊天窗口失败")

        self.auth_manager.login_success.connect(on_login_success)
        self.auth_manager.show()

    def _setup_fps_overlay(self) -> None:
        """启动一个低开销的 FPS 监控（用于验证 GUI 流畅度）。"""
        if not hasattr(self, "_fps_label") or self._fps_label is None:
            return
        if hasattr(self, "_fps_timer") and self._fps_timer is not None:
            return

        self._fps_frame_count = 0
        self._fps_last_ts = time.perf_counter()
        self._fps_timer = QTimer(self)
        self._fps_timer.timeout.connect(self._on_fps_tick)
        # 以 60fps 为目标节奏；若主线程忙，实际 tick 次数会显著降低
        self._fps_timer.start(16)

    def _on_fps_tick(self) -> None:
        self._fps_frame_count += 1
        now = time.perf_counter()
        elapsed = now - self._fps_last_ts
        if elapsed < 1.0:
            return

        fps = self._fps_frame_count / elapsed if elapsed > 0 else 0.0
        try:
            if hasattr(self, "_fps_label") and self._fps_label is not None:
                self._fps_label.setText(f"FPS {fps:.0f}")
        except Exception:
            pass
        self._fps_frame_count = 0
        self._fps_last_ts = now

    def eventFilter(self, obj, event):  # noqa: N802 - Qt API naming
        try:
            if obj is getattr(self, "_overlay_viewport", None):
                et = event.type()
                if et in {QEvent.Type.Resize, QEvent.Type.Show}:
                    QTimer.singleShot(0, self._position_message_overlays)
                    QTimer.singleShot(0, self._update_messages_column_width)
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def _update_messages_column_width(self) -> None:
        """Reduce excessive whitespace by adapting the message column width to the viewport."""
        viewport = getattr(self, "_overlay_viewport", None)
        messages_widget = getattr(self, "messages_widget", None)
        if viewport is None or messages_widget is None:
            return

        try:
            vw = max(0, int(viewport.width()))
        except Exception:
            vw = 0

        # Keep some breathing room on both sides but allow the column to grow on wide windows.
        # Wider columns reduce the "too much whitespace" feel (especially with Live2D on the right).
        target = vw - 48
        target = max(900, min(1400, int(target)))

        current = getattr(self, "_messages_column_max_width", None)
        if current is not None and int(current) == int(target):
            return

        self._messages_column_max_width = int(target)
        try:
            messages_widget.setMaximumWidth(int(target))
        except Exception:
            pass

        # Keep the input card aligned with the message reading width for a cleaner layout.
        enhanced_input = getattr(self, "enhanced_input", None)
        if enhanced_input is not None:
            try:
                enhanced_input.setMaximumWidth(int(target))
            except Exception:
                pass

    def _on_live2d_collapse_requested(self, collapsed: bool) -> None:
        host = getattr(self, "_messages_dock_host", None)
        dock = getattr(self, "_live2d_dock", None)
        if host is None or dock is None:
            return

        target = 72 if bool(collapsed) else 420
        panel = getattr(self, "live2d_panel", None)
        # Keep a small min width during the animation to avoid jumpy expansion.
        try:
            if panel is not None and hasattr(panel, "apply_collapsed_constraints"):
                panel.apply_collapsed_constraints()
        except Exception:
            pass
        try:
            current = int(dock.width())
        except Exception:
            current = int(target)

        if current <= 0:
            current = int(target)

        if int(current) == int(target):
            try:
                self._update_messages_column_width()
            except Exception:
                pass
            return

        # Smooth dock resize for a less "jumpy" collapse/expand.
        try:
            anim = getattr(self, "_live2d_dock_resize_anim", None)
            if anim is not None:
                try:
                    anim.stop()
                except Exception:
                    pass

            anim = QVariantAnimation(self)
            anim.setStartValue(int(current))
            anim.setEndValue(int(target))
            anim.setDuration(180)
            anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

            def _on_value_changed(v) -> None:
                try:
                    host.resizeDocks([dock], [int(v)], Qt.Orientation.Horizontal)
                except Exception:
                    pass

            def _on_finished() -> None:
                try:
                    if (not bool(collapsed)) and panel is not None and hasattr(panel, "apply_expanded_constraints"):
                        panel.apply_expanded_constraints()
                except Exception:
                    pass
                try:
                    self._update_messages_column_width()
                except Exception:
                    pass

            anim.valueChanged.connect(_on_value_changed)
            anim.finished.connect(_on_finished)
            self._live2d_dock_resize_anim = anim
            anim.start()
        except Exception:
            try:
                host.resizeDocks([dock], [int(target)], Qt.Orientation.Horizontal)
            except Exception:
                pass

    def _position_message_overlays(self) -> None:
        """让“原子岛”等 overlay 始终固定在消息显示框顶部居中。"""
        viewport = getattr(self, "_overlay_viewport", None)
        island = getattr(self, "character_island", None)
        if viewport is None or island is None:
            return

        # Edge blur overlay: match the viewport rect and stay below the status island.
        try:
            blur_overlay = getattr(self, "_edge_blur_overlay", None)
            if blur_overlay is not None:
                blur_overlay.setGeometry(viewport.rect())
                blur_overlay.raise_()
        except Exception:
            pass

        try:
            margin_x = 24
            margin_top = 12
            available = max(0, int(viewport.width()) - margin_x * 2)
            max_w = 420
            try:
                max_w = int(island.maximumWidth() or max_w)
            except Exception:
                pass
            target_w = min(max_w, available) if available > 0 else 0
            if target_w <= 0:
                return
            if target_w < 260 and available >= 260:
                target_w = 260
            island.setFixedWidth(target_w)
            x = max(0, (int(viewport.width()) - target_w) // 2)
            y = max(0, int(margin_top))
            island.move(x, y)
            island.raise_()
        except Exception:
            pass

        try:
            fps = getattr(self, "_fps_label", None)
            if fps is not None:
                fps.adjustSize()
                fps_x = max(0, int(viewport.width()) - int(fps.width()) - 12)
                fps.move(fps_x, 12)
                fps.raise_()
        except Exception:
            pass

    def _setup_avatar_pulse_animation(self):
        """设置头像脉冲动画 - 在线状态指示器

        使用缩放动画模拟心跳效果，提升视觉吸引力
        """
        # 性能优化：避免通过 min/max size 动画触发布局重算（会显著拉低帧率）。
        # 改为对状态文字做轻量透明度脉冲，只重绘小区域即可。
        try:
            if not hasattr(self, "status_label") or self.status_label is None:
                return

            effect = QGraphicsOpacityEffect(self.status_label)
            self.status_label.setGraphicsEffect(effect)

            self.status_pulse_animation = QPropertyAnimation(effect, b"opacity")
            self.status_pulse_animation.setDuration(1200)
            self.status_pulse_animation.setStartValue(0.55)
            self.status_pulse_animation.setKeyValueAt(0.5, 1.0)
            self.status_pulse_animation.setEndValue(0.55)
            self.status_pulse_animation.setEasingCurve(QEasingCurve.Type.InOutSine)
            self.status_pulse_animation.setLoopCount(-1)
            self.status_pulse_animation.start()
        except Exception:
            # 动画失败不影响主流程
            return

    def _show_shortcut_help(self):
        """显示快捷键帮助 (v2.42.0: 连接设置信号)"""
        try:
            from src.gui.widgets import ShortcutHelpDialog

            dialog = ShortcutHelpDialog(self)
            # v2.42.0: 连接设置请求信号
            dialog.settings_requested.connect(self._show_shortcut_settings)
            dialog.exec()

        except Exception as e:
            logger.error("显示快捷键帮助失败: %s", e)

    def _show_shortcut_settings(self):
        """显示快捷键设置对话框 (v2.42.0)"""
        try:
            from src.gui.widgets import ShortcutSettingsDialog

            # 获取当前快捷键配置
            current_shortcuts = {}

            # 显示对话框
            dialog = ShortcutSettingsDialog(current_shortcuts, self)
            dialog.shortcuts_changed.connect(self._on_shortcuts_changed)
            dialog.exec()

        except Exception as e:
            logger.error("显示快捷键设置失败: %s", e)

    def _on_shortcuts_changed(self, new_shortcuts: dict):
        """快捷键变更处理 (v2.42.0)"""
        try:
            show_toast(self, "快捷键设置已保存", Toast.TYPE_SUCCESS)
            logger.info("快捷键已更新: %s", new_shortcuts)

        except Exception as e:
            logger.error("快捷键变更处理失败: %s", e)
            show_toast(self, f"快捷键设置失败: {e}", Toast.TYPE_ERROR)

    def closeEvent(self, event):
        """窗口关闭事件 - 清理资源"""
        try:
            logger.info("聊天窗口正在关闭，清理资源...")
            self._closing = True

            # 0. 停止语音输入（若开启）
            try:
                if bool(getattr(self, "_asr_listening", False)):
                    self._stop_asr_listening()
            except Exception:
                pass

            # 1. 停止所有动画
            if hasattr(self, "avatar_pulse_animation") and self.avatar_pulse_animation:
                self.avatar_pulse_animation.stop()
            if hasattr(self, "avatar_pulse_animation_max") and self.avatar_pulse_animation_max:
                self.avatar_pulse_animation_max.stop()
            if hasattr(self, "status_pulse_animation") and self.status_pulse_animation:
                self.status_pulse_animation.stop()
            if hasattr(self, "page_fade_animation") and self.page_fade_animation:
                self.page_fade_animation.stop()
            if hasattr(self, "_fps_timer") and self._fps_timer:
                self._fps_timer.stop()

            # 2. 停止正在运行的聊天线程 (v2.46.1: 增强清理逻辑)
            if self.current_chat_thread is not None:
                try:
                    logger.info("停止聊天线程...")

                    # v2.46.1: 断开所有信号连接，防止信号槽泄漏
                    try:
                        self.current_chat_thread.chunk_received.disconnect()
                        self.current_chat_thread.finished.disconnect()
                        self.current_chat_thread.error.disconnect()
                    except TypeError:
                        # 信号可能已经断开
                        pass

                    # v2.46.2: 停止线程（先停止内部的Python线程）
                    if self.current_chat_thread.isRunning():
                        # 调用stop()方法，这会设置_is_running=False并等待Python线程
                        self.current_chat_thread.stop()

                        # 等待QThread结束，最多5秒（给Python线程足够时间）
                        if not self.current_chat_thread.wait(5000):
                            logger.warning("聊天线程未能在5秒内结束，强制终止")
                            self.current_chat_thread.terminate()
                            self.current_chat_thread.wait(1000)
                        else:
                            logger.info("聊天线程已正常结束")

                    # v2.46.1: 清理线程资源
                    if hasattr(self.current_chat_thread, 'cleanup'):
                        self.current_chat_thread.cleanup()

                    # v2.46.1: 标记为待删除
                    self.current_chat_thread.deleteLater()
                    self.current_chat_thread = None
                    logger.info("聊天线程已清理")
                except Exception as e:
                    logger.error("清理聊天线程失败: %s", e)

            # 2.1 清理仍在回收中的 ChatThread（例如：取消后尚未结束）
            if getattr(self, "_live_chat_threads", None):
                for thread in list(self._live_chat_threads):
                    try:
                        if thread is None or thread is self.current_chat_thread:
                            continue
                        if thread.isRunning():
                            thread.stop()
                            if not thread.wait(2000):
                                thread.terminate()
                                thread.wait(500)
                        if hasattr(thread, "cleanup"):
                            thread.cleanup()
                        thread.deleteLater()
                    except Exception:
                        pass
                try:
                    self._live_chat_threads.clear()
                except Exception:
                    pass

            # 2.2. 停止后台初始化线程（若仍在运行）
            if getattr(self, "_agent_init_thread", None) is not None:
                try:
                    logger.info("停止 Agent 初始化线程...")
                    if self._agent_init_thread.isRunning():
                        try:
                            self._agent_init_thread.requestInterruption()
                        except Exception:
                            pass
                        if not self._agent_init_thread.wait(2000):
                            logger.warning("Agent 初始化线程未能在2秒内结束，强制终止")
                            self._agent_init_thread.terminate()
                            self._agent_init_thread.wait(500)
                    self._agent_init_thread.deleteLater()
                    self._agent_init_thread = None
                    logger.info("Agent 初始化线程已清理")
                except Exception as e:
                    logger.error("清理 Agent 初始化线程失败: %s", e)

            # 2.3. 清理历史加载线程（切换联系人/上滑加载更多）
            if getattr(self, "_live_history_threads", None):
                for thread in list(self._live_history_threads):
                    try:
                        if thread is None:
                            continue
                        if thread.isRunning():
                            try:
                                thread.requestInterruption()
                            except Exception:
                                pass
                            if not thread.wait(2000):
                                thread.terminate()
                                thread.wait(500)
                        thread.deleteLater()
                    except Exception:
                        pass
                try:
                    self._live_history_threads.clear()
                except Exception:
                    pass
            try:
                self._pending_history_load_state.clear()
            except Exception:
                pass

            # 2.5. 清理图片识别线程 (v2.46.1: 新增)
            worker = getattr(self, "image_recognition_thread", None)
            if worker is not None:
                try:
                    logger.info("停止图片识别线程...")
                    is_running = getattr(worker, "isRunning", None)
                    if callable(is_running) and is_running():
                        if hasattr(worker, "stop"):
                            worker.stop()
                        if hasattr(worker, "wait") and callable(worker.wait):
                            if not worker.wait(2000):
                                logger.warning("图片识别线程未能在2秒内结束，强制终止")
                                if hasattr(worker, "terminate"):
                                    worker.terminate()
                                worker.wait(1000)
                    if hasattr(worker, "deleteLater"):
                        worker.deleteLater()
                    self.image_recognition_thread = None
                    logger.info("图片识别线程已清理")
                except Exception as e:
                    logger.error("清理图片识别线程失败: %s", e)

            # 2.6. 清理批量识别线程 (v2.46.1: 新增)
            batch_worker = getattr(self, "batch_recognition_thread", None)
            if batch_worker is not None:
                try:
                    logger.info("停止批量识别线程...")
                    is_running = getattr(batch_worker, "isRunning", None)
                    if callable(is_running) and is_running():
                        if hasattr(batch_worker, "stop"):
                            batch_worker.stop()
                        if hasattr(batch_worker, "wait") and callable(batch_worker.wait):
                            if not batch_worker.wait(2000):
                                logger.warning("批量识别线程未能在2秒内结束，强制终止")
                                if hasattr(batch_worker, "terminate"):
                                    batch_worker.terminate()
                                batch_worker.wait(1000)
                    if hasattr(batch_worker, "deleteLater"):
                        batch_worker.deleteLater()
                    self.batch_recognition_thread = None
                    logger.info("批量识别线程已清理")
                except Exception as e:
                    logger.error("清理批量识别线程失败: %s", e)

            # 3. 清理流式消息气泡
            if self.current_streaming_bubble is not None:
                if hasattr(self.current_streaming_bubble, "cleanup"):
                    self.current_streaming_bubble.cleanup()
                self.current_streaming_bubble = None
            try:
                self._reset_stream_render_state()
            except Exception:
                pass

            # 4. 清理打字指示器
            if hasattr(self, "typing_indicator") and self.typing_indicator is not None:
                if hasattr(self.typing_indicator, "stop_animation"):
                    self.typing_indicator.stop_animation()
                self.typing_indicator = None

            # 5. 清理表情选择器
            if self.emoji_picker is not None:
                self.emoji_picker.close()
                self.emoji_picker = None

            # 5.5 清理设置面板（懒加载情况下可能为 None）
            if getattr(self, "settings_panel", None) is not None:
                try:
                    if hasattr(self.settings_panel, "cleanup"):
                        self.settings_panel.cleanup()
                except Exception as e:
                    logger.debug("清理 SettingsPanel 时出错: %s", e)
                try:
                    self.settings_panel.deleteLater()
                except Exception:
                    pass
                self.settings_panel = None

            # 6. 清理消息缓存
            if hasattr(self, "_message_cache"):
                self._message_cache.clear()

            # 7. 清理 Agent 资源
            if self.agent is not None:
                logger.info("清理 Agent 资源...")
                try:
                    if hasattr(self.agent, 'close'):
                        self.agent.close()
                except Exception as e:
                    logger.warning("关闭 Agent 时出错: %s", e)
                finally:
                    self.agent = None

            # 8. 清理 TTS 工作线程和队列
            if hasattr(self, "tts_workers") and self.tts_workers:
                logger.info("清理 %s 个 TTS 后台任务...", len(self.tts_workers))
                # 兼容旧实现：如果列表里仍有 QThread，则尽量停止；线程池任务无法强制中断，关闭时需保留引用避免 GC 崩溃。
                remaining_tasks: list[object] = []
                for worker in list(self.tts_workers):
                    try:
                        is_running = getattr(worker, "isRunning", None)
                        if callable(is_running):
                            if is_running():
                                if hasattr(worker, "requestInterruption"):
                                    worker.requestInterruption()
                                if hasattr(worker, "wait") and callable(worker.wait):
                                    if not worker.wait(2000):
                                        if hasattr(worker, "terminate"):
                                            worker.terminate()
                                        worker.wait(1000)
                            if hasattr(worker, "deleteLater"):
                                worker.deleteLater()
                            continue
                    except Exception as exc:
                        logger.debug("清理 TTS worker 时出错: %s", exc)

                    # QRunnable：保留引用直到线程池任务自然结束（避免窗口关闭时被 GC）
                    remaining_tasks.append(worker)

                self.tts_workers = remaining_tasks
            
            # 清理TTS队列和状态
            if hasattr(self, "tts_queue"):
                self.tts_queue.clear()
            if hasattr(self, "tts_busy"):
                self.tts_busy = False

            # 9. 清理线程池
            if hasattr(self, "thread_pool"):
                self.thread_pool.waitForDone(1000)  # 等待最多1秒

            # 10. 关闭 TTS runtime（放在线程池收尾之后，避免提前关闭导致任务卡死）
            try:
                from src.multimodal.tts_runtime import shutdown_tts_runtime

                shutdown_tts_runtime(timeout_s=1.0)
            except Exception:
                pass

            logger.info("资源清理完成")
        except Exception as e:
            from src.utils.exceptions import handle_exception

            handle_exception(e, logger, "清理资源时出错")

        # 调用父类的 closeEvent
        super().closeEvent(event)

    def setup_window_animation(self):
        """设置窗口启动动画 - 优雅的淡入效果

        使用透明度动画实现平滑的窗口显示效果
        """
        # 创建透明度效果
        self.window_opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.window_opacity_effect)

        # 淡入动画
        self.window_fade_in = QPropertyAnimation(self.window_opacity_effect, b"opacity")
        self.window_fade_in.setDuration(600)  # 600ms 优雅淡入
        self.window_fade_in.setStartValue(0.0)
        self.window_fade_in.setEndValue(1.0)
        self.window_fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)

        # 动画完成后移除效果，减少GPU负担
        self.window_fade_in.finished.connect(lambda: self.setGraphicsEffect(None))

        # 延迟启动动画，确保窗口已显示
        QTimer.singleShot(50, self.window_fade_in.start)

    def _init_tts_system(self):
        """初始化 TTS 系统 (v2.48.13，参考 MoeChat 逻辑，统一使用多模态初始化结果)"""
        try:
            from src.config.settings import settings
            from src.multimodal import (
                get_tts_manager_instance,
                get_tts_config_instance,
                is_tts_available,
                get_audio_player,
            )
            from src.utils.stream_processor import StreamProcessor

            # 检查 TTS 配置
            if not hasattr(settings, "tts") or not settings.tts or not settings.tts.enabled:
                logger.info("TTS 未启用")
                return

            logger.info("开始初始化 TTS 系统...")

            # 使用多模态模块中已经初始化好的 TTS 管理器 / 配置
            tts_manager = get_tts_manager_instance()
            tts_config = get_tts_config_instance()

            if not tts_manager or not tts_config:
                # init_tts 可能仍在后台初始化：这里不直接“永久禁用”，而是有限次重试，避免启动阻塞。
                retry_count = int(getattr(self, "_tts_init_retry_count", 0))
                if retry_count < 8 and not getattr(self, "_tts_init_retry_scheduled", False):
                    self._tts_init_retry_count = retry_count + 1
                    self._tts_init_retry_scheduled = True
                    delay_ms = 500 if retry_count == 0 else 1500

                    def _retry() -> None:
                        self._tts_init_retry_scheduled = False
                        self._init_tts_system()

                    QTimer.singleShot(delay_ms, _retry)
                    logger.info(
                        "TTS 尚未就绪（等待 init_tts 完成），%0.1fs 后重试 (%d/8)",
                        delay_ms / 1000.0,
                        self._tts_init_retry_count,
                    )
                self.tts_enabled = False
                return

            # 只有当 TTS 连接测试成功时才允许启用 TTS
            if not is_tts_available():
                # 连接测试结果可能仍在后台更新（init_tts 健康检查尚未结束），这里同样做有限次重试。
                retry_count = int(getattr(self, "_tts_health_retry_count", 0))
                if retry_count < 8 and not getattr(self, "_tts_health_retry_scheduled", False):
                    self._tts_health_retry_count = retry_count + 1
                    self._tts_health_retry_scheduled = True
                    delay_ms = 800 if retry_count == 0 else 2000

                    def _retry() -> None:
                        self._tts_health_retry_scheduled = False
                        self._init_tts_system()

                    QTimer.singleShot(delay_ms, _retry)
                    logger.info(
                        "TTS 健康检查未就绪/未通过，%0.1fs 后重试 (%d/8)",
                        delay_ms / 1000.0,
                        self._tts_health_retry_count,
                    )
                else:
                    logger.warning("TTS 服务连接测试未通过，暂不启用 TTS")
                self.tts_enabled = False
                return

            self.tts_manager = tts_manager

            # 获取音频播放器
            self.audio_player = get_audio_player(
                default_volume=settings.tts.default_volume,
                max_queue_size=settings.tts.max_queue_size,
            )
            try:
                self._setup_live2d_lipsync_bridge()
            except Exception:
                pass

            # 创建流式文本处理器
            # v2.48.13: 将最小句子长度从 5 降低到 3，避免短句（如“好啊！”、“嗯。”）被过滤掉导致 TTS 丢句
            self.tts_stream_processor = StreamProcessor(
                min_sentence_length=3,
                max_buffer_size=500,
            )

            # 启用 TTS
            self.tts_enabled = True

            logger.info("TTS 系统初始化成功")

        except Exception as e:
            logger.error("TTS 系统初始化失败: %s", e)
            self.tts_enabled = False

    def _setup_live2d_lipsync_bridge(self) -> None:
        """Bridge TTS audio playback to Live2D mouth movement (VTuber-style lip sync).

        - Audio playback happens on AudioPlayer's worker thread.
        - Qt UI updates must happen on the GUI thread.
        We therefore emit a Qt signal on playback start and drive a lightweight GUI-timer.
        """

        timer = getattr(self, "_lipsync_timer", None)
        if timer is None:
            idle_ms = 40
            active_ms = 16
            self._lipsync_idle_interval_ms = int(idle_ms)
            self._lipsync_active_interval_ms = int(active_ms)
            self._lipsync_env: list[float] = []
            self._lipsync_step_s = 1.0 / 60.0
            self._lipsync_start_t = 0.0
            self._lipsync_active = False
            self._lipsync_last_level = 0.0
            self._lipsync_last_idx = -1

            timer = QTimer(self)
            timer.setTimerType(Qt.TimerType.PreciseTimer)
            timer.setInterval(int(idle_ms))
            timer.timeout.connect(self._on_lipsync_tick)
            timer.start()
            self._lipsync_timer = timer

        player = getattr(self, "audio_player", None)
        if player is None:
            return

        if getattr(self, "_lipsync_audio_player", None) is player:
            return

        register = getattr(player, "register_playback_start_observer", None)
        if not callable(register):
            return

        try:
            register(self._emit_lipsync_playback_started)
            self._lipsync_audio_player = player
        except Exception:
            pass

    def _emit_lipsync_playback_started(self, envelope: list[float], step_s: float, start_monotonic: float) -> None:
        """Audio thread callback -> emit a queued signal to the GUI thread."""
        if bool(getattr(self, "_closing", False)):
            return
        try:
            self.lipsync_playback_started.emit(envelope, float(step_s), float(start_monotonic))
        except Exception:
            pass

    def _on_lipsync_playback_started(self, envelope: object, step_s: float, start_monotonic: float) -> None:
        """GUI thread: store envelope + wake the lipsync timer immediately."""
        if bool(getattr(self, "_closing", False)):
            return
        try:
            raw = envelope or []
            if not isinstance(raw, (list, tuple)):
                raw = list(raw)
            env = [float(x) for x in raw]
        except Exception:
            env = []
        if not env:
            return

        try:
            step = float(step_s)
        except Exception:
            step = 1.0 / 60.0
        step = max(1e-3, min(0.2, step))
        try:
            start_t = float(start_monotonic)
        except Exception:
            start_t = time.monotonic()

        self._lipsync_env = env
        self._lipsync_step_s = step
        self._lipsync_start_t = start_t
        self._lipsync_active = True
        self._lipsync_last_idx = -1

        timer = getattr(self, "_lipsync_timer", None)
        if timer is not None:
            try:
                timer.setInterval(int(getattr(self, "_lipsync_active_interval_ms", 16)))
            except Exception:
                pass
        self._on_lipsync_tick()

    def _get_live2d_gl_for_lipsync(self):
        panel = getattr(self, "live2d_panel", None)
        if panel is None:
            return None
        try:
            if bool(getattr(panel, "is_collapsed", False)):
                return None
        except Exception:
            pass
        try:
            if not panel.isVisible():
                return None
        except Exception:
            pass

        gl = getattr(panel, "gl", None)
        if gl is None:
            return None
        try:
            if hasattr(gl, "is_ready") and not bool(gl.is_ready):
                return None
        except Exception:
            pass
        try:
            if hasattr(gl, "is_paused") and bool(gl.is_paused):
                return None
        except Exception:
            pass
        return gl

    def _on_lipsync_tick(self) -> None:
        if bool(getattr(self, "_closing", False)):
            return

        timer = getattr(self, "_lipsync_timer", None)
        idle_ms = int(getattr(self, "_lipsync_idle_interval_ms", 40))
        active_ms = int(getattr(self, "_lipsync_active_interval_ms", 16))

        gl = self._get_live2d_gl_for_lipsync()

        env = getattr(self, "_lipsync_env", []) or []
        active = bool(getattr(self, "_lipsync_active", False)) and bool(env)

        if not active:
            try:
                if timer is not None and timer.interval() != idle_ms:
                    timer.setInterval(idle_ms)
            except Exception:
                pass

            last = float(getattr(self, "_lipsync_last_level", 0.0) or 0.0)
            if gl is not None and last > 0.01:
                try:
                    gl.set_lipsync_level(0.0)
                except Exception:
                    pass
            self._lipsync_last_level = 0.0
            self._lipsync_last_idx = -1
            return

        try:
            step_s = float(getattr(self, "_lipsync_step_s", 1.0 / 60.0) or 1.0 / 60.0)
        except Exception:
            step_s = 1.0 / 60.0
        step_s = max(1e-3, step_s)
        try:
            start_t = float(getattr(self, "_lipsync_start_t", 0.0) or 0.0)
        except Exception:
            start_t = 0.0

        elapsed = max(0.0, time.monotonic() - start_t) if start_t else 0.0
        idx = int(elapsed / step_s) if step_s > 0 else int(elapsed * 60.0)

        if idx >= len(env):
            self._lipsync_active = False
            self._lipsync_env = []
            self._lipsync_last_level = 0.0
            self._lipsync_last_idx = -1
            try:
                if timer is not None and timer.interval() != idle_ms:
                    timer.setInterval(idle_ms)
            except Exception:
                pass
            if gl is not None:
                try:
                    gl.set_lipsync_level(0.0)
                except Exception:
                    pass
            return

        try:
            level = float(env[idx])
        except Exception:
            level = 0.0

        # Noise gate: prevents tiny residuals from keeping the mouth slightly open.
        if level < 0.01:
            level = 0.0

        desired_ms = active_ms if gl is not None else idle_ms
        try:
            if timer is not None and timer.interval() != desired_ms:
                timer.setInterval(desired_ms)
        except Exception:
            pass

        last_idx = int(getattr(self, "_lipsync_last_idx", -1))
        last_level = float(getattr(self, "_lipsync_last_level", 0.0) or 0.0)
        if idx == last_idx and abs(level - last_level) < 0.002:
            return

        self._lipsync_last_idx = idx
        self._lipsync_last_level = level

        if gl is not None:
            try:
                gl.set_lipsync_level(level)
            except Exception:
                pass

    def _synthesize_tts_async(self, text: str):
        """异步合成 TTS 音频 (v2.48.13 优化版，单线程队列顺序播放，参考 MoeChat)"""
        if not self.tts_enabled or not self.tts_manager or not self.audio_player:
            return

        if bool(getattr(self, "_closing", False)):
            return

        if not text or not text.strip():
            return

        # v2.48.14: 最终过滤保护层 - 确保工具调用信息不会进入TTS
        # 即使前面的过滤有遗漏，这里也会再次过滤
        if self._needs_tool_filter(text):
            text = self._filter_tool_info_safe(text)

        # 角色扮演动作/神态描写（括号内）不需要朗读：仅影响 TTS，不影响 UI 显示文本
        try:
            from src.multimodal.tts_text import strip_stage_directions

            text = strip_stage_directions(text)
        except Exception:
            pass

        # 如果过滤后为空或只包含空白，直接返回
        if not text or not text.strip():
            logger.debug("TTS 跳过空文本（最终过滤后）")
            return

        # 如果当前已有 TTS 任务在执行，则加入队列，保持顺序播放
        if getattr(self, "tts_busy", False):
            self.tts_queue.append(text)
            logger.debug("TTS 任务加入队列: %s...", text[:20])
            return

        self.tts_busy = True

        task = TTSSynthesisTask(self.tts_manager, text)
        self.tts_workers.append(task)

        def on_audio_ready(audio_data: bytes) -> None:
            if bool(getattr(self, "_closing", False)):
                return
            try:
                if self.audio_player:
                    success = self.audio_player.play_audio(audio_data)
                    if not success:
                        logger.warning("音频播放失败，但继续处理队列")
            except Exception as exc:
                logger.error("播放音频时出错: %s", exc)

        def on_error_occurred(error_msg: str) -> None:
            logger.error(error_msg)

        def cleanup_task() -> None:
            try:
                if task in self.tts_workers:
                    self.tts_workers.remove(task)
            except Exception:
                pass
            finally:
                self.tts_busy = False

            if bool(getattr(self, "_closing", False)):
                return

            if self.tts_queue:
                next_text = self.tts_queue.pop(0)
                QTimer.singleShot(0, lambda: self._synthesize_tts_async(next_text))

        task.signals.audio_ready.connect(on_audio_ready)
        task.signals.error.connect(on_error_occurred)
        task.signals.finished.connect(cleanup_task)

        try:
            self.thread_pool.start(task)
            logger.debug("TTS 合成任务已提交: %s...", text[:20])
        except Exception as exc:
            logger.error("启动 TTS 合成任务失败: %s", exc)
            cleanup_task()
