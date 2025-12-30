from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any
import os


ENV_LIVE2D_STATE_EVENTS = "MINTCHAT_LIVE2D_STATE_EVENTS"
ENV_LIVE2D_STATE_DIRECTIVES = "MINTCHAT_LIVE2D_STATE_DIRECTIVES"
ENV_LIVE2D_STREAM_FEEDBACK = "MINTCHAT_LIVE2D_STREAM_FEEDBACK"
ENV_LIVE2D_STATE_DEBOUNCE_MS = "MINTCHAT_LIVE2D_STATE_DEBOUNCE_MS"
ENV_LIVE2D_STREAM_TAIL_CHARS = "MINTCHAT_LIVE2D_STREAM_TAIL_CHARS"


@dataclass(frozen=True, slots=True)
class Live2DStateEventsConfig:
    enabled: bool = True
    allow_directives: bool = True
    stream_feedback: bool = True
    debounce_ms: int = 750
    stream_tail_chars: int = 360


def _parse_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if int(value) == 0:
            return False
        if int(value) == 1:
            return True
        return None
    if isinstance(value, str):
        raw = value.strip().lower()
        if raw in {"1", "true", "yes", "y", "on", "enable", "enabled"}:
            return True
        if raw in {"0", "false", "no", "n", "off", "disable", "disabled"}:
            return False
    return None


def _parse_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            return int(float(raw))
        except Exception:
            return None
    return None


@lru_cache(maxsize=1)
def _read_live2d_section_from_config() -> dict[str, Any]:
    try:
        from src.config.config_files import load_merged_config

        data, _user_path, _dev_path, _legacy_used = load_merged_config()
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    gui_section = data.get("GUI") or data.get("gui") or {}
    if not isinstance(gui_section, dict):
        return {}
    live2d_section = gui_section.get("live2d") or gui_section.get("Live2D") or {}
    if not isinstance(live2d_section, dict):
        return {}
    state_events = live2d_section.get("state_events") or live2d_section.get("StateEvents") or {}
    if not isinstance(state_events, dict):
        return {}
    return dict(state_events)


@lru_cache(maxsize=1)
def get_live2d_state_events_config() -> Live2DStateEventsConfig:
    state_cfg = _read_live2d_section_from_config()

    enabled = _parse_bool(os.getenv(ENV_LIVE2D_STATE_EVENTS))
    allow_directives = _parse_bool(os.getenv(ENV_LIVE2D_STATE_DIRECTIVES))
    stream_feedback = _parse_bool(os.getenv(ENV_LIVE2D_STREAM_FEEDBACK))
    debounce_ms = _parse_int(os.getenv(ENV_LIVE2D_STATE_DEBOUNCE_MS))
    stream_tail_chars = _parse_int(os.getenv(ENV_LIVE2D_STREAM_TAIL_CHARS))

    if enabled is None:
        enabled = _parse_bool(state_cfg.get("enabled")) if state_cfg else None
    if allow_directives is None:
        allow_directives = _parse_bool(state_cfg.get("allow_directives")) if state_cfg else None
    if stream_feedback is None:
        stream_feedback = _parse_bool(state_cfg.get("stream_feedback")) if state_cfg else None
    if debounce_ms is None:
        debounce_ms = _parse_int(state_cfg.get("debounce_ms")) if state_cfg else None
    if stream_tail_chars is None:
        stream_tail_chars = _parse_int(state_cfg.get("stream_tail_chars")) if state_cfg else None

    base = Live2DStateEventsConfig()
    return Live2DStateEventsConfig(
        enabled=base.enabled if enabled is None else bool(enabled),
        allow_directives=(
            base.allow_directives if allow_directives is None else bool(allow_directives)
        ),
        stream_feedback=base.stream_feedback if stream_feedback is None else bool(stream_feedback),
        debounce_ms=max(
            0, min(30_000, base.debounce_ms if debounce_ms is None else int(debounce_ms))
        ),
        stream_tail_chars=max(
            0,
            min(
                5000,
                base.stream_tail_chars if stream_tail_chars is None else int(stream_tail_chars),
            ),
        ),
    )
