"""
Roleplay-first settings panel (anime / frosted-glass inspired).

Design goals:
- One-page, scrollable layout like the provided mock.
- Keep only the "main" settings to emphasize roleplay experience.
- Lightweight visuals: minimal effects, cached background painting.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import yaml
from PyQt6.QtCore import (
    QEasingCurve,
    QEvent,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
    QUrl,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QDesktopServices, QFont, QPainter, QPen, QPixmap, QRadialGradient
from PyQt6.QtWidgets import (
    QAbstractButton,
    QAbstractScrollArea,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.auth.user_session import user_session
from src.gui.material_design_enhanced import MD3_ENHANCED_COLORS, MD3_ENHANCED_RADIUS, get_typography_css
from src.gui.notifications import Toast, show_toast
from src.utils.logger import get_logger

logger = get_logger(__name__)


_RGBA_RE = re.compile(r"rgba?\\(\\s*(\\d+)\\s*,\\s*(\\d+)\\s*,\\s*(\\d+)(?:\\s*,\\s*([0-9.]+))?\\s*\\)")


def _parse_color(value: str, *, fallback: str = "#FFFFFF") -> QColor:
    raw = str(value or "").strip()
    match = _RGBA_RE.fullmatch(raw)
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
    fb = QColor(str(fallback))
    return fb if fb.isValid() else QColor("#FFFFFF")


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge dictionaries (override wins), without mutating inputs."""
    merged: dict[str, Any] = dict(base or {})
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged.get(key, {}), value)
        else:
            merged[key] = value
    return merged


class ToggleSwitch(QAbstractButton):
    """A small, smooth toggle switch (iOS-like), implemented in pure paint for performance."""

    def __init__(self, parent: QWidget | None = None, *, checked: bool = False, width: int = 56, height: int = 30):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(bool(checked))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedSize(int(width), int(height))

        self._thumb_t = 1.0 if self.isChecked() else 0.0
        self._hover_t = 0.0
        self._press_t = 0.0

        self._thumb_anim = QPropertyAnimation(self, b"thumb_t", self)
        self._thumb_anim.setDuration(160)
        self._thumb_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._hover_anim = QPropertyAnimation(self, b"hover_t", self)
        self._hover_anim.setDuration(120)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._press_anim = QPropertyAnimation(self, b"press_t", self)
        self._press_anim.setDuration(90)
        self._press_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.toggled.connect(self._on_toggled)

    @pyqtProperty(float)
    def thumb_t(self) -> float:
        return float(self._thumb_t)

    @thumb_t.setter
    def thumb_t(self, value: float) -> None:
        self._thumb_t = max(0.0, min(1.0, float(value)))
        self.update()

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

    def _start_anim(self, anim: QPropertyAnimation, end_value: float, start_value: float | None = None) -> None:
        anim.stop()
        if start_value is not None:
            anim.setStartValue(float(start_value))
        anim.setEndValue(float(end_value))
        anim.start()

    def _on_toggled(self, checked: bool) -> None:
        self._start_anim(self._thumb_anim, 1.0 if checked else 0.0, float(self._thumb_t))

    def enterEvent(self, event):  # noqa: N802 - Qt API naming
        super().enterEvent(event)
        self._start_anim(self._hover_anim, 1.0, float(self._hover_t))

    def leaveEvent(self, event):  # noqa: N802 - Qt API naming
        super().leaveEvent(event)
        self._start_anim(self._hover_anim, 0.0, float(self._hover_t))

    def mousePressEvent(self, event):  # noqa: N802 - Qt API naming
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_anim(self._press_anim, 1.0, float(self._press_t))
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802 - Qt API naming
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_anim(self._press_anim, 0.0, float(self._press_t))
        super().mouseReleaseEvent(event)

    def paintEvent(self, _event):  # noqa: N802 - Qt API naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w = float(self.width())
        h = float(self.height())
        radius = h / 2.0

        # Track
        track_off = _parse_color(MD3_ENHANCED_COLORS.get("outline_variant", "#D0D0D0"))
        track_off.setAlpha(210)
        track_on = _parse_color(MD3_ENHANCED_COLORS.get("primary", "#FF6FAE"))
        track_on.setAlpha(235)

        t = float(self._thumb_t)
        track = QColor(
            int(round(track_off.red() + (track_on.red() - track_off.red()) * t)),
            int(round(track_off.green() + (track_on.green() - track_off.green()) * t)),
            int(round(track_off.blue() + (track_on.blue() - track_off.blue()) * t)),
            int(round(track_off.alpha() + (track_on.alpha() - track_off.alpha()) * t)),
        )
        if self._hover_t > 0.01:
            track.setAlpha(min(255, int(track.alpha() + 18 * self._hover_t)))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(QRectF(0.5, 0.5, w - 1.0, h - 1.0), radius, radius)

        # Thumb
        margin = 3.0
        thumb_d = h - margin * 2.0
        travel = w - margin * 2.0 - thumb_d
        x = margin + travel * t
        y = margin + 0.6 * self._press_t
        thumb = _parse_color(MD3_ENHANCED_COLORS.get("surface_bright", "#FFFFFF"))
        thumb.setAlpha(255)

        # Subtle outline & shadow
        outline = _parse_color(MD3_ENHANCED_COLORS.get("outline", "#000000"))
        outline.setAlpha(55)

        shadow = QColor(0, 0, 0, int(30 * (1.0 - self._press_t)))
        painter.setBrush(shadow)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(x + thumb_d / 2.0, y + thumb_d / 2.0 + 0.8), thumb_d / 2.0, thumb_d / 2.0)

        painter.setBrush(thumb)
        painter.setPen(QPen(outline, 1.0))
        painter.drawEllipse(QPointF(x + thumb_d / 2.0, y + thumb_d / 2.0), thumb_d / 2.0, thumb_d / 2.0)


@dataclass(frozen=True)
class _RowSpec:
    title: str
    subtitle: str


class SettingsPanel(QWidget):
    """Roleplay-first Settings Panel (replaces the old multi-tab tool-like settings)."""

    settings_saved = pyqtSignal()
    back_clicked = pyqtSignal()

    def __init__(self, agent=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.agent = agent

        self._config_data: dict[str, Any] = {}
        self._bg_cache = QPixmap()
        self._bg_cache_key: tuple[int, int] | None = None
        self._has_unsaved_changes = False
        self._suppress_change_mark = False
        self._is_saving = False

        self._mark_timer = QTimer(self)
        self._mark_timer.setSingleShot(True)
        self._mark_timer.setInterval(120)
        self._mark_timer.timeout.connect(self._apply_unsaved_indicator)

        self._build_ui()
        self._reload_config()
        self._apply_config_to_widgets()

    # -------------------------
    # UI
    # -------------------------

    def _build_ui(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background: transparent;")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # 性能：减少滚动/内容变化时的无效重绘
        try:
            if hasattr(self.scroll_area, "setViewportUpdateMode"):
                self.scroll_area.setViewportUpdateMode(QAbstractScrollArea.ViewportUpdateMode.MinimalViewportUpdate)
        except Exception:
            pass
        self.scroll_area.setStyleSheet(
            f"""
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 10px;
                margin: 6px 6px 6px 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {MD3_ENHANCED_COLORS['outline_variant']};
                border-radius: 5px;
                min-height: 48px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {MD3_ENHANCED_COLORS['outline']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
            """
        )

        content = QWidget()
        content.setObjectName("settingsContent")
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(56, 44, 56, 44)
        content_layout.setSpacing(18)

        # Header (like the mock)
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(12)

        title = QLabel("设置")
        font = QFont()
        font.setFamilies(["Microsoft YaHei UI", "Segoe UI"])
        font.setPixelSize(44)
        font.setWeight(QFont.Weight.Black)
        title.setFont(font)
        title.setStyleSheet(f"color: {MD3_ENHANCED_COLORS['on_surface']}; background: transparent;")
        header_row.addWidget(title, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        header_row.addStretch(1)

        self.unsaved_dot = QLabel("●")
        self.unsaved_dot.setVisible(False)
        self.unsaved_dot.setStyleSheet(
            f"""
            QLabel {{
                color: {MD3_ENHANCED_COLORS.get('primary', '#FF6FAE')};
                background: transparent;
                font-size: 14px;
                font-weight: 800;
            }}
            """
        )
        header_row.addWidget(self.unsaved_dot, 0, Qt.AlignmentFlag.AlignVCenter)

        self.saved_hint = QLabel("已保存")
        self.saved_hint.setVisible(False)
        self.saved_hint.setStyleSheet(
            f"""
            QLabel {{
                color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                background-color: {MD3_ENHANCED_COLORS['surface_container_low']};
                border: 1px solid {MD3_ENHANCED_COLORS['outline_variant']};
                border-radius: {MD3_ENHANCED_RADIUS['full']};
                padding: 6px 12px;
                {get_typography_css('label_large')}
                font-weight: 700;
            }}
            """
        )
        header_row.addWidget(self.saved_hint, 0, Qt.AlignmentFlag.AlignVCenter)

        content_layout.addLayout(header_row)

        # Sections
        content_layout.addSpacing(8)
        content_layout.addWidget(self._section_title("基础设置"))
        content_layout.addWidget(self._build_basic_card())

        content_layout.addSpacing(14)
        content_layout.addWidget(self._section_title("服务设置"))
        content_layout.addWidget(self._build_service_card())

        content_layout.addSpacing(14)
        content_layout.addWidget(self._section_title("关于项目"))
        content_layout.addWidget(self._build_about_card())

        content_layout.addStretch(1)

        self.scroll_area.setWidget(content)
        root.addWidget(self.scroll_area, 1)

    def _section_title(self, text: str) -> QLabel:
        label = QLabel(str(text or ""))
        label.setStyleSheet(
            f"""
            QLabel {{
                color: {MD3_ENHANCED_COLORS['on_surface']};
                {get_typography_css('headline_small')}
                background: transparent;
                font-weight: 800;
                padding: 6px 6px;
            }}
            """
        )
        return label

    def _build_card(self) -> tuple[QWidget, QVBoxLayout]:
        card = QWidget()
        card.setObjectName("settingsCard")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 16, 22, 16)
        layout.setSpacing(0)

        # Simple "frosted" card without heavy blur effects.
        border = _parse_color(MD3_ENHANCED_COLORS.get("outline_variant", "#E0E0E0"))
        border.setAlpha(130)
        card_bg = _parse_color(MD3_ENHANCED_COLORS.get("frosted_glass_light", "#FFFFFF"))
        card_bg.setAlpha(220)
        card.setStyleSheet(
            f"""
            QWidget#settingsCard {{
                background: rgba({card_bg.red()}, {card_bg.green()}, {card_bg.blue()}, {card_bg.alpha()});
                border: 1px solid rgba({border.red()}, {border.green()}, {border.blue()}, {border.alpha()});
                border-radius: {MD3_ENHANCED_RADIUS['extra_large']};
            }}
            """
        )
        return card, layout

    def _build_basic_card(self) -> QWidget:
        card, layout = self._build_card()

        rows: list[tuple[_RowSpec, QWidget]] = []

        self.role_name_input = self._build_line_edit(placeholder="例如：雪糕 / 小雪糕")
        rows.append((_RowSpec("角色名", "AI 在聊天中展示的名字"), self.role_name_input))

        self.user_name_input = self._build_line_edit(placeholder="例如：主人 / 你的昵称")
        rows.append((_RowSpec("我的称呼", "AI 将如何称呼你（更沉浸的角色扮演）"), self.user_name_input))

        self.ai_avatar_input = self._build_line_edit(placeholder="emoji 或图片路径")
        rows.append((_RowSpec("AI 头像", "支持 emoji / 本地图片路径"), self.ai_avatar_input))

        self.mood_switch = ToggleSwitch(checked=True)
        rows.append((_RowSpec("情绪系统", "让角色拥有心情变化（更真实的互动）"), self.mood_switch))

        self.emotion_memory_switch = ToggleSwitch(checked=True)
        rows.append((_RowSpec("情绪记忆", "记住你们的互动温度（影响好感度）"), self.emotion_memory_switch))

        self.long_memory_switch = ToggleSwitch(checked=True)
        rows.append((_RowSpec("长期记忆", "让角色记住你们的故事（建议开启）"), self.long_memory_switch))

        self.tts_switch = ToggleSwitch(checked=False)
        rows.append((_RowSpec("语音回复", "开启后可使用 TTS 让角色“说话”"), self.tts_switch))

        self.asr_switch = ToggleSwitch(checked=False)
        rows.append((_RowSpec("语音输入", "开启后可使用 ASR 将语音实时转为文字"), self.asr_switch))

        for idx, (spec, control) in enumerate(rows):
            layout.addWidget(self._row(spec.title, spec.subtitle, control))
            if idx != len(rows) - 1:
                layout.addWidget(self._divider())

        # Mark changes
        for w in (
            self.role_name_input,
            self.user_name_input,
            self.ai_avatar_input,
        ):
            w.textChanged.connect(self._mark_unsaved_changes)
        for sw in (self.mood_switch, self.emotion_memory_switch, self.long_memory_switch, self.tts_switch, self.asr_switch):
            sw.toggled.connect(lambda _checked, _sw=sw: self._mark_unsaved_changes())

        return card

    def _build_service_card(self) -> QWidget:
        card, layout = self._build_card()

        self.llm_api_input = self._build_line_edit(placeholder="例如：http://127.0.0.1:8001", fixed_width=420)
        layout.addWidget(self._row("服务器地址", "连接到 LLM 服务的地址（仅保留最核心项）", self.llm_api_input))

        self.llm_api_input.textChanged.connect(self._mark_unsaved_changes)
        return card

    def _build_about_card(self) -> QWidget:
        card, layout = self._build_card()

        # Project info row
        info = QWidget()
        info_layout = QHBoxLayout(info)
        info_layout.setContentsMargins(0, 4, 0, 4)
        info_layout.setSpacing(12)

        title = QLabel("MintChat · 角色扮演聊天")
        title.setStyleSheet(
            f"""
            QLabel {{
                color: {MD3_ENHANCED_COLORS['on_surface']};
                {get_typography_css('title_medium')}
                background: transparent;
                font-weight: 750;
            }}
            """
        )
        info_layout.addWidget(title, 0, Qt.AlignmentFlag.AlignVCenter)
        info_layout.addStretch(1)

        try:
            from src.version import __version__

            version_text = f"v{__version__}"
        except Exception:
            version_text = "v?"
        version = QLabel(version_text)
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setFixedHeight(32)
        version.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        version_radius = "16px"
        version.setStyleSheet(
            f"""
            color: {MD3_ENHANCED_COLORS['on_surface_variant']};
            {get_typography_css('label_large')}
            background-color: {MD3_ENHANCED_COLORS['surface_container_low']};
            padding: 4px 12px;
            border-radius: {version_radius};
            border: 1px solid {MD3_ENHANCED_COLORS['outline_variant']};
            font-weight: 700;
            """
        )
        info_layout.addWidget(version, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(info)

        layout.addWidget(self._divider())

        # Action buttons row (like the mock)
        btn_row = QWidget()
        row_layout = QHBoxLayout(btn_row)
        row_layout.setContentsMargins(0, 6, 0, 0)
        row_layout.setSpacing(12)
        row_layout.addStretch(1)

        docs_btn = self._pill_button("核心项目", accent=False)
        docs_btn.clicked.connect(lambda: self._open_local_file(Path("README.md")))
        row_layout.addWidget(docs_btn, 0)

        helper_btn = self._pill_button("助手项目", accent=True)
        helper_btn.clicked.connect(lambda: self._open_local_file(Path("docs/README.md")))
        row_layout.addWidget(helper_btn, 0)

        layout.addWidget(btn_row)
        return card

    def _pill_button(self, text: str, *, accent: bool) -> QPushButton:
        btn = QPushButton(str(text or ""))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_height = 42
        btn.setFixedHeight(btn_height)
        btn.setMinimumWidth(120)
        btn.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        btn_radius = f"{int(round(btn_height / 2))}px"
        if accent:
            bg = MD3_ENHANCED_COLORS["gradient_primary"]
            fg = MD3_ENHANCED_COLORS["on_primary"]
            border = "none"
        else:
            bg = MD3_ENHANCED_COLORS["surface_container_high"]
            fg = MD3_ENHANCED_COLORS["on_surface"]
            border = f"1px solid {MD3_ENHANCED_COLORS['outline_variant']}"
        btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {bg};
                color: {fg};
                border: {border};
                border-radius: {btn_radius};
                padding: 0px 18px;
                {get_typography_css('label_large')}
                font-weight: 700;
            }}
            QPushButton:hover {{
                background-color: {MD3_ENHANCED_COLORS['surface_container_highest'] if not accent else bg};
            }}
            QPushButton:pressed {{
                background-color: {MD3_ENHANCED_COLORS.get('primary_70', MD3_ENHANCED_COLORS['primary']) if accent else bg};
            }}
            """
        )
        return btn

    def _open_local_file(self, path: Path) -> None:
        try:
            resolved = path.resolve()
        except Exception:
            resolved = path
        if not resolved.exists():
            show_toast(self, f"找不到文件：{path}", Toast.TYPE_ERROR, duration=1800)
            return
        try:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(resolved)))
        except Exception:
            show_toast(self, "无法打开文件", Toast.TYPE_ERROR, duration=1800)

    def _divider(self) -> QWidget:
        line = QWidget()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background: {MD3_ENHANCED_COLORS['outline_variant']};")
        return line

    def _row(self, title: str, subtitle: str, control: QWidget) -> QWidget:
        row = QWidget()
        row.setObjectName("settingsRow")
        row.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        row.setMouseTracking(True)
        row.setStyleSheet(
            f"""
            QWidget#settingsRow {{
                background: transparent;
                border-radius: 14px;
            }}
            QWidget#settingsRow:hover {{
                background: {MD3_ENHANCED_COLORS.get('frosted_glass_medium', MD3_ENHANCED_COLORS['surface_container'])};
            }}
            """
        )
        row.setMinimumHeight(74)

        layout = QHBoxLayout(row)
        layout.setContentsMargins(6, 10, 6, 10)
        layout.setSpacing(16)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)

        title_label = QLabel(str(title or ""))
        title_label.setStyleSheet(
            f"""
            QLabel {{
                color: {MD3_ENHANCED_COLORS['on_surface']};
                {get_typography_css('title_medium')}
                background: transparent;
                font-weight: 750;
            }}
            """
        )
        text_col.addWidget(title_label)

        subtitle_label = QLabel(str(subtitle or ""))
        subtitle_label.setWordWrap(True)
        subtitle_label.setStyleSheet(
            f"""
            QLabel {{
                color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                {get_typography_css('body_small')}
                background: transparent;
            }}
            """
        )
        text_col.addWidget(subtitle_label)

        layout.addLayout(text_col, 1)
        layout.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        return row

    def _build_line_edit(self, *, placeholder: str = "", fixed_width: int = 380) -> QLineEdit:
        edit = QLineEdit()
        edit.setPlaceholderText(str(placeholder or ""))
        edit.setFixedHeight(40)
        edit.setMinimumWidth(int(fixed_width))
        try:
            edit.setClearButtonEnabled(True)
        except Exception:
            pass
        edit.setStyleSheet(
            f"""
            QLineEdit {{
                background: {MD3_ENHANCED_COLORS['surface_container_low']};
                color: {MD3_ENHANCED_COLORS['on_surface']};
                border: 2px solid {MD3_ENHANCED_COLORS['outline_variant']};
                border-radius: 12px;
                padding: 8px 12px;
                {get_typography_css('body_medium')}
            }}
            QLineEdit:focus {{
                border: 2px solid {MD3_ENHANCED_COLORS.get('primary', '#FF6FAE')};
                background: {MD3_ENHANCED_COLORS['surface_bright']};
            }}
            """
        )
        return edit

    # -------------------------
    # Config load/save
    # -------------------------

    @staticmethod
    def _read_config_file() -> dict[str, Any]:
        config_path = Path("config.yaml")
        if not config_path.exists():
            return {}
        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}

    def _reload_config(self) -> None:
        self._config_data = self._read_config_file()

        # Merge user settings (DB) if available (DB wins over file).
        try:
            if user_session.is_logged_in():
                user_settings = user_session.load_settings()
                if isinstance(user_settings, dict) and user_settings:
                    self._config_data = _deep_merge(self._config_data, user_settings)
        except Exception:
            pass

    def _apply_config_to_widgets(self) -> None:
        self._suppress_change_mark = True
        try:
            agent_cfg = self._config_data.get("Agent") or self._config_data.get("agent") or {}
            if not isinstance(agent_cfg, dict):
                agent_cfg = {}
            llm_cfg = self._config_data.get("LLM") or self._config_data.get("llm") or {}
            if not isinstance(llm_cfg, dict):
                llm_cfg = {}
            tts_cfg = self._config_data.get("TTS") or self._config_data.get("tts") or {}
            if not isinstance(tts_cfg, dict):
                tts_cfg = {}
            asr_cfg = self._config_data.get("ASR") or self._config_data.get("asr") or {}
            if not isinstance(asr_cfg, dict):
                asr_cfg = {}

            try:
                self.role_name_input.setText(str(agent_cfg.get("char", "") or ""))
                self.user_name_input.setText(str(agent_cfg.get("user", "") or ""))
            except Exception:
                pass

            try:
                self.llm_api_input.setText(str(llm_cfg.get("api", "") or ""))
            except Exception:
                pass

            try:
                self.mood_switch.setChecked(bool(agent_cfg.get("mood_system_enabled", True)))
                self.emotion_memory_switch.setChecked(bool(agent_cfg.get("emotion_memory_enabled", True)))
                self.long_memory_switch.setChecked(bool(agent_cfg.get("long_memory", True)))
            except Exception:
                pass

            try:
                self.tts_switch.setChecked(bool(tts_cfg.get("enabled", False)))
            except Exception:
                pass

            try:
                self.asr_switch.setChecked(bool(asr_cfg.get("enabled", False)))
            except Exception:
                pass

            try:
                if user_session.is_logged_in():
                    self.ai_avatar_input.setText(str(user_session.get_ai_avatar() or ""))
            except Exception:
                pass

            self._set_unsaved(False)
        finally:
            self._suppress_change_mark = False

    def _collect_config_from_widgets(self) -> dict[str, Any]:
        config = dict(self._config_data or {})
        agent_cfg = config.get("Agent")
        if not isinstance(agent_cfg, dict):
            agent_cfg = {}
            config["Agent"] = agent_cfg
        llm_cfg = config.get("LLM")
        if not isinstance(llm_cfg, dict):
            llm_cfg = {}
            config["LLM"] = llm_cfg
        tts_cfg = config.get("TTS")
        if not isinstance(tts_cfg, dict):
            tts_cfg = {}
            config["TTS"] = tts_cfg
        asr_cfg = config.get("ASR")
        if not isinstance(asr_cfg, dict):
            asr_cfg = {}
            config["ASR"] = asr_cfg

        role_name_input = getattr(self, "role_name_input", None)
        user_name_input = getattr(self, "user_name_input", None)
        llm_api_input = getattr(self, "llm_api_input", None)
        mood_switch = getattr(self, "mood_switch", None)
        emotion_memory_switch = getattr(self, "emotion_memory_switch", None)
        long_memory_switch = getattr(self, "long_memory_switch", None)
        tts_switch = getattr(self, "tts_switch", None)
        asr_switch = getattr(self, "asr_switch", None)

        agent_cfg["char"] = str(role_name_input.text() if role_name_input is not None else "")
        agent_cfg["user"] = str(user_name_input.text() if user_name_input is not None else "")
        agent_cfg["mood_system_enabled"] = bool(mood_switch.isChecked() if mood_switch is not None else True)
        agent_cfg["emotion_memory_enabled"] = bool(
            emotion_memory_switch.isChecked() if emotion_memory_switch is not None else True
        )
        agent_cfg["long_memory"] = bool(long_memory_switch.isChecked() if long_memory_switch is not None else True)

        llm_cfg["api"] = str(llm_api_input.text() if llm_api_input is not None else "")
        tts_cfg["enabled"] = bool(tts_switch.isChecked() if tts_switch is not None else False)
        asr_cfg["enabled"] = bool(asr_switch.isChecked() if asr_switch is not None else False)
        return config

    def save_settings(self, *, show_feedback: bool = True) -> bool:
        if self._is_saving:
            return False
        self._is_saving = True
        try:
            config = self._collect_config_from_widgets()

            # persist avatars to user session (DB)
            try:
                if user_session.is_logged_in():
                    ai_avatar = str(self.ai_avatar_input.text() or "").strip()
                    if ai_avatar and hasattr(user_session, "update_ai_avatar"):
                        user_session.update_ai_avatar(ai_avatar)
            except Exception:
                pass

            # persist to DB (best-effort)
            try:
                if user_session.is_logged_in():
                    user_session.save_settings(config)
            except Exception:
                pass

            # write config.yaml atomically
            config_path = Path("config.yaml")
            tmp_path = config_path.with_name(config_path.name + ".tmp")
            try:
                tmp_path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
                tmp_path.replace(config_path)
            finally:
                try:
                    if tmp_path.exists():
                        tmp_path.unlink()
                except Exception:
                    pass

            self._config_data = config
            self._set_unsaved(False)
            if show_feedback:
                self._flash_saved_hint()
            self.settings_saved.emit()
            return True
        except Exception as exc:
            logger.error("保存设置失败: %s", exc, exc_info=True)
            if show_feedback:
                show_toast(self, f"保存失败：{exc}", Toast.TYPE_ERROR, duration=2000)
            return False
        finally:
            self._is_saving = False

    def _flash_saved_hint(self) -> None:
        try:
            if getattr(self, "_saved_hint_effect", None) is None:
                effect = QGraphicsOpacityEffect(self.saved_hint)
                effect.setOpacity(0.0)
                self.saved_hint.setGraphicsEffect(effect)
                self._saved_hint_effect = effect

                anim_in = QPropertyAnimation(effect, b"opacity", self)
                anim_in.setDuration(160)
                anim_in.setEasingCurve(QEasingCurve.Type.OutCubic)
                self._saved_hint_anim_in = anim_in

                anim_out = QPropertyAnimation(effect, b"opacity", self)
                anim_out.setDuration(220)
                anim_out.setEasingCurve(QEasingCurve.Type.OutCubic)
                anim_out.finished.connect(lambda: self.saved_hint.setVisible(False))
                self._saved_hint_anim_out = anim_out

            self.saved_hint.setVisible(True)
            self._saved_hint_anim_out.stop()
            self._saved_hint_anim_in.stop()
            self._saved_hint_effect.setOpacity(0.0)

            self._saved_hint_anim_in.setStartValue(0.0)
            self._saved_hint_anim_in.setEndValue(1.0)
            self._saved_hint_anim_in.start()

            QTimer.singleShot(950, self._start_saved_hint_fade_out)
        except Exception:
            pass

    def _start_saved_hint_fade_out(self) -> None:
        try:
            effect = getattr(self, "_saved_hint_effect", None)
            anim_out = getattr(self, "_saved_hint_anim_out", None)
            if effect is None or anim_out is None:
                return
            anim_out.stop()
            try:
                start_opacity = float(effect.opacity())
            except Exception:
                start_opacity = 1.0
            anim_out.setStartValue(start_opacity)
            anim_out.setEndValue(0.0)
            anim_out.start()
        except Exception:
            pass

    def keyPressEvent(self, event):  # noqa: N802 - Qt API naming
        try:
            if event.key() == Qt.Key.Key_Escape:
                self.back_clicked.emit()
                return
        except Exception:
            pass
        super().keyPressEvent(event)

    def hideEvent(self, event):  # noqa: N802 - Qt API naming
        # 退出设置界面时自动保存（无需显式保存按钮）
        try:
            if self._has_unsaved_changes and not self._is_saving:
                self.save_settings(show_feedback=False)
        except Exception:
            pass
        super().hideEvent(event)

    # -------------------------
    # Unsaved handling
    # -------------------------

    def _mark_unsaved_changes(self) -> None:
        if self._suppress_change_mark:
            return
        self._set_unsaved(True)

    def _set_unsaved(self, value: bool) -> None:
        changed = bool(value)
        if changed == self._has_unsaved_changes:
            return
        self._has_unsaved_changes = changed
        if not self._mark_timer.isActive():
            self._mark_timer.start()

    def _apply_unsaved_indicator(self) -> None:
        try:
            self.unsaved_dot.setVisible(bool(self._has_unsaved_changes))
        except Exception:
            pass

    # -------------------------
    # Background paint
    # -------------------------

    def resizeEvent(self, event):  # noqa: N802 - Qt API naming
        super().resizeEvent(event)
        self._bg_cache_key = None
        self.update()

    def paintEvent(self, event):  # noqa: N802 - Qt API naming
        w = int(self.width())
        h = int(self.height())
        if w <= 0 or h <= 0:
            return super().paintEvent(event)

        key = (w, h)
        if self._bg_cache_key != key or self._bg_cache.isNull():
            self._bg_cache = QPixmap(w, h)
            self._bg_cache.fill(Qt.GlobalColor.transparent)
            self._bg_cache_key = key

            painter = QPainter(self._bg_cache)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            base = _parse_color(MD3_ENHANCED_COLORS.get("surface", "#FFFFFF"))
            painter.fillRect(0, 0, w, h, base)

            # Soft multi-color blobs (anime-ish), similar to the mock background.
            blobs = [
                (0.18, 0.18, 0.62, MD3_ENHANCED_COLORS.get("primary_40", "#FFB3D3"), 130),
                (0.62, 0.22, 0.66, MD3_ENHANCED_COLORS.get("secondary_40", "#B1A8FF"), 120),
                (0.38, 0.64, 0.70, MD3_ENHANCED_COLORS.get("tertiary_40", "#8FD1FF"), 105),
                (0.15, 0.78, 0.55, MD3_ENHANCED_COLORS.get("primary_30", "#FFD2E6"), 95),
            ]
            for cx, cy, r, color_str, alpha in blobs:
                color = _parse_color(str(color_str), fallback="#FFB3D3")
                grad = QRadialGradient(QPointF(w * cx, h * cy), float(min(w, h)) * float(r))
                c0 = QColor(color)
                c0.setAlpha(int(alpha))
                c1 = QColor(color)
                c1.setAlpha(0)
                grad.setColorAt(0.0, c0)
                grad.setColorAt(1.0, c1)
                painter.fillRect(0, 0, w, h, grad)

            # Frosted overlay to soften contrast.
            overlay = _parse_color(MD3_ENHANCED_COLORS.get("frosted_glass_light", "#FFFFFF"))
            overlay.setAlpha(170)
            painter.fillRect(0, 0, w, h, overlay)
            painter.end()

        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._bg_cache)
        painter.end()
        return super().paintEvent(event)

    # -------------------------
    # Shortcuts
    # -------------------------

    def event(self, event):  # noqa: N802 - Qt API naming
        try:
            if event.type() == QEvent.Type.KeyPress:
                if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_S:
                    self.save_settings(show_feedback=True)
                    return True
        except Exception:
            pass
        return super().event(event)

    def cleanup(self) -> None:
        try:
            self._mark_timer.stop()
        except Exception:
            pass
