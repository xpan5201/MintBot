"""Unified tooltip rendering for MintChat.

Some Windows themes (especially dark mode) can render Qt tooltips with an unexpected
black background while our app-level QSS still forces a dark text color, resulting
in unreadable tooltips. To make tooltips consistent and readable across the GUI,
we intercept QEvent.ToolTip and display our own lightweight tooltip widget.

The manager is intentionally conservative:
- It only overrides tooltips for QWidget instances that have a non-empty toolTip().
- It does not interfere with item-view/model tooltips that are generated dynamically.
- It can be disabled via the MINTCHAT_GUI_CUSTOM_TOOLTIPS env var.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import QEvent, QObject, QPoint, QTimer, Qt
from PyQt6.QtGui import QCursor, QGuiApplication
from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from .material_design_enhanced import MD3_ENHANCED_COLORS, MD3_ENHANCED_RADIUS, get_typography_css


ENV_CUSTOM_TOOLTIPS = "MINTCHAT_GUI_CUSTOM_TOOLTIPS"


def _is_enabled() -> bool:
    return os.getenv(ENV_CUSTOM_TOOLTIPS, "1").strip().lower() not in {"0", "false", "no", "off"}


class _MintTooltipWidget(QWidget):
    def __init__(self) -> None:
        super().__init__(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("mintchatTooltip")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        # Keep the tooltip widget opaque. Transparent tooltip windows can render as black on some
        # Windows GPU/theme combinations and are harder to style reliably.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        try:
            self.setAutoFillBackground(True)
        except Exception:
            pass

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

        self._label = QLabel(self)
        self._label.setWordWrap(True)
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._label.setTextFormat(Qt.TextFormat.AutoText)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.addWidget(self._label)

        c = MD3_ENHANCED_COLORS
        r = MD3_ENHANCED_RADIUS
        self.setStyleSheet(
            f"""
            QWidget#mintchatTooltip {{
                background: {c.get('surface_container_highest', '#F3F3F3')};
                border: 1px solid {c.get('outline_variant', '#D8D8D8')};
                border-radius: {r.get('md', '10px')};
            }}
            QLabel {{
                background: transparent;
                color: {c.get('on_surface', '#000000')};
                {get_typography_css('label_medium')}
            }}
            """
        )

    def show_tip(self, text: str, *, global_pos: QPoint, parent: QWidget | None) -> None:
        txt = str(text or "").strip()
        if not txt:
            self.hide()
            return

        # Respect toolTipDuration when available; otherwise use a short text-length heuristic.
        duration_ms = -1
        try:
            if parent is not None:
                duration_ms = int(getattr(parent, "toolTipDuration", lambda: -1)())
        except Exception:
            duration_ms = -1
        if duration_ms is None:
            duration_ms = -1
        if duration_ms < 0:
            duration_ms = max(1200, min(10_000, 850 + 55 * len(txt)))

        # Limit max width so long tooltips wrap nicely.
        try:
            self._label.setMaximumWidth(360)
        except Exception:
            pass

        self._label.setText(txt)
        self.adjustSize()

        pos = QPoint(int(global_pos.x()), int(global_pos.y()))
        pos += QPoint(12, 18)

        try:
            screen = QGuiApplication.screenAt(pos)
        except Exception:
            screen = None
        if screen is None:
            try:
                screen = QGuiApplication.primaryScreen()
            except Exception:
                screen = None

        if screen is not None:
            try:
                geo = screen.availableGeometry()
                x = max(int(geo.left()), min(int(pos.x()), int(geo.right() - self.width() - 4)))
                y = max(int(geo.top()), min(int(pos.y()), int(geo.bottom() - self.height() - 4)))
                pos = QPoint(x, y)
            except Exception:
                pass

        try:
            self.move(pos)
        except Exception:
            pass
        self.show()
        self.raise_()
        try:
            self._hide_timer.start(int(duration_ms))
        except Exception:
            pass


class _MintTooltipEventFilter(QObject):
    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        self._app = app
        self._tip = _MintTooltipWidget()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt API naming
        et = event.type()
        if et == QEvent.Type.ToolTip:
            # Only override standard QWidget tooltips that are set via QWidget::setToolTip().
            if not isinstance(obj, QWidget):
                return False

            try:
                text = str(obj.toolTip() or "").strip()
            except Exception:
                text = ""
            if not text:
                return False

            try:
                gp = getattr(event, "globalPos", None)
                if callable(gp):
                    pos = gp()
                else:
                    gpf = getattr(event, "globalPosition", None)
                    pos = gpf().toPoint() if callable(gpf) else QCursor.pos()
            except Exception:
                pos = QCursor.pos()

            try:
                self._tip.show_tip(text, global_pos=pos, parent=obj)
            except Exception:
                return False

            try:
                event.accept()
            except Exception:
                pass
            return True

        # Hide on common interactions.
        if et in {
            QEvent.Type.Leave,
            QEvent.Type.Hide,
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonDblClick,
            QEvent.Type.Wheel,
            QEvent.Type.FocusOut,
            QEvent.Type.WindowDeactivate,
        }:
            try:
                self._tip.hide()
            except Exception:
                pass
        return False


def install_unified_tooltips(app: QApplication) -> None:
    """Install the unified tooltip manager (idempotent)."""
    if app is None:
        return
    if not _is_enabled():
        return

    try:
        existing = getattr(app, "_mintchat_tooltip_filter", None)
        if existing is not None:
            return
    except Exception:
        existing = None

    try:
        filt = _MintTooltipEventFilter(app)
        app.installEventFilter(filt)
        setattr(app, "_mintchat_tooltip_filter", filt)
    except Exception:
        return
