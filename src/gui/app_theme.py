"""Application-level stylesheet for MintChat GUI.

This module applies lightweight global QSS for widgets that are not always styled
locally (menus, tooltips, scrollbars). Component-specific QSS remains in each
widget/module.
"""

from __future__ import annotations

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QToolTip

from .material_design_enhanced import MD3_ENHANCED_COLORS, MD3_ENHANCED_RADIUS, get_typography_css
from .theme_manager import get_active_theme_name, THEME_ANIME


def build_global_stylesheet() -> str:
    c = MD3_ENHANCED_COLORS
    r = MD3_ENHANCED_RADIUS

    # Keep this QSS minimal: global styles should not fight with per-widget styles.
    qss = f"""
        QToolTip {{
            /* Use background-color instead of background to avoid platform-specific tooltip palette issues. */
            background-color: {c['surface_container_highest']};
            color: {c['on_surface']};
            border: 1px solid {c['outline_variant']};
            border-radius: {r['md']};
            padding: 8px 10px;
            {get_typography_css('label_medium')}
        }}
        QToolTip QLabel {{
            background: transparent;
            color: {c['on_surface']};
        }}

        QMenu {{
            background: {c['surface_container']};
            color: {c['on_surface']};
            border: 1px solid {c['outline_variant']};
            border-radius: {r['lg']};
            padding: 6px;
        }}
        QMenu::item {{
            padding: 8px 12px;
            border-radius: {r['md']};
        }}
        QMenu::item:selected {{
            background: {c['primary_container']};
            color: {c['on_primary_container']};
        }}
        QMenu::separator {{
            height: 1px;
            background: {c['outline_variant']};
            margin: 6px 8px;
        }}

        QScrollBar:vertical {{
            background: transparent;
            width: 10px;
            margin: 4px 2px;
        }}
        QScrollBar::handle:vertical {{
            background: {c['outline_variant']};
            border-radius: 5px;
            min-height: 32px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {c['outline']};
        }}
        QScrollBar::handle:vertical:pressed {{
            background: {c['primary']};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: none;
        }}

        QLineEdit, QTextEdit {{
            background: {c['surface_container_high']};
            color: {c['on_surface']};
            border: 1px solid {c['outline_variant']};
            border-radius: {r['md']};
            padding: 8px 10px;
            selection-background-color: {c['primary_container']};
            selection-color: {c['on_primary_container']};
        }}
        QLineEdit:focus, QTextEdit:focus {{
            border: 2px solid {c['primary']};
            padding: 7px 9px;
        }}
    """

    if get_active_theme_name() == THEME_ANIME:
        # Anime theme: slightly stronger highlight for selected menu item.
        qss += f"""
            QMenu::item:selected {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c['primary_container']},
                    stop:1 {c['secondary_container']}
                );
                color: {c['on_primary_container']};
            }}
        """

    return qss


def apply_app_theme(app: QApplication) -> None:
    """Apply global QSS. Safe to call multiple times."""
    if app is None:
        return

    app.setStyleSheet(build_global_stylesheet())
    _apply_tooltip_palette()


def _apply_tooltip_palette() -> None:
    """Force a readable tooltip palette even when OS theme/palette is dark."""
    try:
        c = MD3_ENHANCED_COLORS
        tooltip_bg = QColor(c["surface_container_highest"])
        tooltip_fg = QColor(c["on_surface"])
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.ToolTipBase, tooltip_bg)
        palette.setColor(QPalette.ColorRole.ToolTipText, tooltip_fg)
        QToolTip.setPalette(palette)
    except Exception:
        return
