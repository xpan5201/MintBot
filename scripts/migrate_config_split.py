#!/usr/bin/env python3
"""
Migrate legacy single-file config.yaml to the split config files:
- config.user.yaml (user)
- config.dev.yaml (developer overrides, optional)

Design goals:
- Preserve behavior: deep-merge(user, dev) should equal the legacy config content.
- Reduce user risk: keep common settings in user config; move advanced knobs to dev config.
- Non-destructive: backup existing destination files before overwriting.

NOTE: This script never prints secret values. It only prints file paths and key names.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
import argparse

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True, slots=True)
class SplitResult:
    user: dict[str, Any]
    dev: dict[str, Any]


USER_LOG_KEYS = {"log_level", "log_dir"}
DEV_LOG_KEYS = {
    "log_rotation",
    "log_retention",
    "log_json",
    "log_quiet_libs",
    "log_quiet_level",
    "log_drop_keywords",
}

USER_AGENT_KEYS = {
    "char",
    "user",
    "prompt",
    "message_example",
    "char_settings",
    "char_personalities",
    "mask",
    "start_with",
    "is_up",
    "enable_streaming",
    "max_history_length",
    "enable_tools",
    "mood_system_enabled",
    "emotion_memory_enabled",
    "long_memory",
    "style_learning_enabled",
    "tool_selector_enabled",
}

USER_ASR_KEYS = {"enabled", "realtime_mode", "model", "device", "sample_rate"}

USER_TTS_KEYS = {
    "enabled",
    "api_url",
    "ref_audio_path",
    "ref_audio_text",
    "text_lang",
    "prompt_lang",
    "speed_factor",
    "top_k",
    "top_p",
    "temperature",
    "batch_size",
    "seed",
    "max_queue_size",
    "default_volume",
    "disk_cache_enabled",
    "disk_cache_dir",
}


def _is_mapping(value: Any) -> bool:
    return isinstance(value, Mapping)


def _split_mapping(
    mapping: Mapping[str, Any], keep_keys: set[str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    kept: dict[str, Any] = {}
    rest: dict[str, Any] = {}
    for k, v in dict(mapping).items():
        if k in keep_keys:
            kept[k] = v
        else:
            rest[k] = v
    return kept, rest


def _deep_merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = dict(base or {})
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dict(merged.get(key, {}), value)
        else:
            merged[key] = value
    return merged


def split_config(config: dict[str, Any]) -> SplitResult:
    user: dict[str, Any] = {}
    dev: dict[str, Any] = {}

    for key, value in (config or {}).items():
        if key == "MCP":
            dev[key] = value
            continue

        if key in USER_LOG_KEYS:
            user[key] = value
            continue
        if key in DEV_LOG_KEYS:
            dev[key] = value
            continue

        if key in {"LLM", "VISION_LLM", "AMAP", "GUI"}:
            user[key] = value
            continue

        if key == "TAVILY":
            if _is_mapping(value):
                u, d = _split_mapping(value, {"api_key"})
                if u:
                    user[key] = u
                if d:
                    dev[key] = d
            else:
                user[key] = value
            continue

        if key == "Agent":
            if _is_mapping(value):
                u, d = _split_mapping(value, USER_AGENT_KEYS)
                if u:
                    user[key] = u
                if d:
                    dev[key] = d
            else:
                user[key] = value
            continue

        if key == "ASR":
            if _is_mapping(value):
                u, d = _split_mapping(value, USER_ASR_KEYS)
                if u:
                    user[key] = u
                if d:
                    dev[key] = d
            else:
                user[key] = value
            continue

        if key == "TTS":
            if _is_mapping(value):
                u, d = _split_mapping(value, USER_TTS_KEYS)
                if u:
                    user[key] = u
                if d:
                    dev[key] = d
            else:
                user[key] = value
            continue

        # Default: put the rest into user config (user-facing settings).
        user[key] = value

    # Reorder for readability (without losing any keys).
    user_order = [
        "LLM",
        "VISION_LLM",
        "Agent",
        "TTS",
        "ASR",
        "TAVILY",
        "AMAP",
        "GUI",
        "embedding_model",
        "embedding_api_base",
        "use_local_embedding",
        "enable_embedding_cache",
        "max_image_size",
        "max_audio_duration",
        "data_dir",
        "vector_db_path",
        "memory_path",
        "cache_path",
        "log_level",
        "log_dir",
        "favorite_emojis",
        "recent_emojis",
    ]
    dev_order = [
        "MCP",
        "Agent",
        "ASR",
        "TTS",
        "TAVILY",
        "log_json",
        "log_rotation",
        "log_retention",
        "log_quiet_libs",
        "log_quiet_level",
        "log_drop_keywords",
    ]

    def _reorder(data: dict[str, Any], order: list[str]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k in order:
            if k in data:
                out[k] = data[k]
        for k, v in data.items():
            if k not in out:
                out[k] = v
        return out

    return SplitResult(user=_reorder(user, user_order), dev=_reorder(dev, dev_order))


def _backup_file(path: Path) -> Path | None:
    if not path.exists():
        return None
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.bak.{ts}")
    path.replace(backup)
    return backup


def _load_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"Config must be a YAML mapping/object: {path}")
    return raw


def _dump_yaml(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(data or {}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _print_keys(title: str, data: dict[str, Any]) -> None:
    keys = list(data.keys())
    print(f"{title}: {len(keys)} keys")
    if keys:
        print("  " + ", ".join(keys))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="config.yaml")
    parser.add_argument("--user", default="config.user.yaml")
    parser.add_argument("--dev", default="config.dev.yaml")
    parser.add_argument("--no-backup", action="store_true", help="Do not backup existing files.")
    args = parser.parse_args()

    source_path = (PROJECT_ROOT / str(args.source)).resolve()
    user_path = (PROJECT_ROOT / str(args.user)).resolve()
    dev_path = (PROJECT_ROOT / str(args.dev)).resolve()

    if not source_path.exists():
        print(f"[ERROR] Legacy config not found: {source_path}")
        return 1

    config = _load_yaml(source_path)
    result = split_config(config)

    merged = _deep_merge_dict(result.user, result.dev)
    if merged != config:
        print("[WARN] Split result does not deep-merge back to the source config.")
        print("       Please inspect user/dev files after migration.")
    else:
        print("[OK] Split result deep-merges back to the source config.")

    if not args.no_backup:
        for path in (user_path, dev_path):
            backup = _backup_file(path)
            if backup is not None:
                print(f"[OK] Backup created: {backup}")

    _dump_yaml(user_path, result.user)
    _dump_yaml(dev_path, result.dev)

    print(f"[OK] Wrote user config: {user_path}")
    print(f"[OK] Wrote dev config : {dev_path}")
    _print_keys("[INFO] user", result.user)
    _print_keys("[INFO] dev", result.dev)
    print("[INFO] You can now stop using config.yaml (kept as legacy backup).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
