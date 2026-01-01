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
from .tooltip_manager import install_unified_tooltips


def build_global_stylesheet() -> str:
    c = MD3_ENHANCED_COLORS
    r = MD3_ENHANCED_RADIUS

    # Keep this QSS minimal: global styles should not fight with per-widget styles.
    qss = f"""
        QToolTip {{
            /* Prefer palette-driven colors to stay readable across OS themes
               (esp. Windows dark mode). */
            border: 1px solid {c['outline_variant']};
            border-radius: {r['md']};
            padding: 8px 10px;
            {get_typography_css('label_medium')}
        }}
        QToolTip QLabel {{
            background: transparent;
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
    _apply_tooltip_palette(app)
    install_unified_tooltips(app)


def _apply_tooltip_palette(app: QApplication | None = None) -> None:
    """Ensure tooltips stay readable across OS themes and widget styles.

    Windows dark mode (and some platform styles) may render native-looking tooltip backgrounds
    that are effectively dark, even when a custom palette is set.
    If we force a dark tooltip text color in that scenario, tooltips can become unreadable
    ("black on black"). We therefore:

    - Detect whether the current tooltip base color is dark.
    - Choose a contrasting tooltip text color.
    - Apply the tooltip palette both to QToolTip and the QApplication palette so all tooltip widgets
      (including platform-specific ones) remain consistent.
    """
    try:
        c = MD3_ENHANCED_COLORS

        try:
            app = app or QApplication.instance()
        except Exception:
            app = None
        if app is None:
            return

        def _luma(color: QColor) -> float:
            try:
                r = float(color.red())
                g = float(color.green())
                b = float(color.blue())
            except Exception:
                return 0.0
            return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0

        try:
            pal0 = app.palette()
            sys_tip_bg = pal0.color(QPalette.ColorGroup.Inactive, QPalette.ColorRole.ToolTipBase)
        except Exception:
            sys_tip_bg = QColor("#000000")

        # If the system tooltip base is dark, prefer a dark tooltip palette with a light text color
        # to
        # guarantee readability even when the platform style ignores palette background overrides.
        if _luma(sys_tip_bg) < 0.42:
            tooltip_bg = QColor(c.get("on_surface", "#1A1C1E"))
            tooltip_fg = QColor(c.get("surface_bright", "#FFFFFF"))
        else:
            tooltip_bg = QColor(c.get("surface_container_highest", "#F3F3F3"))
            tooltip_fg = QColor(c.get("on_surface", "#000000"))

        try:
            app_palette = app.palette()
            app_palette.setColor(QPalette.ColorRole.ToolTipBase, tooltip_bg)
            app_palette.setColor(QPalette.ColorRole.ToolTipText, tooltip_fg)
            app.setPalette(app_palette)
        except Exception:
            app_palette = QPalette()
            app_palette.setColor(QPalette.ColorRole.ToolTipBase, tooltip_bg)
            app_palette.setColor(QPalette.ColorRole.ToolTipText, tooltip_fg)

        # QToolTip uses its own palette; also set Window roles so tooltip widgets that paint via
        # Window/WindowText still look correct.
        tip_palette = QPalette(app_palette)
        tip_palette.setColor(QPalette.ColorRole.ToolTipBase, tooltip_bg)
        tip_palette.setColor(QPalette.ColorRole.ToolTipText, tooltip_fg)
        tip_palette.setColor(QPalette.ColorRole.Window, tooltip_bg)
        tip_palette.setColor(QPalette.ColorRole.WindowText, tooltip_fg)
        tip_palette.setColor(QPalette.ColorRole.Text, tooltip_fg)
        QToolTip.setPalette(tip_palette)
    except Exception:
        return
