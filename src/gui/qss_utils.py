"""Helpers for building Qt stylesheet (QSS) strings."""

from __future__ import annotations

from typing import Tuple


def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    value = (hex_color or "").strip()
    if value.startswith("#"):
        value = value[1:]

    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)

    if len(value) != 6:
        return (0, 0, 0)

    try:
        r = int(value[0:2], 16)
        g = int(value[2:4], 16)
        b = int(value[4:6], 16)
    except ValueError:
        return (0, 0, 0)

    return (r, g, b)


def qss_rgba(hex_color: str, alpha: float | int) -> str:
    """Return a QSS rgba(...) string from hex color.

    Qt style sheets accept `rgba(r,g,b,a)`, and in practice `a` is widely used
    as a *byte* alpha (0..255) in this codebase. This helper accepts:
    - float in [0..1] -> converted to 0..255
    - int in [0..255] -> used as-is (clamped)
    - float > 1 -> treated as 0..255 and clamped
    """
    r, g, b = _hex_to_rgb(hex_color)

    if isinstance(alpha, float):
        if 0.0 <= alpha <= 1.0:
            alpha_value = int(round(alpha * 255))
        else:
            alpha_value = int(round(alpha))
    else:
        alpha_value = int(alpha)

    alpha_value = max(0, min(255, alpha_value))
    return f"rgba({r}, {g}, {b}, {alpha_value})"
