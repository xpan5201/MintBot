"""Settings panel (compatibility shim).

`SettingsPanel` used to live here with a large, tool-like UI. The app now uses a
roleplay-first settings page implemented in `roleplay_settings_panel.py`.

This file is intentionally kept small to avoid breaking older imports.
"""

from __future__ import annotations

from .roleplay_settings_panel import SettingsPanel

__all__ = ["SettingsPanel"]
