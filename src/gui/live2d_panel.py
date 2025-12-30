"""Live2D side panel for MintChat (OpenGL, Python-first).

This panel renders a Cubism 3+ model inside a `QOpenGLWidget` via `live2d-py`.
It replaces the previous WebEngine/JS based approach to keep the runtime fully
Qt + Python (no embedded browser, no local static server).
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QPropertyAnimation, QTimer, QEasingCurve, Qt, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .live2d_gl_widget import Live2DGlWidget
from .enhanced_rich_input import ChatComposerIconButton
from .material_design_enhanced import MD3_ENHANCED_COLORS, MD3_ENHANCED_RADIUS, get_typography_css
from src.utils.logger import get_logger

logger = get_logger(__name__)


class _Live2DViewport(QWidget):
    def __init__(self, *, model_path: Path | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._gl = Live2DGlWidget(model_json=model_path, parent=self)
        try:
            # Avoid transparent/black GL background; match the frosted panel tone.
            self._gl.set_clear_color_css(
                MD3_ENHANCED_COLORS.get("surface_container_low", "#FFF7FB"), force_alpha=1.0
            )
        except Exception:
            pass
        try:
            self._gl.status_changed.connect(self._sync_overlay)
        except Exception:
            pass

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._gl, 1)

        self._overlay = QLabel(self)
        self._overlay.setObjectName("live2dPlaceholder")
        self._overlay.setWordWrap(True)
        self._overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        try:
            self._overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        except Exception:
            pass

        self._overlay.setText("Live2D 加载中…")
        self._overlay.show()
        self._sync_overlay()

    @property
    def gl(self) -> Live2DGlWidget:
        return self._gl

    def resizeEvent(self, event):  # noqa: N802 - Qt API naming
        try:
            self._overlay.setGeometry(self.rect())
        except Exception:
            pass
        super().resizeEvent(event)

    def _sync_overlay(self) -> None:
        try:
            msg = self._gl.error_message
            if msg:
                self._overlay.setText(msg)
                self._overlay.show()
                return
            if self._gl.is_ready:
                self._overlay.hide()
            else:
                self._overlay.setText("Live2D 加载中…")
                self._overlay.show()
        except Exception:
            pass


class Live2DPanel(QWidget):
    """A rounded Live2D panel intended to sit to the right of the message list."""

    collapse_requested = pyqtSignal(bool)

    def __init__(self, *, model_path: Path | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("live2dPanel")

        self._collapsed = False
        self._app_active = True
        self._viewport: _Live2DViewport | None = None
        self._content: QWidget | None = None
        self._header_label: QLabel | None = None
        self._gl: Live2DGlWidget | None = None
        self._collapse_btn: ChatComposerIconButton | None = None
        self._reset_btn: ChatComposerIconButton | None = None
        self._view_btn: ChatComposerIconButton | None = None
        self._lock_btn: ChatComposerIconButton | None = None
        self._react_btn: ChatComposerIconButton | None = None
        self._controls_container: QWidget | None = None
        self._controls_effect: QGraphicsOpacityEffect | None = None
        self._controls_anim: QPropertyAnimation | None = None
        self._fade_scrim: QWidget | None = None
        self._fade_effect: QGraphicsOpacityEffect | None = None
        self._fade_anim: QPropertyAnimation | None = None
        self._constraints_timer: QTimer | None = None

        self._build_ui(model_path=model_path)

        # Performance: pause rendering when app is inactive/minimized.
        try:
            app = QGuiApplication.instance()
            if app is not None:
                app.applicationStateChanged.connect(self._on_app_state_changed)
        except Exception:
            pass

        if model_path is not None:
            QTimer.singleShot(0, lambda: self.load_model(model_path))

    # -------------------------
    # UI
    # -------------------------

    def _build_ui(self, *, model_path: Path | None) -> None:
        # Let the dock splitter resize the panel smoothly.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._expanded_min_w = 320
        self._expanded_max_w = 560
        self._collapsed_w = 72
        self.setMinimumWidth(int(self._expanded_min_w))
        self.setMaximumWidth(int(self._expanded_max_w))
        self._constraints_timer = QTimer(self)
        self._constraints_timer.setSingleShot(True)
        self._constraints_timer.setInterval(220)
        self._constraints_timer.timeout.connect(self._apply_expanded_constraints_if_needed)

        self.setStyleSheet(
            f"""
            QWidget#live2dPanel {{
                background: {MD3_ENHANCED_COLORS.get('frosted_glass_light', MD3_ENHANCED_COLORS['surface_container_low'])};
                border: 1px solid {MD3_ENHANCED_COLORS['outline_variant']};
                border-radius: {MD3_ENHANCED_RADIUS['extra_large']};
            }}
            QLabel#live2dHeader {{
                color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                background: transparent;
                {get_typography_css('label_large')}
                font-weight: 760;
                padding: 10px 12px 0px 12px;
            }}
            QLabel#live2dPlaceholder {{
                color: {MD3_ENHANCED_COLORS['on_surface_variant']};
                background: transparent;
                {get_typography_css('body_small')}
                padding: 16px 16px;
            }}
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(8)

        controls = QWidget(self)
        controls.setObjectName("live2dControls")
        controls.setStyleSheet("background: transparent;")
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)

        header = QLabel("Live2D")
        header.setObjectName("live2dHeader")
        controls_layout.addWidget(header, 1)
        self._header_label = header

        btn_size = 36
        icon_size = 18
        lock_btn = ChatComposerIconButton(
            "lock_open",
            "锁定交互（防止误触拖拽/缩放）",
            size=btn_size,
            icon_size=icon_size,
            variant=ChatComposerIconButton.VARIANT_GHOST,
            parent=self,
        )
        lock_btn.clicked.connect(self._toggle_lock)
        controls_layout.addWidget(lock_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        self._lock_btn = lock_btn

        view_btn = ChatComposerIconButton(
            "zoom_out_map",
            "视图：全身（点击切换近景）",
            size=btn_size,
            icon_size=icon_size,
            variant=ChatComposerIconButton.VARIANT_GHOST,
            parent=self,
        )
        view_btn.clicked.connect(self._toggle_view_mode)
        controls_layout.addWidget(view_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        self._view_btn = view_btn

        reset_btn = ChatComposerIconButton(
            "center_focus_strong",
            "重置视图",
            size=btn_size,
            icon_size=icon_size,
            variant=ChatComposerIconButton.VARIANT_GHOST,
            parent=self,
        )
        reset_btn.clicked.connect(self._reset_view)
        controls_layout.addWidget(reset_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        self._reset_btn = reset_btn

        react_btn = ChatComposerIconButton(
            "auto_awesome",
            "随机表情/动作",
            size=btn_size,
            icon_size=icon_size,
            variant=ChatComposerIconButton.VARIANT_GHOST,
            parent=self,
        )
        react_btn.clicked.connect(self._react_once)
        controls_layout.addWidget(react_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        self._react_btn = react_btn

        # Controls container fade (keeps collapse button always accessible).
        try:
            effect = QGraphicsOpacityEffect(controls)
            effect.setOpacity(1.0)
            controls.setGraphicsEffect(effect)
            self._controls_container = controls
            self._controls_effect = effect
        except Exception:
            self._controls_container = controls
            self._controls_effect = None

        header_row.addWidget(controls, 1)

        collapse_btn = ChatComposerIconButton(
            "chevron_right",
            "折叠 Live2D",
            size=btn_size,
            icon_size=icon_size,
            variant=ChatComposerIconButton.VARIANT_GHOST,
            parent=self,
        )
        collapse_btn.clicked.connect(self._toggle_collapsed)
        header_row.addWidget(collapse_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        self._collapse_btn = collapse_btn

        root.addLayout(header_row)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        self._content = content
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(6, 6, 6, 6)
        content_layout.setSpacing(0)

        viewport = _Live2DViewport(model_path=model_path)
        viewport.setObjectName("live2dViewport")
        content_layout.addWidget(viewport, 1)
        self._viewport = viewport
        self._gl = viewport.gl
        try:
            # Default to full-body view (user can switch to portrait via the view button).
            self._gl.set_view_mode(Live2DGlWidget.VIEW_MODE_FULL)
        except Exception:
            pass

        root.addWidget(content, 1)

        # Fade scrim: animate a simple overlay on top of the GL viewport to get a
        # reliable fade even when QOpenGLWidget doesn't cooperate with opacity effects.
        try:
            scrim = QWidget(content)
            scrim.setObjectName("live2dFadeScrim")
            scrim.setStyleSheet(
                f"""
                QWidget#live2dFadeScrim {{
                    background: {MD3_ENHANCED_COLORS.get('surface_container_low', '#FFF7FB')};
                    border-radius: {MD3_ENHANCED_RADIUS['extra_large']};
                }}
                """
            )
            scrim.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            effect = QGraphicsOpacityEffect(scrim)
            effect.setOpacity(0.0)
            scrim.setGraphicsEffect(effect)
            scrim.hide()
            self._fade_scrim = scrim
            self._fade_effect = effect
        except Exception:
            self._fade_scrim = None
            self._fade_effect = None

        self._sync_controls()
        self._apply_collapsed_state(emit_signal=False)

    # -------------------------
    # Public API
    # -------------------------

    @property
    def gl(self) -> Live2DGlWidget | None:
        return self._gl

    @property
    def is_collapsed(self) -> bool:
        return bool(self._collapsed)

    def set_collapsed(self, collapsed: bool, *, emit_signal: bool = True) -> None:
        collapsed = bool(collapsed)
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self._apply_collapsed_state(emit_signal=emit_signal)

    def load_model(self, model_path: Path) -> None:
        if self._gl is None:
            return
        try:
            self._gl.set_model(model_path)
        except Exception:
            logger.warning("Live2D load_model failed: %s", model_path, exc_info=True)

    # -------------------------
    # App state
    # -------------------------

    def _on_app_state_changed(self, state) -> None:
        try:
            self._app_active = state == Qt.ApplicationState.ApplicationActive
        except Exception:
            self._app_active = True
        self._apply_pause_state()

    # -------------------------
    # Qt events
    # -------------------------

    def showEvent(self, event):  # noqa: N802 - Qt API naming
        super().showEvent(event)
        self._apply_pause_state()

    def hideEvent(self, event):  # noqa: N802 - Qt API naming
        self._apply_pause_state()
        super().hideEvent(event)

    def resizeEvent(self, event):  # noqa: N802 - Qt API naming
        super().resizeEvent(event)
        self._position_fade_scrim()

    # -------------------------
    # Controls
    # -------------------------

    def _apply_collapsed_state(self, *, emit_signal: bool) -> None:
        collapsed = bool(self._collapsed)

        # Collapse layout: fade the controls; keep only the toggle button visible.
        self._set_controls_visible(not collapsed)

        # Allow the dock to animate widths: don't hard-fix maxWidth to collapsed size.
        try:
            self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
            if collapsed:
                self.setMinimumWidth(int(self._collapsed_w))
                self.setMaximumWidth(int(self._expanded_max_w))
            else:
                self.setMaximumWidth(int(self._expanded_max_w))
        except Exception:
            pass

        # When expanding from a collapsed state we keep a small min width during the dock animation,
        # then apply the real expanded min width shortly after (or when the parent tells us).
        try:
            if self._constraints_timer is not None:
                self._constraints_timer.stop()
                if not collapsed:
                    self._constraints_timer.start()
        except Exception:
            pass

        # Start fade transition on the viewport content.
        self._start_fade(collapsed=collapsed)

        self._apply_pause_state()
        self._sync_controls()
        try:
            self.updateGeometry()
        except Exception:
            pass

        if emit_signal:
            try:
                self.collapse_requested.emit(bool(collapsed))
            except Exception:
                pass

    def apply_expanded_constraints(self) -> None:
        """Apply the preferred expanded min width (helps prevent accidental tiny docks)."""
        try:
            self.setMinimumWidth(int(self._expanded_min_w))
        except Exception:
            pass

    def apply_collapsed_constraints(self) -> None:
        """Apply the collapsed min width (keeps the panel as a slim strip)."""
        try:
            self.setMinimumWidth(int(self._collapsed_w))
        except Exception:
            pass

    def _apply_expanded_constraints_if_needed(self) -> None:
        if bool(self._collapsed):
            return
        self.apply_expanded_constraints()

    def _apply_pause_state(self) -> None:
        should_pause = bool((not self._app_active) or (not self.isVisible()) or self._collapsed)
        if self._gl is not None:
            try:
                self._gl.set_paused(should_pause)
            except Exception:
                pass
        self._sync_controls()

    def _sync_controls(self) -> None:
        gl = self._gl
        if gl is None:
            return

        if self._lock_btn is not None:
            try:
                locked = bool(getattr(gl, "interaction_locked", False))
                if locked:
                    self._lock_btn.set_icon("lock")
                    self._lock_btn.setToolTip("已锁定：点击解锁交互")
                    try:
                        self._lock_btn.set_active(True)
                    except Exception:
                        pass
                else:
                    self._lock_btn.set_icon("lock_open")
                    self._lock_btn.setToolTip("锁定交互（防止误触拖拽/缩放）")
                    try:
                        self._lock_btn.set_active(False)
                    except Exception:
                        pass
            except Exception:
                pass

        if self._collapse_btn is not None:
            try:
                if self._collapsed:
                    self._collapse_btn.set_icon("chevron_left")
                    self._collapse_btn.setToolTip("展开 Live2D")
                else:
                    self._collapse_btn.set_icon("chevron_right")
                    self._collapse_btn.setToolTip("折叠 Live2D")
            except Exception:
                pass

        if self._view_btn is not None:
            try:
                mode = getattr(gl, "view_mode", "full")
                if str(mode) == Live2DGlWidget.VIEW_MODE_PORTRAIT:
                    self._view_btn.set_icon("zoom_in_map")
                    self._view_btn.setToolTip("视图：近景（点击切换全身）")
                else:
                    self._view_btn.set_icon("zoom_out_map")
                    self._view_btn.setToolTip("视图：全身（点击切换近景）")
            except Exception:
                pass

    def _reset_view(self) -> None:
        if self._gl is None:
            return
        try:
            self._gl.reset_view()
        except Exception:
            pass

    def _toggle_lock(self) -> None:
        if self._gl is None:
            return
        try:
            locked = bool(getattr(self._gl, "interaction_locked", False))
            self._gl.set_interaction_locked(not locked)
        except Exception:
            pass
        self._sync_controls()

    def _toggle_collapsed(self) -> None:
        self.set_collapsed(not bool(self._collapsed))

    def _toggle_view_mode(self) -> None:
        if self._gl is None:
            return
        try:
            self._gl.toggle_view_mode()
        except Exception:
            pass
        self._sync_controls()

    def _react_once(self) -> None:
        gl = self._gl
        if gl is None:
            return
        try:
            gl.trigger_reaction("manual")
        except Exception:
            pass

    def _set_controls_visible(self, visible: bool) -> None:
        container = self._controls_container
        effect = self._controls_effect
        if container is None:
            return

        visible = bool(visible)
        if effect is None:
            container.setVisible(visible)
            return

        try:
            if self._controls_anim is not None:
                self._controls_anim.stop()
        except Exception:
            pass

        try:
            if visible:
                container.setVisible(True)
                effect.setOpacity(0.0)
        except Exception:
            pass

        start = float(effect.opacity())
        end = 1.0 if visible else 0.0
        if abs(start - end) < 0.01:
            try:
                effect.setOpacity(float(end))
            except Exception:
                pass
            if not visible:
                try:
                    container.setVisible(False)
                except Exception:
                    pass
            return

        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(140 if visible else 110)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(QEasingCurve.Type.InOutSine)

        def _finish() -> None:
            if not visible:
                try:
                    container.setVisible(False)
                except Exception:
                    pass

        anim.finished.connect(_finish)
        self._controls_anim = anim
        anim.start()

    def _position_fade_scrim(self) -> None:
        scrim = self._fade_scrim
        content = self._content
        if scrim is None or content is None:
            return
        try:
            scrim.setGeometry(content.rect())
            scrim.raise_()
        except Exception:
            pass

    def _start_fade(self, *, collapsed: bool) -> None:
        scrim = self._fade_scrim
        effect = self._fade_effect
        content = self._content
        if scrim is None or effect is None or content is None:
            # Fallback: no animation; apply visibility immediately.
            if self._content is not None:
                self._content.setVisible(not bool(collapsed))
            return

        self._position_fade_scrim()

        try:
            if self._fade_anim is not None:
                self._fade_anim.stop()
        except Exception:
            pass

        # Ensure content is visible while animating (both directions).
        try:
            content.setVisible(True)
        except Exception:
            pass

        try:
            scrim.show()
            scrim.raise_()
        except Exception:
            pass

        if not bool(collapsed):
            # Expand: start covered, then reveal.
            try:
                effect.setOpacity(1.0)
            except Exception:
                pass

        start = float(effect.opacity())
        end = 1.0 if bool(collapsed) else 0.0
        if abs(start - end) < 0.01:
            try:
                effect.setOpacity(float(end))
            except Exception:
                pass
            try:
                if not bool(collapsed):
                    scrim.hide()
            except Exception:
                pass
            try:
                content.setVisible(not bool(collapsed))
            except Exception:
                pass
            return

        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(160)
        anim.setStartValue(float(start))
        anim.setEndValue(float(end))
        anim.setEasingCurve(QEasingCurve.Type.InOutSine)

        def _finish() -> None:
            try:
                if bool(collapsed):
                    content.setVisible(False)
                else:
                    scrim.hide()
            except Exception:
                pass

        anim.finished.connect(_finish)
        self._fade_anim = anim
        anim.start()
