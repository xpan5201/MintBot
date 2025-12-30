"""MintChat - in-window popup action menu.

Why:
    On Windows, native popup/drop shadows can render square corners that leak
    outside of a rounded QMenu stylesheet, producing gray/black "shadow corners".
    Since this is OS-controlled and often ignores Qt window hints, the most
    reliable fix is to avoid system popups for these small menus.

What:
    PopupActionMenu is a lightweight QWidget that is parented to an existing
    widget (e.g. a viewport overlay) so it:
      - does not use an OS popup window,
      - never gets an OS-level drop shadow,
      - can still show a rounded card + soft shadow (drawn by Qt).
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QCursor
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.gui.material_design_enhanced import (
    MD3_ENHANCED_COLORS,
    MD3_ENHANCED_RADIUS,
    get_typography_css,
)
from src.gui.qss_utils import qss_rgba


@dataclass(frozen=True, slots=True)
class PopupAction:
    action_id: str
    label: str
    enabled: bool = True
    destructive: bool = False


class _CloseOnOutsideFilter(QObject):
    """Application-level event filter to dismiss an in-window popup."""

    def __init__(self, menu: "PopupActionMenu") -> None:
        super().__init__(menu)
        self._menu = menu

    def eventFilter(self, _obj, event: QEvent) -> bool:  # noqa: N802 - Qt API naming
        menu = getattr(self, "_menu", None)
        if menu is None or not bool(getattr(menu, "isVisible", lambda: False)()):
            return False

        et = event.type()
        if et == QEvent.Type.KeyPress:
            try:
                key = int(getattr(event, "key")())
            except Exception:
                key = None
            if key == int(Qt.Key.Key_Escape):
                try:
                    menu.dismiss()
                except Exception:
                    pass
                return True
            return False

        if et in {QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick, QEvent.Type.Wheel}:
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
                rect = QRect(menu.mapToGlobal(QPoint(0, 0)), menu.size())
                inside = rect.contains(pos)
            except Exception:
                inside = False

            if not inside:
                try:
                    menu.dismiss()
                except Exception:
                    pass
            return False

        return False


class PopupActionMenu(QWidget):
    """Rounded, shadowed action menu rendered inside the main window."""

    action_selected = pyqtSignal(str)

    def __init__(
        self,
        actions: list[PopupAction],
        *,
        parent: QWidget,
        min_width: int = 220,
        max_width: int = 320,
    ) -> None:
        super().__init__(parent)
        self._actions = list(actions)
        self._min_width = int(min_width)
        self._max_width = int(max_width)
        self._filter: _CloseOnOutsideFilter | None = None

        self.setObjectName("popupActionMenu")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)  # allows shadow to render without clipping
        outer.setSpacing(0)

        self._card = QFrame(self)
        self._card.setObjectName("popupActionMenuCard")
        self._card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer.addWidget(self._card, 1)

        shadow = QGraphicsDropShadowEffect(self._card)
        shadow.setBlurRadius(26)
        shadow.setOffset(0, 10)
        shadow_color = QColor(0, 0, 0, 70)
        shadow.setColor(shadow_color)
        self._card.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self._card)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(2)

        for act in self._actions:
            btn = QPushButton(str(act.label or ""), self._card)
            btn.setObjectName(
                "popupActionMenuItemDestructive" if act.destructive else "popupActionMenuItem"
            )
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setEnabled(bool(act.enabled))
            btn.setFlat(True)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda _=False, aid=str(act.action_id): self._on_action(aid))
            layout.addWidget(btn)

        self._apply_style()
        self._apply_size_constraints()
        self.hide()

    def _apply_size_constraints(self) -> None:
        try:
            self._card.adjustSize()
            w = int(self._card.sizeHint().width() or 0)
        except Exception:
            w = 0
        if w <= 0:
            w = self._min_width
        w = max(self._min_width, min(self._max_width, w))
        try:
            self.setFixedWidth(int(w) + 20)  # outer margins included
        except Exception:
            pass

    def _apply_style(self) -> None:
        c = MD3_ENHANCED_COLORS
        r = MD3_ENHANCED_RADIUS
        selected_bg = qss_rgba(c["primary"], 0.08)
        destructive = c.get("error", "#B3261E")

        self.setStyleSheet(
            f"""
            QWidget#popupActionMenu {{
                background: transparent;
            }}
            QFrame#popupActionMenuCard {{
                background: {c['surface_container']};
                border: 1px solid {c['outline_variant']};
                border-radius: {r['xl']};
            }}
            QPushButton#popupActionMenuItem,
            QPushButton#popupActionMenuItemDestructive {{
                background: transparent;
                border: none;
                border-radius: {r['lg']};
                padding: 10px 14px;
                text-align: left;
                {get_typography_css('body_medium')}
                font-weight: 550;
            }}
            QPushButton#popupActionMenuItem {{
                color: {c['on_surface']};
            }}
            QPushButton#popupActionMenuItem:hover {{
                background: {selected_bg};
            }}
            QPushButton#popupActionMenuItem:pressed {{
                background: {qss_rgba(c['primary'], 0.14)};
            }}
            QPushButton#popupActionMenuItem:disabled {{
                color: {qss_rgba(c['on_surface_variant'], 0.55)};
            }}
            QPushButton#popupActionMenuItemDestructive {{
                color: {destructive};
            }}
            QPushButton#popupActionMenuItemDestructive:hover {{
                background: {qss_rgba(destructive, 0.10)};
            }}
            QPushButton#popupActionMenuItemDestructive:pressed {{
                background: {qss_rgba(destructive, 0.16)};
            }}
            """
        )

    def open_at_anchor(
        self,
        anchor: QWidget,
        *,
        prefer_below: bool = True,
        spacing: int = 8,
        margin: int = 12,
        align_right: bool = True,
    ) -> None:
        parent = self.parentWidget()
        if parent is None or anchor is None:
            return

        try:
            self._apply_size_constraints()
        except Exception:
            pass
        self.adjustSize()

        try:
            anchor_rect = QRect(anchor.mapTo(parent, QPoint(0, 0)), anchor.size())
        except Exception:
            return

        menu_w = int(self.width() or 0)
        menu_h = int(self.height() or 0)
        if menu_w <= 0 or menu_h <= 0:
            return

        if align_right:
            x = int(anchor_rect.right() - menu_w + 1)
        else:
            x = int(anchor_rect.left())

        y_below = int(anchor_rect.bottom() + spacing)
        y_above = int(anchor_rect.top() - spacing - menu_h)

        avail = parent.rect()
        if prefer_below:
            y = y_below if y_below + menu_h <= avail.bottom() - margin else y_above
        else:
            y = y_above if y_above >= avail.top() + margin else y_below

        x = max(int(avail.left() + margin), min(int(x), int(avail.right() - margin - menu_w + 1)))
        y = max(int(avail.top() + margin), min(int(y), int(avail.bottom() - margin - menu_h + 1)))

        self.move(int(x), int(y))
        self.show()
        self.raise_()
        try:
            self.setFocus(Qt.FocusReason.PopupFocusReason)
        except Exception:
            self.setFocus()

        self._install_close_filter()

    def dismiss(self) -> None:
        self._remove_close_filter()
        try:
            self.hide()
        except Exception:
            pass
        try:
            self.deleteLater()
        except Exception:
            pass

    def _install_close_filter(self) -> None:
        if self._filter is not None:
            return
        try:
            app = QApplication.instance()
        except Exception:
            app = None
        if app is None:
            return
        filt = _CloseOnOutsideFilter(self)
        try:
            app.installEventFilter(filt)
            self._filter = filt
        except Exception:
            self._filter = None

    def _remove_close_filter(self) -> None:
        filt = self._filter
        if filt is None:
            return
        self._filter = None
        try:
            app = QApplication.instance()
        except Exception:
            app = None
        if app is None:
            return
        try:
            app.removeEventFilter(filt)
        except Exception:
            pass

    def _on_action(self, action_id: str) -> None:
        try:
            self.action_selected.emit(str(action_id))
        except Exception:
            pass
        self.dismiss()
