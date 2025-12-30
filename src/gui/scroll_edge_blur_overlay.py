"""Scroll edge blur overlay for QScrollArea.

This widget draws a subtle blurred+faded strip at the top/bottom edges of a
scroll viewport. It creates a "soft clip" effect when message bubbles are
partially outside the viewport during scrolling.

Implementation notes:
- We only capture and blur small strips (edge_height) for performance.
- Updates are debounced and only triggered on scroll/resize/range changes.
- Blur is approximated via QGraphicsBlurEffect rendered into a small pixmap.
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QEvent, QRect, QTimer, Qt
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QGraphicsBlurEffect,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QScrollArea,
    QWidget,
)


@dataclass(frozen=True)
class _EdgeFrame:
    pixmap: QPixmap
    height: int


class ScrollEdgeBlurOverlay(QWidget):
    """Top/bottom blurred fade overlay for a scroll area's viewport."""

    def __init__(
        self,
        *,
        scroll_area: QScrollArea,
        edge_height: int = 28,
        blur_radius: float = 10.0,
        strength: float = 0.85,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("scrollEdgeBlurOverlay")

        self._scroll_area = scroll_area
        self._edge_height = max(8, int(edge_height))
        self._blur_radius = max(0.0, float(blur_radius))
        self._strength = max(0.0, min(1.0, float(strength)))

        self._top: _EdgeFrame | None = None
        self._bottom: _EdgeFrame | None = None
        self._last_key: tuple[int, int, int, int] | None = None

        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.setInterval(32)  # debounce to ~30Hz (scroll can be very chatty)
        self._update_timer.timeout.connect(self._rebuild_cache)

        try:
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        except Exception:
            pass

        self._connect_scroll_signals()

    # -------------------------
    # Qt events
    # -------------------------

    def event(self, event: QEvent):  # noqa: N802 - Qt API naming
        try:
            if event.type() == QEvent.Type.Show:
                self.schedule_update(immediate=True)
        except Exception:
            pass
        return super().event(event)

    def resizeEvent(self, event):  # noqa: N802 - Qt API naming
        try:
            parent = self.parentWidget()
            if parent is not None:
                rect = parent.rect()
                if self.geometry() != rect:
                    self.setGeometry(rect)
        except Exception:
            pass
        self.schedule_update(immediate=True)
        return super().resizeEvent(event)

    def paintEvent(self, event):  # noqa: N802 - Qt API naming
        if self._top is None and self._bottom is None:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        try:
            if self._top is not None:
                painter.drawPixmap(0, 0, self._top.pixmap)
            if self._bottom is not None:
                y = max(0, int(self.height()) - int(self._bottom.height))
                painter.drawPixmap(0, y, self._bottom.pixmap)
        finally:
            painter.end()

    # -------------------------
    # Public API
    # -------------------------

    def schedule_update(self, *, immediate: bool = False) -> None:
        if immediate:
            try:
                self._update_timer.stop()
            except Exception:
                pass
            self._rebuild_cache()
            return

        try:
            if not self._update_timer.isActive():
                self._update_timer.start()
        except Exception:
            self._rebuild_cache()

    # -------------------------
    # Internals
    # -------------------------

    def _connect_scroll_signals(self) -> None:
        try:
            bar = self._scroll_area.verticalScrollBar()
            bar.valueChanged.connect(lambda _=None: self.schedule_update())
            bar.rangeChanged.connect(
                lambda _min=None, _max=None: self.schedule_update(immediate=True)
            )
        except Exception:
            pass

        try:
            # If the content changes size, the viewport needs new samples.
            self._scroll_area.widgetResizableChanged.connect(lambda _=None: self.schedule_update(immediate=True))  # type: ignore[attr-defined]
        except Exception:
            pass

    def _should_show_top(self) -> bool:
        try:
            return int(self._scroll_area.verticalScrollBar().value()) > 0
        except Exception:
            return False

    def _should_show_bottom(self) -> bool:
        try:
            bar = self._scroll_area.verticalScrollBar()
            return int(bar.value()) < int(bar.maximum())
        except Exception:
            return False

    def _rebuild_cache(self) -> None:
        viewport = self._scroll_area.viewport()
        if viewport is None:
            return
        content = self._scroll_area.widget()
        if content is None:
            return

        try:
            vw = max(1, int(viewport.width()))
            vh = max(1, int(viewport.height()))
        except Exception:
            return

        try:
            bar = self._scroll_area.verticalScrollBar()
            sv = int(bar.value())
            smax = int(bar.maximum())
        except Exception:
            sv = 0
            smax = 0

        edge_h = max(8, min(int(self._edge_height), vh // 3))

        key = (vw, vh, sv, smax)
        if self._last_key == key:
            return
        self._last_key = key

        top = None
        bottom = None
        try:
            if self._should_show_top():
                src = QRect(0, max(0, sv), vw, edge_h)
                top_pix = content.grab(src)
                top = _EdgeFrame(self._blur_and_mask(top_pix, edge_h, direction="down"), edge_h)
        except Exception:
            top = None

        try:
            if self._should_show_bottom():
                src_y = max(0, sv + vh - edge_h)
                src = QRect(0, src_y, vw, edge_h)
                bottom_pix = content.grab(src)
                bottom = _EdgeFrame(self._blur_and_mask(bottom_pix, edge_h, direction="up"), edge_h)
        except Exception:
            bottom = None

        self._top = top
        self._bottom = bottom

        try:
            # Skip extra repaints when invisible.
            if self.isVisible():
                self.update()
        except Exception:
            pass

    def _blur_and_mask(self, pix: QPixmap, height: int, *, direction: str) -> QPixmap:
        """Return a blurred pixmap with an alpha gradient mask."""

        pix = pix if not pix.isNull() else QPixmap(int(self.width()), int(height))
        try:
            src_w = max(1, int(pix.width()))
            src_h = max(1, int(pix.height()))
        except Exception:
            src_w, src_h = max(1, int(self.width())), int(height)

        # Downscale for cheaper blur, then scale back up.
        try:
            scaled_w = max(1, int(src_w * 0.5))
            scaled_h = max(1, int(src_h * 0.5))
            scaled = pix.scaled(
                scaled_w,
                scaled_h,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        except Exception:
            scaled = pix

        blurred = self._blur_pixmap(scaled)
        if blurred.size() != pix.size():
            try:
                blurred = blurred.scaled(
                    src_w,
                    src_h,
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            except Exception:
                pass

        return self._apply_fade_mask(blurred, direction=direction)

    def _blur_pixmap(self, pix: QPixmap) -> QPixmap:
        if pix.isNull() or self._blur_radius <= 0.0:
            return pix

        scene = QGraphicsScene()
        item = QGraphicsPixmapItem(pix)
        blur = QGraphicsBlurEffect()
        blur.setBlurRadius(float(self._blur_radius))
        item.setGraphicsEffect(blur)
        scene.addItem(item)

        out = QPixmap(pix.size())
        out.fill(Qt.GlobalColor.transparent)
        painter = QPainter(out)
        try:
            scene.render(painter)
        finally:
            painter.end()
        return out

    def _apply_fade_mask(self, pix: QPixmap, *, direction: str) -> QPixmap:
        """Apply an alpha gradient so the blur fades into the normal content."""

        if pix.isNull():
            return pix

        masked = QPixmap(pix.size())
        masked.fill(Qt.GlobalColor.transparent)

        painter = QPainter(masked)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        try:
            painter.drawPixmap(0, 0, pix)

            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
            grad = QLinearGradient(0.0, 0.0, 0.0, float(pix.height()))
            alpha_edge = int(255 * self._strength)
            if direction == "up":
                # Bottom strip: fade towards the content (top).
                grad.setColorAt(0.0, QColor(0, 0, 0, 0))
                grad.setColorAt(1.0, QColor(0, 0, 0, alpha_edge))
            else:
                # Top strip: fade towards the content (bottom).
                grad.setColorAt(0.0, QColor(0, 0, 0, alpha_edge))
                grad.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.fillRect(masked.rect(), grad)
        finally:
            painter.end()

        return masked
