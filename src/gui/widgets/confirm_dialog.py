"""
MintChat - Themed confirm dialog (MD3 enhanced).

Used for confirmation flows (e.g., logout) where native QMessageBox styling
doesn't match the app theme.

This dialog is frameless and supports an optional custom background image.

Background file location (auto-created):
  - <data_dir>/gui/backgrounds/

Background key lookup:
  - key without extension (e.g. "logout_confirm") will try:
    logout_confirm.png/jpg/jpeg/webp/bmp
  - key with extension (e.g. "logout_confirm.png") will look for that file
    under the folder above (or accept an absolute path).

Sizing:
  - width = parent.width * size_ratio, height = parent.height * size_ratio
  - fallback: 520x300
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QFont, QGuiApplication, QImageReader, QPainterPath, QPixmap, QRegion
from PyQt6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
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
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ConfirmDialogTexts:
    title: str
    message: str
    confirm: str = "确定"
    cancel: str = "取消"


class ConfirmDialog(QDialog):
    """A themed confirm dialog with two actions (frameless)."""

    def __init__(
        self,
        texts: ConfirmDialogTexts,
        *,
        parent=None,
        icon_ligature: str = "help",
        size_ratio: float = 0.5,
        default_to_cancel: bool = True,
        background_key: str | None = None,
    ) -> None:
        super().__init__(parent)
        self._texts = texts
        self._size_ratio = float(size_ratio)
        self._default_to_cancel = bool(default_to_cancel)
        self._background_key = str(background_key or "").strip()

        self._background_original: QPixmap | None = None
        self._background_scaled: QPixmap | None = None
        self._background_scaled_size: tuple[int, int] | None = None

        self._drag_start_pos = None
        self._drag_start_window_pos = None
        self._corner_radius_px = self._parse_radius_px(MD3_ENHANCED_RADIUS.get("xl", "16px"))

        self.setObjectName("confirmDialog")
        self.setWindowTitle(texts.title)
        self.setModal(True)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        container = QWidget(self)
        container.setObjectName("confirmContainer")
        container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        root.addWidget(container, 1)

        grid = QGridLayout(container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)

        self._bg_label = QLabel(container)
        self._bg_label.setObjectName("confirmBackground")
        self._bg_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._bg_label.setVisible(False)
        self._bg_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.card = QWidget(container)
        self.card.setObjectName("confirmCard")
        self.card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        grid.addWidget(self._bg_label, 0, 0)
        grid.addWidget(self.card, 0, 0)
        self._bg_label.lower()

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(28, 26, 28, 22)
        card_layout.setSpacing(16)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(14)

        icon = QLabel(icon_ligature, self.card)
        icon.setObjectName("confirmIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_font = QFont("Material Symbols Outlined")
        icon_font.setPixelSize(26)
        icon.setFont(icon_font)
        icon.setFixedSize(52, 52)

        title = QLabel(texts.title, self.card)
        title.setObjectName("confirmTitle")
        title.setWordWrap(True)

        self.close_btn = QPushButton("close", self.card)
        self.close_btn.setObjectName("confirmClose")
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_btn.setToolTip("关闭")
        close_font = QFont("Material Symbols Outlined")
        close_font.setPixelSize(20)
        self.close_btn.setFont(close_font)
        self.close_btn.setFixedSize(34, 34)
        self.close_btn.clicked.connect(self.reject)

        header.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        header.addWidget(title, 1, Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(self.close_btn, 0, Qt.AlignmentFlag.AlignTop)
        card_layout.addLayout(header)

        message = QLabel(texts.message, self.card)
        message.setObjectName("confirmMessage")
        message.setWordWrap(True)
        message.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        card_layout.addWidget(message, 1)

        card_layout.addStretch(1)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(12)
        buttons.addStretch(1)

        self.cancel_btn = QPushButton(texts.cancel, self.card)
        self.cancel_btn.setObjectName("confirmSecondary")
        self.cancel_btn.setMinimumWidth(120)
        self.cancel_btn.clicked.connect(self.reject)

        self.confirm_btn = QPushButton(texts.confirm, self.card)
        self.confirm_btn.setObjectName("confirmPrimary")
        self.confirm_btn.setMinimumWidth(140)
        self.confirm_btn.clicked.connect(self.accept)

        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(self.confirm_btn)
        card_layout.addLayout(buttons)

        self._apply_styles()
        self._background_original = self._load_background_pixmap()
        self._apply_sizing(parent)
        self._update_background_scaled()
        self._apply_window_mask()
        self._apply_default_focus()

    @staticmethod
    def _parse_radius_px(value: object) -> int:
        try:
            s = str(value).strip().lower().replace("px", "")
            return max(0, int(float(s)))
        except Exception:
            return 0

    def _apply_window_mask(self) -> None:
        try:
            radius = int(self._corner_radius_px)
            if radius <= 0:
                self.clearMask()
                return

            rect = self.rect()
            w = int(rect.width())
            h = int(rect.height())
            if w <= 0 or h <= 0:
                return

            path = QPainterPath()
            path.addRoundedRect(0.0, 0.0, float(w), float(h), float(radius), float(radius))
            region = QRegion(path.toFillPolygon().toPolygon())
            self.setMask(region)
        except Exception:
            pass

    def _background_dir(self) -> Path:
        try:
            from src.config.settings import settings as runtime_settings

            base = Path(getattr(runtime_settings, "data_dir", "./data") or "./data")
        except Exception:
            base = Path("./data")
        return base / "gui" / "backgrounds"

    def _available_geometry(self, parent) -> QRect | None:
        try:
            if parent is not None and hasattr(parent, "screen"):
                screen = parent.screen()
                if screen is not None:
                    return screen.availableGeometry()
        except Exception:
            pass

        try:
            if parent is not None:
                parent_center = parent.frameGeometry().center()
                screen = QGuiApplication.screenAt(parent_center)
                if screen is not None:
                    return screen.availableGeometry()
        except Exception:
            pass

        try:
            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                return screen.availableGeometry()
        except Exception:
            pass

        return None

    def _load_background_pixmap(self) -> QPixmap | None:
        key = self._background_key
        if not key:
            return None

        bg_dir = self._background_dir()
        try:
            bg_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        candidates: list[Path] = []
        path_key = Path(key)
        if path_key.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
            candidates.append(path_key if path_key.is_absolute() else (bg_dir / path_key.name))
        else:
            for ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
                candidates.append(bg_dir / f"{key}{ext}")

        for cand in candidates:
            try:
                if not cand.exists():
                    continue
                reader = QImageReader(str(cand))
                reader.setAutoTransform(True)
                image = reader.read()
                if image.isNull():
                    continue
                return QPixmap.fromImage(image)
            except Exception:
                continue

        logger.debug("confirm dialog background not found for key=%s", key)
        return None

    def _update_background_scaled(self) -> None:
        pixmap = self._background_original
        if pixmap is None or pixmap.isNull():
            self._bg_label.setVisible(False)
            return

        target = self.size()
        w = int(target.width())
        h = int(target.height())
        if w <= 0 or h <= 0:
            return

        if self._background_scaled_size == (w, h) and self._background_scaled is not None:
            self._bg_label.setPixmap(self._background_scaled)
            self._bg_label.setVisible(True)
            return

        scaled = pixmap.scaled(
            target,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._background_scaled = scaled
        self._background_scaled_size = (w, h)
        self._bg_label.setPixmap(scaled)
        self._bg_label.setVisible(True)

    def resizeEvent(self, event):  # noqa: N802 - Qt API naming
        super().resizeEvent(event)
        try:
            self._update_background_scaled()
            self._apply_window_mask()
        except Exception:
            pass

    def showEvent(self, event):  # noqa: N802 - Qt API naming
        super().showEvent(event)
        try:
            self.raise_()
            self.activateWindow()
            self._apply_window_mask()
        except Exception:
            pass

    def _apply_styles(self) -> None:
        c = MD3_ENHANCED_COLORS
        r = MD3_ENHANCED_RADIUS

        card_bg = c["frosted_glass_light"]
        border = qss_rgba(c["outline_variant"], 0.95)

        primary_hover = c.get("primary_60", c["primary"])
        primary_pressed = c.get("primary_70", c["primary"])
        secondary_hover = c.get("surface_container_highest", c["surface_container_high"])

        self.setStyleSheet(
            f"""
            QDialog#confirmDialog {{
                background: {c['background']};
            }}
            QWidget#confirmContainer {{
                background: {c['background']};
            }}
            QWidget#confirmCard {{
                background: {card_bg};
                border: 1px solid {border};
                border-radius: {r['xl']};
            }}
            QLabel#confirmIcon {{
                color: {c['primary']};
                background: {c['primary_container']};
                border-radius: 26px;
                border: 1px solid {qss_rgba(c['primary'], 0.22)};
            }}
            QLabel#confirmTitle {{
                color: {c['on_surface']};
                {get_typography_css('headline_small')}
                font-weight: 650;
            }}
            QLabel#confirmMessage {{
                color: {c['on_surface_variant']};
                {get_typography_css('body_large')}
            }}
            QPushButton#confirmClose {{
                background: transparent;
                border: none;
                border-radius: {r['lg']};
                color: {c['on_surface_variant']};
            }}
            QPushButton#confirmClose:hover {{
                background: {qss_rgba(c['primary'], 0.10)};
                color: {c['on_surface']};
            }}
            QPushButton#confirmClose:pressed {{
                background: {qss_rgba(c['primary'], 0.16)};
            }}
            QPushButton#confirmPrimary {{
                background: {c['primary']};
                color: {c['on_primary']};
                border: none;
                border-radius: {r['lg']};
                padding: 10px 18px;
                {get_typography_css('label_large')}
                font-weight: 600;
            }}
            QPushButton#confirmPrimary:hover {{
                background: {primary_hover};
            }}
            QPushButton#confirmPrimary:pressed {{
                background: {primary_pressed};
            }}
            QPushButton#confirmPrimary:disabled {{
                background: {qss_rgba(c['outline_variant'], 0.8)};
                color: {qss_rgba(c['on_surface_variant'], 0.6)};
            }}
            QPushButton#confirmSecondary {{
                background: {c['surface_container_high']};
                color: {c['on_surface']};
                border: 1px solid {qss_rgba(c['outline_variant'], 0.95)};
                border-radius: {r['lg']};
                padding: 10px 18px;
                {get_typography_css('label_large')}
                font-weight: 550;
            }}
            QPushButton#confirmSecondary:hover {{
                background: {secondary_hover};
            }}
            QPushButton#confirmSecondary:pressed {{
                background: {qss_rgba(c['outline_variant'], 0.85)};
            }}
            QPushButton#confirmSecondary:focus, QPushButton#confirmPrimary:focus {{
                outline: none;
                border: 2px solid {qss_rgba(c['primary'], 0.6)};
            }}
            """
        )

    def _apply_sizing(self, parent) -> None:
        ratio = max(0.2, min(self._size_ratio, 1.0))
        w = 520
        h = 300
        try:
            if parent is not None:
                w = int(parent.width() * ratio)
                h = int(parent.height() * ratio)
        except Exception:
            pass

        if w <= 0 or h <= 0:
            w, h = 520, 300

        try:
            screen = None
            if parent is not None and hasattr(parent, "screen"):
                screen = parent.screen()
            if screen is None:
                screen = QGuiApplication.primaryScreen()
            if screen is not None:
                avail: QRect = screen.availableGeometry()
                w = min(w, max(320, int(avail.width() * 0.9)))
                h = min(h, max(220, int(avail.height() * 0.9)))
        except Exception:
            pass

        self.setFixedSize(int(w), int(h))

        try:
            avail = self._available_geometry(parent)
            if parent is not None:
                center = parent.frameGeometry().center()
                cx, cy = int(center.x()), int(center.y())
            elif avail is not None:
                center = avail.center()
                cx, cy = int(center.x()), int(center.y())
            else:
                cx, cy = 0, 0

            x = int(cx - self.width() // 2)
            y = int(cy - self.height() // 2)

            if avail is not None:
                margin = 12
                min_x = int(avail.left() + margin)
                min_y = int(avail.top() + margin)
                max_x = int(avail.right() - margin - self.width() + 1)
                max_y = int(avail.bottom() - margin - self.height() + 1)
                if max_x >= min_x:
                    x = max(min_x, min(x, max_x))
                if max_y >= min_y:
                    y = max(min_y, min(y, max_y))

            self.move(int(x), int(y))
        except Exception:
            pass

    def mousePressEvent(self, event):  # noqa: N802 - Qt API naming
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                self._drag_start_pos = event.globalPosition().toPoint()
                self._drag_start_window_pos = self.frameGeometry().topLeft()
        except Exception:
            pass
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802 - Qt API naming
        try:
            if (
                event.buttons() & Qt.MouseButton.LeftButton
                and self._drag_start_pos is not None
                and self._drag_start_window_pos is not None
            ):
                delta = event.globalPosition().toPoint() - self._drag_start_pos
                # Only allow dragging from the top area to avoid fighting the buttons.
                if event.position().y() <= 72:
                    self.move(self._drag_start_window_pos + delta)
                    return
        except Exception:
            pass
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802 - Qt API naming
        try:
            self._drag_start_pos = None
            self._drag_start_window_pos = None
        except Exception:
            pass
        super().mouseReleaseEvent(event)

    def _apply_default_focus(self) -> None:
        try:
            if self._default_to_cancel:
                self.cancel_btn.setDefault(True)
                self.cancel_btn.setAutoDefault(True)
                self.cancel_btn.setFocus()
            else:
                self.confirm_btn.setDefault(True)
                self.confirm_btn.setAutoDefault(True)
                self.confirm_btn.setFocus()
        except Exception:
            pass
