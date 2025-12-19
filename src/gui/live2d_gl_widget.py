"""Live2D OpenGL widget (QOpenGLWidget) backed by `live2d-py`.

Why this approach:
- Pure Qt + OpenGL (no WebEngine / JS runtime).
- `live2d-py` wraps Cubism Native SDK, supports `.model3.json/.moc3` models.

Notes:
- This widget is best-effort and degrades gracefully when `live2d-py` is missing.
- All Live2D / GL calls must happen on the GUI thread with a current GL context.
"""

from __future__ import annotations

import importlib
from importlib.machinery import PathFinder
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys
import math
import time
import random
from typing import Any

from PyQt6.QtCore import QElapsedTimer, QEvent, QPointF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QCursor, QSurfaceFormat
from PyQt6.QtOpenGLWidgets import QOpenGLWidget

from src.utils.logger import get_logger

logger = get_logger(__name__)


def _repo_root() -> Path:
    try:
        return Path(__file__).resolve().parents[2]
    except Exception:
        return Path.cwd()


def _sys_path_excluding_repo_root(repo_root: Path) -> list[str]:
    root = str(repo_root)
    result: list[str] = []
    for entry in sys.path:
        # "" and "." both mean current working directory (repo root when running MintChat.py)
        if entry in ("", "."):
            continue
        try:
            if str(Path(entry).resolve()) == root:
                continue
        except Exception:
            pass
        result.append(entry)
    return result


def _try_import_live2d_v3() -> tuple[Any | None, str]:
    """Import `live2d.v3` even if the repo's `live2d/` asset folder shadows the package name."""

    try:
        return importlib.import_module("live2d.v3"), ""
    except Exception as exc:
        first_error = repr(exc)

    repo_root = _repo_root()
    search_path = _sys_path_excluding_repo_root(repo_root)

    try:
        pkg_spec = PathFinder.find_spec("live2d", search_path)
        if pkg_spec is None or pkg_spec.loader is None:
            raise ModuleNotFoundError("live2d-py not installed (missing live2d package)")

        # Force-load the pip package into sys.modules, replacing any namespace package created
        # from the repo's `live2d/` assets directory.
        pkg_mod = importlib.util.module_from_spec(pkg_spec)
        sys.modules["live2d"] = pkg_mod
        pkg_spec.loader.exec_module(pkg_mod)

        v3_spec = None
        try:
            v3_spec = PathFinder.find_spec("live2d.v3", getattr(pkg_mod, "__path__", None))
        except Exception:
            v3_spec = None
        if v3_spec is None or v3_spec.loader is None:
            raise ModuleNotFoundError("live2d-py not installed (missing live2d.v3)")

        v3_mod = importlib.util.module_from_spec(v3_spec)
        sys.modules["live2d.v3"] = v3_mod
        v3_spec.loader.exec_module(v3_mod)
        return v3_mod, ""
    except Exception as exc:
        # Keep the most actionable message (prefer the second attempt which can surface shadowing issues).
        return None, repr(exc) or first_error


def _is_ascii(s: str) -> bool:
    try:
        s.encode("ascii")
        return True
    except Exception:
        return False


def _relpath_posix(target: Path, start: Path) -> str:
    return Path(os.path.relpath(str(target), str(start))).as_posix()


_CSS_RGB_RE = re.compile(
    r"^\s*rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*(?:,\s*([0-9.]+)\s*)?\)\s*$",
    re.IGNORECASE,
)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _css_color_to_rgba(css: str, *, force_alpha: float | None = None) -> tuple[float, float, float, float]:
    s = str(css or "").strip()
    if not s:
        return (0.0, 0.0, 0.0, 1.0)

    if s.startswith("#"):
        hex_str = s[1:]
        if len(hex_str) == 3:
            r = int(hex_str[0] * 2, 16)
            g = int(hex_str[1] * 2, 16)
            b = int(hex_str[2] * 2, 16)
            a = 1.0
        elif len(hex_str) == 6:
            r = int(hex_str[0:2], 16)
            g = int(hex_str[2:4], 16)
            b = int(hex_str[4:6], 16)
            a = 1.0
        else:
            return (0.0, 0.0, 0.0, 1.0)
        if force_alpha is not None:
            a = float(force_alpha)
        return (r / 255.0, g / 255.0, b / 255.0, _clamp01(a))

    m = _CSS_RGB_RE.match(s)
    if m:
        r = min(255, max(0, int(m.group(1))))
        g = min(255, max(0, int(m.group(2))))
        b = min(255, max(0, int(m.group(3))))
        a = 1.0
        if m.group(4) is not None:
            try:
                a = float(m.group(4))
            except Exception:
                a = 1.0
        if force_alpha is not None:
            a = float(force_alpha)
        return (r / 255.0, g / 255.0, b / 255.0, _clamp01(a))

    return (0.0, 0.0, 0.0, 1.0)


class Live2DGlWidget(QOpenGLWidget):
    """Render a Live2D Cubism 3+ model inside QOpenGLWidget."""

    VIEW_MODE_FULL = "full"
    VIEW_MODE_PORTRAIT = "portrait"

    status_changed = pyqtSignal()

    def __init__(self, *, model_json: Path | None = None, parent=None) -> None:
        super().__init__(parent)

        # Performance: prefer an inexpensive surface format for continuous animation.
        # - Disable multisampling (MSAA) which can be costly for a constantly updating side panel.
        # - Prefer vsync when available to reduce needless GPU churn.
        try:
            fmt = QSurfaceFormat.defaultFormat()
            try:
                fmt.setSamples(0)
            except Exception:
                pass
            try:
                fmt.setSwapInterval(1)
            except Exception:
                pass
            self.setFormat(fmt)
        except Exception:
            pass

        self._model_json = Path(model_json) if model_json is not None else None
        self._model: Any = None
        self._live2d: Any = None
        self._ready = False
        self._paused = False  # effective paused state
        self._requested_paused = False
        self._visibility_paused = False
        self._error_message = ""
        self._clear_rgba: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
        self._auto_view_enabled = True
        self._view_mode = self.VIEW_MODE_FULL
        self._interaction_locked = False
        self._update_accepts_dt: bool | None = None
        self._param_setter = None
        self._lipsync_supported: bool | None = None
        self._lipsync_target = 0.0
        self._lipsync_value = 0.0
        self._lipsync_form = 0.45
        self._lipsync_last_boost_t = 0.0
        self._param_setter_supports_weight: bool | None = None
        self._param_supported: dict[str, bool] = {}

        # "VTuber" idle layer: subtle motion + blinking + occasional expressions.
        # Implemented best-effort on top of the model without requiring a dedicated motion set.
        self._vtuber_enabled = True
        self._vtuber_t0 = time.monotonic()
        self._vtuber_next_idle_motion_t = self._vtuber_t0 + random.uniform(14.0, 22.0)
        self._vtuber_next_expression_t = self._vtuber_t0 + random.uniform(14.0, 28.0)
        self._vtuber_blink_supported: bool | None = None
        self._vtuber_blink_next_t = self._vtuber_t0 + random.uniform(2.4, 5.0)
        self._vtuber_blink_start_t = 0.0
        self._vtuber_blink_end_t = 0.0
        self._vtuber_blink_hold_s = 0.018
        self._vtuber_next_gesture_t = self._vtuber_t0 + random.uniform(4.0, 7.0)
        self._vtuber_gesture_kind = ""
        self._vtuber_gesture_start_t = 0.0
        self._vtuber_gesture_end_t = 0.0
        self._vtuber_gesture_ax = 0.0
        self._vtuber_gesture_ay = 0.0
        self._vtuber_gesture_az = 0.0
        self._vtuber_gesture_bx = 0.0
        self._vtuber_gesture_by = 0.0
        self._vtuber_gesture_bz = 0.0
        self._vtuber_gesture_ex = 0.0
        self._vtuber_gesture_ey = 0.0

        # Smooth pose state (prevents robotic "teleporting" between targets).
        self._pose_angle_x = 0.0
        self._pose_angle_y = 0.0
        self._pose_angle_z = 0.0
        self._pose_body_x = 0.0
        self._pose_body_y = 0.0
        self._pose_body_z = 0.0
        self._pose_eye_x = 0.0
        self._pose_eye_y = 0.0
        self._pose_breath = 0.5

        # Low-frequency noise (breaks periodic sine stiffness).
        self._noise_ax = 0.0
        self._noise_ay = 0.0
        self._noise_az = 0.0
        self._noise_bx = 0.0
        self._noise_by = 0.0
        self._noise_bz = 0.0
        self._noise_ex = 0.0
        self._noise_ey = 0.0

        # Eye micro-saccades (tiny fast glances).
        self._saccade_next_t = self._vtuber_t0 + random.uniform(0.8, 2.0)
        self._saccade_start_t = 0.0
        self._saccade_end_t = 0.0
        self._saccade_from_x = 0.0
        self._saccade_from_y = 0.0
        self._saccade_to_x = 0.0
        self._saccade_to_y = 0.0
        self._user_scale_mul = 1.0
        self._user_offset_x = 0.0
        self._user_offset_y = 0.0
        self._drag_pos: QPointF | None = None
        self._panning = False
        self._pan_button: Qt.MouseButton | None = None
        self._pan_last_pos: QPointF | None = None
        self._last_viewport_px: tuple[int, int] = (0, 0)

        # Normal FPS target: keep it conservative for a side panel, but smooth enough for
        # idle motion. Temporarily boost during interaction / speech for a snappier feel.
        self._tick_ms_normal = 33  # ~30 FPS
        self._tick_ms_boost = 16  # ~60 FPS

        self._tick_timer = QTimer(self)
        self._tick_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._tick_timer.setInterval(self._tick_ms_normal)  # ~30 FPS, good balance for side panel
        self._tick_timer.timeout.connect(self._on_tick)

        self._fps_boost_reset = QTimer(self)
        self._fps_boost_reset.setSingleShot(True)
        self._fps_boost_reset.timeout.connect(self._restore_fps_normal)

        self._elapsed = QElapsedTimer()
        self._last_dt_s = 1.0 / 30.0

        self.setMouseTracking(True)
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        try:
            self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        except Exception:
            pass
        try:
            self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
            self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        except Exception:
            pass

        # QOpenGLWidget transparency is fragile on Windows (often becomes black or causes artifacts).
        # We render an opaque background by default and let the panel style handle the "glass" look.
        try:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
            self.setAutoFillBackground(False)
        except Exception:
            pass

    # -------------------------
    # Public API
    # -------------------------

    @property
    def is_ready(self) -> bool:
        return bool(self._ready)

    @property
    def is_paused(self) -> bool:
        return bool(self._paused)

    @property
    def error_message(self) -> str:
        return str(self._error_message or "")

    @property
    def view_mode(self) -> str:
        return str(self._view_mode)

    @property
    def interaction_locked(self) -> bool:
        return bool(self._interaction_locked)

    def set_interaction_locked(self, locked: bool) -> None:
        locked = bool(locked)
        if locked == self._interaction_locked:
            return
        self._interaction_locked = locked
        if locked:
            self._end_pan()
        try:
            self.status_changed.emit()
        except Exception:
            pass

    def set_view_mode(self, mode: str) -> None:
        mode = str(mode or "").strip().lower()
        if mode not in {self.VIEW_MODE_FULL, self.VIEW_MODE_PORTRAIT}:
            mode = self.VIEW_MODE_FULL
        if mode == self._view_mode:
            return
        self._view_mode = mode
        ww, hh = self._last_viewport_px
        if ww > 0 and hh > 0:
            self._apply_default_view(ww, hh)
        self.update()

    def toggle_view_mode(self) -> str:
        next_mode = self.VIEW_MODE_PORTRAIT if self._view_mode == self.VIEW_MODE_FULL else self.VIEW_MODE_FULL
        self.set_view_mode(next_mode)
        return str(self._view_mode)

    def trigger_reaction(self, kind: str = "manual") -> None:
        """Trigger a light, non-intrusive reaction (motion + optional expression)."""
        if not self._ready or self._model is None:
            return

        try:
            self._boost_fps(1200)
        except Exception:
            pass

        preferred = "TapHead"
        alt = "TapBody"
        if str(kind) in {"user_send", "user"}:
            preferred, alt = alt, preferred

        group = None
        try:
            motions = self._model.GetMotionGroups() if hasattr(self._model, "GetMotionGroups") else {}
            if isinstance(motions, dict):
                if preferred in motions:
                    group = preferred
                elif alt in motions:
                    group = alt
        except Exception:
            group = None

        if group:
            try:
                self._model.StartRandomMotion(group, 3)
            except Exception:
                pass
        else:
            try:
                self._model.StartRandomMotion("Idle", 1)
            except Exception:
                pass

        try:
            if hasattr(self._model, "SetRandomExpression"):
                self._model.SetRandomExpression()
        except Exception:
            pass

        try:
            self.update()
        except Exception:
            pass

    def set_lipsync_level(self, level: float) -> None:
        """Set a 0-1 lipsync level (mouth open). Applied on the next frame."""
        try:
            lv = float(level)
        except Exception:
            lv = 0.0
        lv = max(0.0, min(1.0, lv))
        self._lipsync_target = lv
        if lv > 0.02:
            try:
                now = time.monotonic()
                last = float(getattr(self, "_lipsync_last_boost_t", 0.0) or 0.0)
                # Avoid spamming QTimer reconfiguration (set_lipsync_level can be called at 60Hz).
                if now - last > 0.35:
                    self._lipsync_last_boost_t = now
                    self._boost_fps(1300)
            except Exception:
                pass

    def reset_view(self) -> None:
        self._user_scale_mul = 1.0
        self._user_offset_x = 0.0
        self._user_offset_y = 0.0
        self._auto_view_enabled = True
        self._end_pan()
        ww, hh = self._last_viewport_px
        if ww > 0 and hh > 0:
            self._apply_default_view(ww, hh)
        self.update()

    def set_clear_color(self, r: float, g: float, b: float, a: float = 1.0) -> None:
        self._clear_rgba = (_clamp01(r), _clamp01(g), _clamp01(b), _clamp01(a))
        self.update()

    def set_clear_color_css(self, css: str, *, force_alpha: float | None = 1.0) -> None:
        self._clear_rgba = _css_color_to_rgba(css, force_alpha=force_alpha)
        self.update()

    def set_model(self, model_json: Path | None) -> None:
        self._model_json = Path(model_json) if model_json is not None else None
        self._update_accepts_dt = None
        if self._model_json is None:
            self._set_error("未配置 Live2D 模型。")
        elif not self._model_json.exists():
            self._set_error(f"未找到模型文件：{self._model_json}")
        else:
            self._set_error("")
        if self._ready:
            # Recreate renderer under current GL context.
            try:
                self.makeCurrent()
                self._destroy_model()
                self._create_model()
            finally:
                try:
                    self.doneCurrent()
                except Exception:
                    pass
            self.update()

    def set_paused(self, paused: bool) -> None:
        self._requested_paused = bool(paused)
        self._apply_pause_state()

    # -------------------------
    # Qt: GL lifecycle
    # -------------------------

    def initializeGL(self) -> None:  # noqa: N802 - Qt API naming
        live2d_mod, err = _try_import_live2d_v3()
        if live2d_mod is None:
            hint = "未检测到 / 无法加载 live2d-py（Cubism Native SDK）。\n"
            hint += f"当前 Python: {sys.executable}\n"
            hint += "请在同一环境中安装：pip install -U live2d-py\n"
            if err:
                hint += f"\n错误信息：{err}"
            self._live2d = None
            self._set_ready(False)
            self._set_error(hint)
            return

        self._live2d = live2d_mod

        try:
            # Keep logs quiet unless user explicitly enables them.
            try:
                if hasattr(self._live2d, "enableLog"):
                    self._live2d.enableLog(False)
                elif hasattr(self._live2d, "setLogEnable"):
                    self._live2d.setLogEnable(False)
            except Exception:
                pass

            # Framework init (safe to call multiple times according to upstream docs).
            try:
                self._live2d.init()
            except Exception:
                pass

            # Init GL shaders / pipeline used by live2d-py.
            try:
                self._live2d.glInit()
            except Exception:
                try:
                    self._live2d.glewInit()
                    self._live2d.glInit()
                except Exception:
                    pass

            self._create_model()
            self._set_ready(self._model is not None)
            if self._ready:
                self._set_error("")

            self._apply_pause_state()
        except Exception as exc:
            logger.error("Live2D initializeGL failed: %s", exc, exc_info=True)
            self._set_ready(False)
            self._set_error("Live2D 初始化失败。")

    def resizeGL(self, w: int, h: int) -> None:  # noqa: N802 - Qt API naming
        if self._model is None:
            return
        ww = max(1, int(w))
        hh = max(1, int(h))

        # Qt's `resizeGL` parameters may already be device-pixel sizes (depending on Qt version/platform).
        # Avoid double-multiplying by DPR, otherwise the model appears "squeezed"/tiny on HiDPI.
        try:
            dpr = float(self.devicePixelRatioF() or 1.0)
        except Exception:
            dpr = 1.0
        try:
            expected_w = int(round(self.width() * dpr))
            expected_h = int(round(self.height() * dpr))
        except Exception:
            expected_w, expected_h = ww, hh

        if abs(ww - expected_w) > 2 or abs(hh - expected_h) > 2:
            ww = max(1, int(round(ww * dpr)))
            hh = max(1, int(round(hh * dpr)))

        try:
            self._model.Resize(ww, hh)
        except Exception:
            pass
        self._last_viewport_px = (int(ww), int(hh))
        self._apply_default_view(ww, hh)

    def paintGL(self) -> None:  # noqa: N802 - Qt API naming
        if not self._ready or self._model is None or self._live2d is None:
            return

        dt_s = self._last_dt_s
        try:
            if self._elapsed.isValid():
                dt_s = max(0.0, min(0.1, self._elapsed.restart() / 1000.0))
        except Exception:
            dt_s = 1.0 / 30.0
        self._last_dt_s = dt_s

        try:
            now = time.monotonic()
        except Exception:
            now = 0.0

        # Feed pointer/idle movement to Live2D once per frame (instead of per mouse event).
        # This keeps interaction smooth without overwhelming the UI thread on high-frequency mice,
        # and also enables a subtle "VTuber" idle motion when the user isn't interacting.
        try:
            self._vtuber_pre_update(now)
        except Exception:
            pass

        try:
            # Some implementations want delta, others use internal timer.
            if hasattr(self._model, "Update"):
                if self._update_accepts_dt is None:
                    try:
                        self._model.Update(float(dt_s))
                        self._update_accepts_dt = True
                    except TypeError:
                        self._update_accepts_dt = False
                        self._model.Update()
                elif self._update_accepts_dt:
                    self._model.Update(float(dt_s))
                else:
                    self._model.Update()
        except Exception:
            pass

        # VTuber layer: blink / occasional expressions (post-update to avoid being overwritten).
        try:
            self._vtuber_post_update(now, dt_s)
        except Exception:
            pass

        # Lip-sync: apply after motion/physics update so it isn't immediately overwritten.
        try:
            self._apply_lipsync(dt_s)
        except Exception:
            pass

        try:
            r, g, b, a = self._clear_rgba
            self._live2d.clearBuffer(float(r), float(g), float(b), float(a))
        except Exception:
            pass
        try:
            self._model.Draw()
        except Exception:
            pass

    def closeEvent(self, event):  # noqa: N802 - Qt API naming
        try:
            self.makeCurrent()
            self._destroy_model()
            try:
                if self._live2d is not None:
                    self._live2d.glRelease()
            except Exception:
                pass
        finally:
            try:
                self.doneCurrent()
            except Exception:
                pass
        super().closeEvent(event)

    # -------------------------
    # Interaction
    # -------------------------

    def event(self, event: QEvent):  # noqa: N802 - Qt API naming
        # Pause when the widget is not visible to save CPU/GPU.
        try:
            if event.type() == QEvent.Type.Show:
                self._visibility_paused = False
                self._apply_pause_state()
            elif event.type() == QEvent.Type.Hide:
                self._visibility_paused = True
                self._apply_pause_state()
        except Exception:
            pass
        return super().event(event)

    def mouseMoveEvent(self, event):  # noqa: N802 - Qt API naming
        if not self._ready or self._model is None:
            return super().mouseMoveEvent(event)
        if self._interaction_locked:
            return super().mouseMoveEvent(event)
        try:
            pos: QPointF = event.position()
            if self._panning and self._pan_last_pos is not None:
                self._boost_fps()
                delta = pos - self._pan_last_pos
                self._pan_last_pos = pos
                try:
                    w = max(1.0, float(self.width()))
                    h = max(1.0, float(self.height()))
                    k = 1.4
                    self._user_offset_x += float(delta.x()) / w * k
                    self._user_offset_y += float(delta.y()) / h * k
                    # Clamp to a sane range to avoid losing the model.
                    self._user_offset_x = max(-0.8, min(0.8, self._user_offset_x))
                    self._user_offset_y = max(-0.8, min(0.6, self._user_offset_y))
                except Exception:
                    pass
                ww, hh = self._last_viewport_px
                if ww > 0 and hh > 0:
                    self._apply_default_view(ww, hh)
                event.accept()
                return

            # Store the latest pointer pos; `paintGL` will feed it to the model once per frame.
            self._drag_pos = pos

            # Dragging is light feedback; no need to boost to 60 FPS on every hover move.
            try:
                if event.buttons() != Qt.MouseButton.NoButton:
                    self._boost_fps()
            except Exception:
                pass
            event.accept()
            return
        except Exception:
            pass
        return super().mouseMoveEvent(event)

    def mousePressEvent(self, event):  # noqa: N802 - Qt API naming
        if not self._ready or self._model is None:
            return super().mousePressEvent(event)
        try:
            self._boost_fps()
            pos: QPointF = event.position()
            x = float(pos.x())
            y = float(pos.y())

            # View pan: Right-drag (or Alt+Left-drag).
            try:
                if not self._interaction_locked:
                    if event.button() == Qt.MouseButton.RightButton or (
                        event.button() == Qt.MouseButton.LeftButton
                        and (event.modifiers() & Qt.KeyboardModifier.AltModifier)
                    ):
                        self._panning = True
                        self._pan_button = event.button()
                        self._pan_last_pos = pos
                        self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
                        event.accept()
                        return
            except Exception:
                pass

            # Tap feedback: prefer "TapHead" group if exists; otherwise random idle motion.
            group = None
            try:
                motions = self._model.GetMotionGroups() if hasattr(self._model, "GetMotionGroups") else {}
                if isinstance(motions, dict) and "TapHead" in motions:
                    group = "TapHead"
                elif isinstance(motions, dict) and "TapBody" in motions:
                    group = "TapBody"
            except Exception:
                group = None

            if group:
                try:
                    self._model.StartRandomMotion(group, 3)
                except Exception:
                    pass
            else:
                try:
                    self._model.StartRandomMotion("Idle", 1)
                except Exception:
                    pass

            # Optional: expression on click (if API exists on this model type).
            try:
                if hasattr(self._model, "SetRandomExpression"):
                    self._model.SetRandomExpression()
            except Exception:
                pass
        except Exception:
            pass
        return super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802 - Qt API naming
        # Safety: end pan even if modifiers/buttons mismatch (avoids sticky pan on some platforms).
        try:
            if self._panning:
                if self._pan_button is None or event.button() == self._pan_button:
                    self._end_pan()
                    event.accept()
                    return
        except Exception:
            pass
        return super().mouseReleaseEvent(event)

    def wheelEvent(self, event):  # noqa: N802 - Qt API naming
        if self._interaction_locked:
            return super().wheelEvent(event)
        try:
            dy = int(event.angleDelta().y())
        except Exception:
            dy = 0
        if dy == 0:
            return super().wheelEvent(event)

        try:
            self._boost_fps(1500)
            steps = float(dy) / 120.0
            factor = pow(1.12, steps)
            self._user_scale_mul *= float(factor)
            self._user_scale_mul = max(0.55, min(2.2, self._user_scale_mul))
            ww, hh = self._last_viewport_px
            if ww > 0 and hh > 0:
                self._apply_default_view(ww, hh)
            self.update()
            event.accept()
            return
        except Exception:
            return super().wheelEvent(event)

    # -------------------------
    # Internals
    # -------------------------

    def _set_ready(self, ready: bool) -> None:
        ready = bool(ready)
        if ready == self._ready:
            return
        self._ready = ready
        self._apply_pause_state()
        try:
            self.status_changed.emit()
        except Exception:
            pass

    def _set_error(self, message: str) -> None:
        message = str(message or "")
        if message == self._error_message:
            return
        self._error_message = message
        try:
            self.status_changed.emit()
        except Exception:
            pass

    def _apply_pause_state(self) -> None:
        should_pause = bool(self._requested_paused or self._visibility_paused or (not self._ready))
        if should_pause == self._paused:
            return
        self._paused = should_pause
        if self._paused:
            try:
                self._tick_timer.stop()
            except Exception:
                pass
        else:
            try:
                if self._ready and not self._tick_timer.isActive():
                    self._elapsed.restart()
                    self._tick_timer.setInterval(self._tick_ms_normal)
                    self._tick_timer.start()
            except Exception:
                pass
        try:
            self.status_changed.emit()
        except Exception:
            pass

    def _on_tick(self) -> None:
        if self._paused or not self._ready or self._model is None:
            return
        self.update()

    def _create_model(self) -> None:
        self._destroy_model()
        self._update_accepts_dt = None
        self._param_setter = None
        self._param_setter_supports_weight = None
        self._param_supported = {}
        self._lipsync_supported = None
        try:
            t0 = time.monotonic()
        except Exception:
            t0 = 0.0
        self._vtuber_t0 = t0
        self._vtuber_next_idle_motion_t = t0 + random.uniform(14.0, 22.0)
        self._vtuber_next_expression_t = t0 + random.uniform(14.0, 28.0)
        self._vtuber_blink_supported = None
        self._vtuber_blink_next_t = t0 + random.uniform(2.4, 5.0)
        self._vtuber_blink_start_t = 0.0
        self._vtuber_blink_end_t = 0.0
        self._vtuber_blink_hold_s = 0.018
        self._vtuber_next_gesture_t = t0 + random.uniform(4.0, 7.0)
        self._vtuber_gesture_kind = ""
        self._vtuber_gesture_start_t = 0.0
        self._vtuber_gesture_end_t = 0.0
        self._vtuber_gesture_ax = 0.0
        self._vtuber_gesture_ay = 0.0
        self._vtuber_gesture_az = 0.0
        self._vtuber_gesture_bx = 0.0
        self._vtuber_gesture_by = 0.0
        self._vtuber_gesture_bz = 0.0
        self._vtuber_gesture_ex = 0.0
        self._vtuber_gesture_ey = 0.0
        if self._live2d is None:
            self._set_error("未检测到 live2d-py。")
            return
        if self._model_json is None:
            self._set_error("未配置 Live2D 模型。")
            return
        src_model_json = Path(self._model_json)
        if not src_model_json.exists():
            self._set_error(f"未找到模型文件：{src_model_json}")
            return

        # live2d-py / CubismJson on Windows can crash on non-ASCII JSON documents.
        # If the model folder contains non-ASCII expressions/motions, generate an ASCII-only
        # model3.json in a cache dir and copy small assets there (expressions/motions only).
        model_path = self._prepare_ascii_model_json(src_model_json)

        try:
            model = self._live2d.LAppModel()
        except Exception:
            try:
                model = self._live2d.Model()
            except Exception:
                model = None
        if model is None:
            return

        try:
            model.LoadModelJson(str(model_path))
        except Exception as exc:
            logger.error("Live2D LoadModelJson failed: %s", exc, exc_info=True)
            self._set_error("Live2D 模型加载失败。")
            return

        # Create GPU resources.
        try:
            if hasattr(model, "CreateRenderer"):
                model.CreateRenderer()
        except Exception:
            pass
        self._model = model
        self._end_pan()

        # Initial size & pose.
        try:
            self.resizeGL(int(self.width()), int(self.height()))
        except Exception:
            pass

        # Start a gentle idle motion if possible (prefer model-provided groups).
        try:
            self._start_default_idle_motion()
        except Exception:
            pass

        self._set_error("")

    def _pick_idle_motion_group(self, groups: Any) -> str | None:
        keys: list[str] = []
        if isinstance(groups, dict):
            keys = [str(k) for k in groups.keys()]
        elif isinstance(groups, (list, tuple, set)):
            keys = [str(k) for k in groups]
        elif isinstance(groups, str):
            keys = [str(groups)]

        keys = [k for k in keys if k]
        if not keys:
            return None

        prefer_exact = {"idle", "default", "standby", "waiting"}
        for k in keys:
            if k.lower() in prefer_exact:
                return k

        prefer_tokens = ("idle", "standby", "default", "wait", "stand")
        prefer_cn = ("待机", "站立", "默认", "呼吸")
        for k in keys:
            low = k.lower()
            if any(tok in low for tok in prefer_tokens) or any(tok in k for tok in prefer_cn):
                return k

        return keys[0]

    def _set_param_cached(self, setter, pid: str, value: float, weight: float) -> bool:
        """Set a Cubism parameter while caching missing IDs to avoid per-frame exceptions."""
        pid = str(pid or "")
        if not pid:
            return False
        cached = self._param_supported.get(pid)
        if cached is False:
            return False
        try:
            setter(pid, float(value), float(weight))
            self._param_supported[pid] = True
            return True
        except Exception:
            self._param_supported[pid] = False
            return False

    def _smooth_to(self, current: float, target: float, *, k: float, dt: float) -> float:
        try:
            kk = max(0.0, float(k))
        except Exception:
            kk = 0.0
        if kk <= 0.0:
            return float(target)
        try:
            d = max(0.0, min(0.2, float(dt)))
        except Exception:
            d = 0.0
        if d <= 0.0:
            return float(current)
        try:
            alpha = 1.0 - math.exp(-kk * d)
        except Exception:
            alpha = min(1.0, kk * d)
        return float(current) + (float(target) - float(current)) * max(0.0, min(1.0, float(alpha)))

    def _ou_step(self, x: float, *, dt: float, tau: float, sigma: float) -> float:
        """Ornstein–Uhlenbeck step (smooth noise)."""
        try:
            d = max(0.0, min(0.2, float(dt)))
        except Exception:
            d = 0.0
        if d <= 0.0:
            return float(x)
        t = max(1e-3, float(tau))
        s = max(0.0, float(sigma))
        try:
            n = random.gauss(0.0, 1.0)
        except Exception:
            n = 0.0
        dx = (-float(x) / t) * d + s * math.sqrt(d) * float(n)
        return float(x) + float(dx)

    def _start_default_idle_motion(self) -> None:
        model = self._model
        if model is None or not hasattr(model, "StartRandomMotion"):
            return
        groups = None
        try:
            groups = model.GetMotionGroups() if hasattr(model, "GetMotionGroups") else None
        except Exception:
            groups = None
        group = self._pick_idle_motion_group(groups) or "Idle"
        try:
            model.StartRandomMotion(str(group), 1)
        except Exception:
            pass

    # -------------------------
    # VTuber idle layer
    # -------------------------

    def set_vtuber_mode(self, enabled: bool) -> None:
        self._vtuber_enabled = bool(enabled)
        try:
            self.status_changed.emit()
        except Exception:
            pass

    def _vtuber_maybe_start_gesture(self, now: float) -> None:
        if not now:
            return
        try:
            now_f = float(now)
        except Exception:
            return

        # Clear finished gesture.
        try:
            end_t = float(getattr(self, "_vtuber_gesture_end_t", 0.0) or 0.0)
        except Exception:
            end_t = 0.0
        if end_t > 0.0 and now_f >= end_t:
            self._vtuber_gesture_kind = ""
            self._vtuber_gesture_start_t = 0.0
            self._vtuber_gesture_end_t = 0.0
            self._vtuber_gesture_ax = 0.0
            self._vtuber_gesture_ay = 0.0
            self._vtuber_gesture_az = 0.0
            self._vtuber_gesture_bx = 0.0
            self._vtuber_gesture_by = 0.0
            self._vtuber_gesture_bz = 0.0
            self._vtuber_gesture_ex = 0.0
            self._vtuber_gesture_ey = 0.0

        # Still active.
        if float(getattr(self, "_vtuber_gesture_end_t", 0.0) or 0.0) > now_f:
            return

        try:
            next_t = float(getattr(self, "_vtuber_next_gesture_t", 0.0) or 0.0)
        except Exception:
            next_t = 0.0
        if now_f < next_t:
            return

        speaking = float(getattr(self, "_lipsync_value", 0.0) or 0.0) > 0.08

        kinds = [
            "nod",
            "shake",
            "tilt",
            "look_left",
            "look_right",
            "look_up",
            "look_down",
            "lean",
        ]
        weights = [1.2, 1.0, 0.9, 0.8, 0.8, 0.7, 0.7, 0.9]
        if speaking:
            # More "talking with head" while speaking.
            weights = [1.8, 1.3, 0.8, 0.55, 0.55, 0.45, 0.45, 0.7]

        try:
            kind = random.choices(kinds, weights=weights, k=1)[0]
        except Exception:
            kind = "nod"

        # Gesture amplitude (degrees / eye params) and duration.
        dur = 1.25
        ax = ay = az = bx = by = bz = ex = ey = 0.0
        if kind == "nod":
            dur = random.uniform(1.0, 1.35)
            ay = random.uniform(10.0, 15.0)
        elif kind == "shake":
            dur = random.uniform(1.05, 1.45)
            ax = random.uniform(12.0, 18.0)
        elif kind == "tilt":
            dur = random.uniform(1.0, 1.3)
            az = random.uniform(6.0, 11.0)
        elif kind == "look_left":
            dur = random.uniform(1.2, 1.7)
            ex = -random.uniform(0.22, 0.38)
            ax = -random.uniform(4.0, 7.0)
        elif kind == "look_right":
            dur = random.uniform(1.2, 1.7)
            ex = random.uniform(0.22, 0.38)
            ax = random.uniform(4.0, 7.0)
        elif kind == "look_up":
            dur = random.uniform(1.1, 1.6)
            ey = random.uniform(0.18, 0.32)
            ay = random.uniform(6.0, 10.0)
        elif kind == "look_down":
            dur = random.uniform(1.1, 1.6)
            ey = -random.uniform(0.16, 0.28)
            ay = -random.uniform(8.0, 12.0)
        elif kind == "lean":
            dur = random.uniform(1.4, 2.1)
            bx = random.uniform(-10.0, 10.0)
            az = random.uniform(-5.0, 5.0)

        self._vtuber_gesture_kind = str(kind)
        self._vtuber_gesture_start_t = now_f
        self._vtuber_gesture_end_t = now_f + float(dur)
        self._vtuber_gesture_ax = float(ax)
        self._vtuber_gesture_ay = float(ay)
        self._vtuber_gesture_az = float(az)
        self._vtuber_gesture_bx = float(bx)
        self._vtuber_gesture_by = float(by)
        self._vtuber_gesture_bz = float(bz)
        self._vtuber_gesture_ex = float(ex)
        self._vtuber_gesture_ey = float(ey)
        self._vtuber_next_gesture_t = (now_f + float(dur)) + random.uniform(4.0, 7.5)

    def _vtuber_gesture_offsets(self, now: float) -> tuple[float, float, float, float, float, float, float, float]:
        if not now:
            return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        try:
            now_f = float(now)
        except Exception:
            return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

        try:
            start_t = float(getattr(self, "_vtuber_gesture_start_t", 0.0) or 0.0)
            end_t = float(getattr(self, "_vtuber_gesture_end_t", 0.0) or 0.0)
        except Exception:
            start_t = 0.0
            end_t = 0.0
        if start_t <= 0.0 or end_t <= 0.0 or now_f < start_t or now_f >= end_t:
            return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

        dur = max(1e-3, end_t - start_t)
        p = max(0.0, min(1.0, (now_f - start_t) / dur))
        env = math.sin(math.pi * p)  # 0->1->0
        tau = 2.0 * math.pi

        kind = str(getattr(self, "_vtuber_gesture_kind", "") or "")
        ax = float(getattr(self, "_vtuber_gesture_ax", 0.0) or 0.0)
        ay = float(getattr(self, "_vtuber_gesture_ay", 0.0) or 0.0)
        az = float(getattr(self, "_vtuber_gesture_az", 0.0) or 0.0)
        bx = float(getattr(self, "_vtuber_gesture_bx", 0.0) or 0.0)
        by = float(getattr(self, "_vtuber_gesture_by", 0.0) or 0.0)
        bz = float(getattr(self, "_vtuber_gesture_bz", 0.0) or 0.0)
        ex = float(getattr(self, "_vtuber_gesture_ex", 0.0) or 0.0)
        ey = float(getattr(self, "_vtuber_gesture_ey", 0.0) or 0.0)

        ox = oy = oz = obx = oby = obz = oex = oey = 0.0
        if kind == "nod":
            # 2 nods.
            oy = ay * math.sin(tau * 2.0 * p) * env
        elif kind == "shake":
            # 3 shakes.
            ox = ax * math.sin(tau * 3.0 * p) * env
        elif kind == "tilt":
            oz = az * math.sin(tau * 1.0 * p) * env
        elif kind.startswith("look_"):
            # Look then return.
            oex = ex * env
            oey = ey * env
            ox = ax * env
            oy = ay * env
        elif kind == "lean":
            obx = bx * env
            oz = az * env

        return (ox, oy, oz, obx, oby, obz, oex, oey)

    def _vtuber_pre_update(self, now: float) -> None:
        """Per-frame pre-update hooks: pointer drag + subtle idle movement."""
        model = self._model
        if model is None:
            return
        if self._panning:
            return

        # 1) User pointer interaction (when unlocked) takes precedence.
        hovering = False
        try:
            hovering = bool(self.underMouse())
        except Exception:
            hovering = False

        if (not self._interaction_locked) and hovering and (self._drag_pos is not None):
            try:
                pos = self._drag_pos
                model.Drag(float(pos.x()), float(pos.y()))
            except Exception:
                pass
        else:
            # 2) VTuber idle motion: a gentle "follow" point wobble.
            if bool(getattr(self, "_vtuber_enabled", True)):
                try:
                    ww = max(1.0, float(self.width()))
                    hh = max(1.0, float(self.height()))
                    t0 = float(getattr(self, "_vtuber_t0", 0.0) or 0.0)
                    t = max(0.0, float(now) - t0) if now and t0 else 0.0
                    tau = 2.0 * math.pi

                    base_x = ww * 0.52
                    base_y = hh * 0.34

                    amp_x = ww * 0.055
                    amp_y = hh * 0.050

                    wobble_x = math.sin(tau * 0.16 * t) + 0.35 * math.sin(tau * 0.47 * t + 0.4)
                    wobble_y = math.sin(tau * 0.13 * t + 1.2) + 0.28 * math.sin(tau * 0.41 * t + 2.1)

                    x = base_x + amp_x * wobble_x
                    y = base_y + amp_y * wobble_y

                    # Speaking bob: tiny head bob tied to lip-sync intensity.
                    lv_seen = float(getattr(self, "_lipsync_value", 0.0) or 0.0)
                    if lv_seen > 0.01:
                        bob = hh * 0.018 * min(1.0, lv_seen)
                        x += (ww * 0.010 * lv_seen) * math.sin(tau * 0.9 * t + 0.8)
                        y += bob * (0.55 + 0.45 * math.sin(tau * 1.1 * t))

                    x = max(0.0, min(ww, x))
                    y = max(0.0, min(hh, y))
                    model.Drag(float(x), float(y))
                except Exception:
                    pass

        # Periodic auto motion/expression to keep the model feeling alive.
        if bool(getattr(self, "_vtuber_enabled", True)) and now:
            try:
                if float(now) >= float(getattr(self, "_vtuber_next_idle_motion_t", 0.0) or 0.0):
                    self._vtuber_next_idle_motion_t = float(now) + random.uniform(14.0, 22.0)
                    try:
                        self._start_default_idle_motion()
                    finally:
                        self._boost_fps(1100)
            except Exception:
                pass
            try:
                if float(now) >= float(getattr(self, "_vtuber_next_expression_t", 0.0) or 0.0):
                    self._vtuber_next_expression_t = float(now) + random.uniform(16.0, 30.0)
                    try:
                        if hasattr(model, "SetRandomExpression"):
                            model.SetRandomExpression()
                            self._boost_fps(900)
                    except Exception:
                        pass
            except Exception:
                pass

    def _vtuber_post_update(self, now: float, dt_s: float) -> None:
        """Post-update: apply parameter tweaks (blink/breath) so they aren't overwritten."""
        if not bool(getattr(self, "_vtuber_enabled", True)):
            return
        if self._model is None:
            return

        setter = self._param_setter
        if setter is None:
            setter = self._discover_param_setter()
            self._param_setter = setter
        if setter is None:
            return

        # Eye blink (best-effort).
        try:
            self._apply_vtuber_blink(now, setter)
        except Exception:
            pass

        # VTuber: subtle idle motion + periodic gestures (nod/shake/look/lean).
        if now:
            try:
                self._vtuber_maybe_start_gesture(now)
            except Exception:
                pass
            try:
                ox, oy, oz, obx, oby, obz, oex, oey = self._vtuber_gesture_offsets(now)
            except Exception:
                ox = oy = oz = obx = oby = obz = oex = oey = 0.0

            supports_weight = bool(getattr(self, "_param_setter_supports_weight", False))
            w = 0.62 if supports_weight else 1.0
            amp_gain = 1.0 if supports_weight else 0.8

            hovering = False
            try:
                hovering = bool(self.underMouse())
            except Exception:
                hovering = False
            if hovering and (not bool(getattr(self, "_interaction_locked", False))):
                amp_gain *= 0.55

            try:
                t0 = float(getattr(self, "_vtuber_t0", 0.0) or 0.0)
            except Exception:
                t0 = 0.0
            try:
                t = max(0.0, float(now) - t0) if t0 else 0.0
            except Exception:
                t = 0.0
            tau = 2.0 * math.pi
            try:
                dt = max(0.0, min(0.1, float(dt_s)))
            except Exception:
                dt = 1.0 / 30.0

            # Base idle: seated upper-body motion.
            angle_x = 6.2 * math.sin(tau * 0.12 * t) + 1.6 * math.sin(tau * 0.31 * t + 0.4)
            angle_y = 3.2 * math.sin(tau * 0.10 * t + 1.1) + 1.1 * math.sin(tau * 0.24 * t + 2.0)
            angle_z = 2.4 * math.sin(tau * 0.09 * t + 0.2)
            body_x = 4.2 * math.sin(tau * 0.08 * t + 0.4)
            body_y = 1.6 * math.sin(tau * 0.06 * t + 0.8)
            body_z = 1.9 * math.sin(tau * 0.07 * t + 2.0)
            breath = 0.5 + 0.5 * math.sin(tau * 0.18 * t + 0.7)

            eye_x = 0.22 * math.sin(tau * 0.19 * t + 1.0) + 0.06 * math.sin(tau * 0.57 * t)
            eye_y = 0.14 * math.sin(tau * 0.17 * t + 2.3)

            # Smooth noise: breaks the "too periodic" feel.
            try:
                self._noise_ax = self._ou_step(float(getattr(self, "_noise_ax", 0.0) or 0.0), dt=dt, tau=2.2, sigma=1.1)
                self._noise_ay = self._ou_step(float(getattr(self, "_noise_ay", 0.0) or 0.0), dt=dt, tau=2.6, sigma=0.9)
                self._noise_az = self._ou_step(float(getattr(self, "_noise_az", 0.0) or 0.0), dt=dt, tau=2.8, sigma=0.7)
                self._noise_bx = self._ou_step(float(getattr(self, "_noise_bx", 0.0) or 0.0), dt=dt, tau=3.1, sigma=0.6)
                self._noise_by = self._ou_step(float(getattr(self, "_noise_by", 0.0) or 0.0), dt=dt, tau=3.4, sigma=0.5)
                self._noise_bz = self._ou_step(float(getattr(self, "_noise_bz", 0.0) or 0.0), dt=dt, tau=3.6, sigma=0.5)
                self._noise_ex = self._ou_step(float(getattr(self, "_noise_ex", 0.0) or 0.0), dt=dt, tau=1.4, sigma=0.06)
                self._noise_ey = self._ou_step(float(getattr(self, "_noise_ey", 0.0) or 0.0), dt=dt, tau=1.4, sigma=0.05)
            except Exception:
                pass
            angle_x += max(-3.0, min(3.0, float(getattr(self, "_noise_ax", 0.0) or 0.0)))
            angle_y += max(-3.0, min(3.0, float(getattr(self, "_noise_ay", 0.0) or 0.0)))
            angle_z += max(-2.2, min(2.2, float(getattr(self, "_noise_az", 0.0) or 0.0)))
            body_x += max(-1.8, min(1.8, float(getattr(self, "_noise_bx", 0.0) or 0.0)))
            body_y += max(-1.6, min(1.6, float(getattr(self, "_noise_by", 0.0) or 0.0)))
            body_z += max(-1.6, min(1.6, float(getattr(self, "_noise_bz", 0.0) or 0.0)))
            eye_x += max(-0.20, min(0.20, float(getattr(self, "_noise_ex", 0.0) or 0.0)))
            eye_y += max(-0.16, min(0.16, float(getattr(self, "_noise_ey", 0.0) or 0.0)))

            # Speaking: tiny pitch bob so the avatar "talks with the head".
            try:
                lv = float(getattr(self, "_lipsync_value", 0.0) or 0.0)
            except Exception:
                lv = 0.0
            if lv > 0.02:
                angle_y += (3.0 * min(1.0, lv)) * math.sin(tau * 0.9 * t + 0.6)
                body_x += (1.6 * min(1.0, lv)) * math.sin(tau * 0.6 * t + 1.2)

            # Eye micro-saccade: quick tiny glances.
            try:
                now_f = float(now)
            except Exception:
                now_f = 0.0
            if now_f:
                try:
                    if self._saccade_end_t <= 0.0 and now_f >= float(getattr(self, "_saccade_next_t", 0.0) or 0.0):
                        self._saccade_start_t = now_f
                        self._saccade_end_t = now_f + random.uniform(0.22, 0.34)
                        self._saccade_to_x = random.uniform(-0.18, 0.18)
                        self._saccade_to_y = random.uniform(-0.12, 0.12)
                        self._saccade_from_x = float(getattr(self, "_pose_eye_x", 0.0) or 0.0)
                        self._saccade_from_y = float(getattr(self, "_pose_eye_y", 0.0) or 0.0)
                except Exception:
                    pass

                if float(getattr(self, "_saccade_end_t", 0.0) or 0.0) > 0.0:
                    st = float(getattr(self, "_saccade_start_t", 0.0) or 0.0)
                    et = float(getattr(self, "_saccade_end_t", 0.0) or 0.0)
                    dur = max(1e-3, et - st)
                    p = max(0.0, min(1.0, (now_f - st) / dur))

                    def _smoothstep(x: float) -> float:
                        x = max(0.0, min(1.0, float(x)))
                        return x * x * (3.0 - 2.0 * x)

                    if p < 0.18:
                        env = _smoothstep(p / 0.18)
                    elif p < 0.70:
                        env = 1.0
                    else:
                        env = 1.0 - _smoothstep((p - 0.70) / 0.30)

                    eye_x += float(getattr(self, "_saccade_to_x", 0.0) or 0.0) * env
                    eye_y += float(getattr(self, "_saccade_to_y", 0.0) or 0.0) * env

                    if now_f >= et:
                        self._saccade_end_t = 0.0
                        self._saccade_start_t = 0.0
                        self._saccade_next_t = now_f + random.uniform(0.9, 2.2)

            # Gesture overlay.
            angle_x += ox
            angle_y += oy
            angle_z += oz
            body_x += obx
            body_y += oby
            body_z += obz
            eye_x += oex
            eye_y += oey

            angle_x *= amp_gain
            angle_y *= amp_gain
            angle_z *= amp_gain
            body_x *= amp_gain
            body_y *= amp_gain
            body_z *= amp_gain
            eye_x *= amp_gain
            eye_y *= amp_gain

            # Clamp to common Cubism ranges.
            angle_x = max(-30.0, min(30.0, float(angle_x)))
            angle_y = max(-30.0, min(30.0, float(angle_y)))
            angle_z = max(-30.0, min(30.0, float(angle_z)))
            body_x = max(-20.0, min(20.0, float(body_x)))
            body_y = max(-20.0, min(20.0, float(body_y)))
            body_z = max(-20.0, min(20.0, float(body_z)))
            breath = max(0.0, min(1.0, float(breath)))
            eye_x = max(-1.0, min(1.0, float(eye_x)))
            eye_y = max(-1.0, min(1.0, float(eye_y)))

            # Smooth pose blending to avoid robotic movement.
            try:
                gesture_active = float(getattr(self, "_vtuber_gesture_end_t", 0.0) or 0.0) > float(now_f)
            except Exception:
                gesture_active = False
            k_head = 11.5 * (1.35 if gesture_active else 1.0)
            k_body = 8.5 * (1.25 if gesture_active else 1.0)
            k_eye = 16.0 * (1.4 if float(getattr(self, "_saccade_end_t", 0.0) or 0.0) > 0.0 else 1.0)
            k_breath = 5.0
            if lv > 0.05:
                k_head *= 1.25
                k_body *= 1.15

            self._pose_angle_x = self._smooth_to(float(getattr(self, "_pose_angle_x", 0.0) or 0.0), angle_x, k=k_head, dt=dt)
            self._pose_angle_y = self._smooth_to(float(getattr(self, "_pose_angle_y", 0.0) or 0.0), angle_y, k=k_head, dt=dt)
            self._pose_angle_z = self._smooth_to(float(getattr(self, "_pose_angle_z", 0.0) or 0.0), angle_z, k=k_head, dt=dt)
            self._pose_body_x = self._smooth_to(float(getattr(self, "_pose_body_x", 0.0) or 0.0), body_x, k=k_body, dt=dt)
            self._pose_body_y = self._smooth_to(float(getattr(self, "_pose_body_y", 0.0) or 0.0), body_y, k=k_body, dt=dt)
            self._pose_body_z = self._smooth_to(float(getattr(self, "_pose_body_z", 0.0) or 0.0), body_z, k=k_body, dt=dt)
            self._pose_eye_x = self._smooth_to(float(getattr(self, "_pose_eye_x", 0.0) or 0.0), eye_x, k=k_eye, dt=dt)
            self._pose_eye_y = self._smooth_to(float(getattr(self, "_pose_eye_y", 0.0) or 0.0), eye_y, k=k_eye, dt=dt)
            self._pose_breath = self._smooth_to(float(getattr(self, "_pose_breath", 0.5) or 0.5), breath, k=k_breath, dt=dt)

            for pid, val in (
                ("ParamAngleX", self._pose_angle_x),
                ("ParamAngleY", self._pose_angle_y),
                ("ParamAngleZ", self._pose_angle_z),
                ("ParamBodyAngleX", self._pose_body_x),
                ("ParamBodyAngleY", self._pose_body_y),
                ("ParamBodyAngleZ", self._pose_body_z),
                ("ParamBreath", self._pose_breath),
                ("ParamEyeBallX", self._pose_eye_x),
                ("ParamEyeBallY", self._pose_eye_y),
            ):
                self._set_param_cached(setter, pid, float(val), w)

    def _apply_vtuber_blink(self, now: float, setter) -> None:
        if self._vtuber_blink_supported is False:
            return

        if not now:
            return

        try:
            now_f = float(now)
        except Exception:
            return

        # Schedule next blink if we're idle.
        if self._vtuber_blink_end_t <= 0.0 and now_f >= float(getattr(self, "_vtuber_blink_next_t", 0.0) or 0.0):
            close_s = 0.055
            open_s = 0.095
            hold_s = float(getattr(self, "_vtuber_blink_hold_s", 0.018) or 0.018)
            self._vtuber_blink_start_t = now_f
            self._vtuber_blink_end_t = now_f + close_s + hold_s + open_s

        open_v = 1.0
        if self._vtuber_blink_end_t > 0.0:
            close_s = 0.055
            open_s = 0.095
            hold_s = float(getattr(self, "_vtuber_blink_hold_s", 0.018) or 0.018)
            t = max(0.0, now_f - float(getattr(self, "_vtuber_blink_start_t", now_f)))

            def _smoothstep(x: float) -> float:
                x = max(0.0, min(1.0, float(x)))
                return x * x * (3.0 - 2.0 * x)

            if t < close_s:
                p = _smoothstep(t / close_s)
                open_v = 1.0 - p
            elif t < close_s + hold_s:
                open_v = 0.0
            else:
                p = _smoothstep((t - close_s - hold_s) / max(1e-6, open_s))
                open_v = p

            if now_f >= float(getattr(self, "_vtuber_blink_end_t", 0.0) or 0.0):
                self._vtuber_blink_end_t = 0.0
                self._vtuber_blink_start_t = 0.0
                # Natural variation: occasionally do a quick double-blink.
                if random.random() < 0.18:
                    self._vtuber_blink_next_t = now_f + random.uniform(0.22, 0.45)
                else:
                    self._vtuber_blink_next_t = now_f + random.uniform(2.4, 5.2)
                open_v = 1.0

        # Apply blink to common parameters. Some models use only one eye parameter; try both.
        ok = 0
        try:
            setter("ParamEyeLOpen", float(open_v), 1.0)
            ok += 1
        except Exception:
            pass
        try:
            setter("ParamEyeROpen", float(open_v), 1.0)
            ok += 1
        except Exception:
            pass
        if ok <= 0:
            self._vtuber_blink_supported = False
        else:
            self._vtuber_blink_supported = True

    def _apply_lipsync(self, dt_s: float) -> None:
        if self._model is None:
            return

        if self._lipsync_supported is False:
            return

        target = float(getattr(self, "_lipsync_target", 0.0) or 0.0)
        value = float(getattr(self, "_lipsync_value", 0.0) or 0.0)
        try:
            dt = max(0.0, min(0.1, float(dt_s)))
        except Exception:
            dt = 1.0 / 30.0

        # Smooth: fast open, slightly slower close for a more "vtuber" mouth feel.
        k_open = 16.0
        k_close = 10.0
        k = k_open if target > value else k_close
        try:
            alpha = 1.0 - math.exp(-k * dt)
        except Exception:
            alpha = min(1.0, dt * 12.0)
        value = value + (target - value) * max(0.0, min(1.0, alpha))
        self._lipsync_value = max(0.0, min(1.0, float(value)))

        setter = self._param_setter
        if setter is None:
            setter = self._discover_param_setter()
            self._param_setter = setter
            self._lipsync_supported = bool(setter is not None)
        if setter is None:
            return

        # Common Cubism 3 params:
        # - ParamMouthOpenY: [0..1] open amount
        # - ParamMouthForm: [-1..1] smile/frown; keep a gentle default
        try:
            setter("ParamMouthOpenY", float(self._lipsync_value), 1.0)
        except Exception:
            self._lipsync_supported = False
            return
        # Do not force `ParamMouthForm` here: expressions often control mouth shape.
        # For lip-sync we only need the open amount; keeping form free makes expressions visible.

    def _discover_param_setter(self):
        """Best-effort discover a parameter setter on the current live2d-py model."""
        model = self._model
        if model is None:
            return None

        objs: list[Any] = []
        try:
            objs.append(model)
        except Exception:
            pass

        for attr in ("model", "_model", "_impl", "_core", "cubism_model"):
            try:
                obj = getattr(model, attr, None)
                if obj is not None and obj not in objs:
                    objs.append(obj)
            except Exception:
                pass

        try:
            get_model = getattr(model, "GetModel", None)
            if callable(get_model):
                obj = get_model()
                if obj is not None and obj not in objs:
                    objs.append(obj)
        except Exception:
            pass

        test_id = "ParamMouthOpenY"

        # 1) Direct setter by id.
        for obj in objs:
            for name in ("SetParameterValueById", "SetParameterValueByID", "SetParameterValue"):
                try:
                    fn = getattr(obj, name, None)
                    if not callable(fn):
                        continue

                    try:
                        fn(test_id, 0.0)
                        self._param_setter_supports_weight = False
                        return lambda pid, v, w=1.0, _fn=fn: _fn(pid, float(v))
                    except TypeError:
                        try:
                            fn(test_id, 0.0, 1.0)
                            self._param_setter_supports_weight = True
                            return lambda pid, v, w=1.0, _fn=fn: _fn(pid, float(v), float(w))
                        except Exception:
                            continue
                except Exception:
                    continue

        # 2) Index based.
        for obj in objs:
            try:
                get_idx = getattr(obj, "GetParameterIndex", None)
                set_by_idx = getattr(obj, "SetParameterValueByIndex", None)
                if not callable(get_idx) or not callable(set_by_idx):
                    continue
                idx = int(get_idx(test_id))
                try:
                    set_by_idx(idx, 0.0)
                    self._param_setter_supports_weight = False
                    return lambda pid, v, w=1.0, _obj=obj, _get_idx=get_idx, _set=set_by_idx: _set(
                        int(_get_idx(pid)),
                        float(v),
                    )
                except TypeError:
                    set_by_idx(idx, 0.0, 1.0)
                    self._param_setter_supports_weight = True
                    return lambda pid, v, w=1.0, _obj=obj, _get_idx=get_idx, _set=set_by_idx: _set(
                        int(_get_idx(pid)),
                        float(v),
                        float(w),
                    )
            except Exception:
                continue

        return None

    def _end_pan(self) -> None:
        try:
            if self._panning:
                self._panning = False
                self._pan_button = None
                self._pan_last_pos = None
                self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        except Exception:
            pass

    def _boost_fps(self, duration_ms: int = 1200) -> None:
        if self._paused or not self._ready:
            return
        try:
            if self._tick_timer.isActive():
                self._tick_timer.setInterval(self._tick_ms_boost)
            self._fps_boost_reset.start(max(200, int(duration_ms)))
        except Exception:
            pass

    def _restore_fps_normal(self) -> None:
        if self._paused or not self._ready:
            return
        try:
            if self._tick_timer.isActive():
                self._tick_timer.setInterval(self._tick_ms_normal)
        except Exception:
            pass

    def _apply_default_view(self, ww: int, hh: int) -> None:
        """Apply a pleasant default view (scale/offset) for the current viewport."""

        if self._model is None:
            return

        if not self._auto_view_enabled:
            return

        try:
            # Use logical pixels for heuristics so HiDPI doesn't change framing.
            logical_w = float(self.width() or 0)
            logical_h = float(self.height() or 0)
            if logical_w <= 0 or logical_h <= 0:
                logical_w = float(ww)
                logical_h = float(hh)
            aspect = float(logical_w) / float(max(1.0, logical_h))
        except Exception:
            aspect = 0.5

        def clamp(x: float, lo: float, hi: float) -> float:
            return max(lo, min(hi, float(x)))

        # Height matters a lot: a short viewport shouldn't be aggressively zoomed-in.
        height_factor = clamp((float(logical_h) - 520.0) / 220.0, 0.0, 1.0)
        aspect_factor = clamp((float(aspect) - 0.55) / 0.45, 0.0, 1.0)

        if self._view_mode == self.VIEW_MODE_PORTRAIT:
            base_scale = 1.12 + 0.38 * height_factor + 0.14 * aspect_factor
            base_offset_x = 0.0
            base_offset_y = -0.10 - 0.10 * height_factor
        else:
            # Full-body framing: conservative zoom by default.
            base_scale = 0.90 + 0.20 * height_factor + 0.06 * aspect_factor
            base_offset_x = 0.0
            base_offset_y = -0.03 - 0.06 * height_factor

        scale = float(base_scale) * float(self._user_scale_mul)
        offset_x = float(base_offset_x) + float(self._user_offset_x)
        offset_y = float(base_offset_y) + float(self._user_offset_y)

        scale = clamp(scale, 0.55, 2.2)
        offset_x = clamp(offset_x, -0.8, 0.8)
        offset_y = clamp(offset_y, -0.8, 0.6)

        try:
            if hasattr(self._model, "SetScale"):
                self._model.SetScale(float(scale))
        except Exception:
            pass
        try:
            if hasattr(self._model, "SetOffset"):
                self._model.SetOffset(float(offset_x), float(offset_y))
        except Exception:
            pass

    def _destroy_model(self) -> None:
        if self._model is None:
            return
        try:
            if hasattr(self._model, "DestroyRenderer"):
                self._model.DestroyRenderer()
        except Exception:
            pass
        self._model = None

    def _prepare_ascii_model_json(self, src_model_json: Path) -> Path:
        """Return a model3.json path that is safe for Cubism's limited JSON parser.

        Empirically, CubismJson may reject Unicode (either UTF-8 bytes or \\u escapes) and
        can even crash on invalid documents. The shipped model folder has Chinese-named
        `.exp3.json` / `.motion3.json` files, so we generate an ASCII-only wrapper and
        copy only those small files into `data/live2d_cache/`.
        """

        try:
            model_dir = src_model_json.parent
            exp_files = sorted(model_dir.glob("*.exp3.json"))
            motion_files = sorted(model_dir.glob("*.motion3.json"))
            if not exp_files and not motion_files:
                return src_model_json

            needs_ascii = False
            for p in exp_files + motion_files:
                if not _is_ascii(p.name):
                    needs_ascii = True
                    break
            if not needs_ascii:
                return src_model_json

            repo_root = _repo_root()
            cache_root = repo_root / "data" / "live2d_cache" / f"{model_dir.name}_ascii"
            expressions_dir = cache_root / "expressions"
            motions_dir = cache_root / "motions"
            sanitized_path = cache_root / "model.model3.json"

            # Fast path: reuse an up-to-date cache wrapper to avoid re-copying assets on every run.
            try:
                if sanitized_path.exists():
                    max_src_mtime = float(src_model_json.stat().st_mtime)
                    for p in exp_files + motion_files:
                        try:
                            max_src_mtime = max(max_src_mtime, float(p.stat().st_mtime))
                        except Exception:
                            pass
                    cache_mtime = float(sanitized_path.stat().st_mtime)

                    expected_expr = [
                        expressions_dir / f"expr_{i:02d}.exp3.json" for i in range(1, len(exp_files) + 1)
                    ]
                    expected_motion = [
                        motions_dir / f"idle_{i:02d}.motion3.json" for i in range(1, len(motion_files) + 1)
                    ]
                    if cache_mtime >= max_src_mtime and all(p.exists() for p in expected_expr + expected_motion):
                        return sanitized_path
            except Exception:
                pass

            # Parse the base model json (usually ASCII-only, safe for Python parser).
            try:
                base = json.loads(src_model_json.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Failed to parse base model json for sanitizing: %s", exc)
                return src_model_json

            expressions_dir.mkdir(parents=True, exist_ok=True)
            motions_dir.mkdir(parents=True, exist_ok=True)

            src_refs = base.get("FileReferences") or {}
            new_refs: dict[str, Any] = {}

            def from_model_ref(ref: str) -> str:
                # Convert model-relative file refs to paths relative to cache_root.
                return _relpath_posix(model_dir / Path(ref), cache_root)

            for key, value in src_refs.items():
                if key in {"Expressions", "Motions"}:
                    continue
                if isinstance(value, str):
                    new_refs[key] = from_model_ref(value)
                elif isinstance(value, list):
                    converted: list[Any] = []
                    for item in value:
                        if isinstance(item, str):
                            converted.append(from_model_ref(item))
                        else:
                            converted.append(item)
                    new_refs[key] = converted
                else:
                    new_refs[key] = value

            # Copy non-ASCII expression files into cache with ASCII names.
            expressions: list[dict[str, str]] = []
            for idx, src_path in enumerate(exp_files, start=1):
                name = f"expr_{idx:02d}"
                dest_name = f"{name}.exp3.json"
                dest_path = expressions_dir / dest_name
                try:
                    shutil.copy2(src_path, dest_path)
                except Exception:
                    try:
                        shutil.copyfile(src_path, dest_path)
                    except Exception as exc:
                        logger.warning("Failed to copy expression %s: %s", src_path, exc)
                        continue
                expressions.append({"Name": name, "File": f"expressions/{dest_name}"})
            if expressions:
                new_refs["Expressions"] = expressions

            # Copy non-ASCII motion files into cache with ASCII names.
            if motion_files:
                idle: list[dict[str, str]] = []
                for idx, src_path in enumerate(motion_files, start=1):
                    dest_name = f"idle_{idx:02d}.motion3.json"
                    dest_path = motions_dir / dest_name
                    try:
                        shutil.copy2(src_path, dest_path)
                    except Exception:
                        try:
                            shutil.copyfile(src_path, dest_path)
                        except Exception as exc:
                            logger.warning("Failed to copy motion %s: %s", src_path, exc)
                            continue
                    idle.append({"File": f"motions/{dest_name}"})
                if idle:
                    new_refs["Motions"] = {"Idle": idle}

            sanitized: dict[str, Any] = {
                "Version": int(base.get("Version") or 3),
                "FileReferences": new_refs,
            }
            if "Groups" in base:
                sanitized["Groups"] = base["Groups"]

            sanitized_path.write_text(
                json.dumps(sanitized, ensure_ascii=True, indent=2),
                encoding="utf-8",
            )
            return sanitized_path
        except Exception as exc:
            logger.warning("Live2D model sanitizer failed: %s", exc, exc_info=True)
            return src_model_json
