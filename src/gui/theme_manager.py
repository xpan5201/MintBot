"""GUI Theme manager.

Theme selection priority:
1) Environment variable: MINTCHAT_GUI_THEME
2) config.yaml: GUI.theme (or gui.theme)
3) Default: mint
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Optional
import os

ENV_GUI_THEME = "MINTCHAT_GUI_THEME"

THEME_MINT = "mint"
THEME_ANIME = "anime"


def normalize_theme_name(value: Optional[str]) -> str:
    if not value:
        return THEME_MINT

    raw = value.strip().lower()
    if not raw:
        return THEME_MINT

    if raw in {"anime", "kawaii", "2d", "acg", "二次元"}:
        return THEME_ANIME

    if raw in {"mint", "default", "md3", "light"}:
        return THEME_MINT

    return THEME_MINT


@lru_cache(maxsize=1)
def _read_theme_from_config() -> Optional[str]:
    config_path = Path(__file__).resolve().parents[2] / "config.yaml"
    if not config_path.exists():
        return None

    try:
        import yaml  # optional dependency in project

        data: Any = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    gui_section = data.get("GUI") or data.get("gui") or {}
    if not isinstance(gui_section, dict):
        return None

    theme_value = gui_section.get("theme") or gui_section.get("Theme")
    if isinstance(theme_value, str):
        return theme_value

    return None


def get_active_theme_name() -> str:
    env = os.getenv(ENV_GUI_THEME)
    if env:
        return normalize_theme_name(env)

    from_config = _read_theme_from_config()
    return normalize_theme_name(from_config)


def is_anime_theme() -> bool:
    return get_active_theme_name() == THEME_ANIME

