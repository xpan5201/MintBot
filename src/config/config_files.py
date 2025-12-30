from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import yaml
except Exception:  # pragma: no cover - environment dependency variance
    yaml = None  # type: ignore[assignment]


PROJECT_ROOT = Path(__file__).resolve().parents[2]


DEFAULT_USER_CONFIG_PATH = "config.user.yaml"
DEFAULT_DEV_CONFIG_PATH = "config.dev.yaml"

# Backward-compatible legacy single-file config.
LEGACY_CONFIG_PATH = "config.yaml"

DEFAULT_USER_CONFIG_EXAMPLE_PATH = "config.user.yaml.example"
DEFAULT_DEV_CONFIG_EXAMPLE_PATH = "config.dev.yaml.example"
LEGACY_CONFIG_EXAMPLE_PATH = "config.yaml.example"


def to_project_path(path: str | Path) -> Path:
    value = Path(path)
    if value.is_absolute():
        return value
    return PROJECT_ROOT / value


def deep_merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge dictionaries (override wins), without mutating inputs."""
    merged: dict[str, Any] = dict(base or {})
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge_dict(merged.get(key, {}), value)
        else:
            merged[key] = value
    return merged


def read_yaml_file(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML 未安装，无法读取配置文件。")

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    if not isinstance(data, dict):
        raise ValueError(f"配置文件必须为 YAML mapping/object: {path}")

    return data


def resolve_config_paths(
    user_config_path: str = DEFAULT_USER_CONFIG_PATH,
    dev_config_path: str = DEFAULT_DEV_CONFIG_PATH,
    *,
    allow_legacy: bool = True,
) -> tuple[Path, Path | None, bool]:
    """Return (user_path, dev_path_or_none, legacy_used)."""
    user_path = to_project_path(user_config_path)
    legacy_used = False

    if allow_legacy and user_config_path == DEFAULT_USER_CONFIG_PATH and not user_path.exists():
        legacy_path = to_project_path(LEGACY_CONFIG_PATH)
        if legacy_path.exists():
            user_path = legacy_path
            legacy_used = True

    dev_path: Path | None = None
    if dev_config_path:
        candidate = to_project_path(dev_config_path)
        if candidate.exists():
            dev_path = candidate

    return user_path, dev_path, legacy_used


def load_merged_config(
    user_config_path: str = DEFAULT_USER_CONFIG_PATH,
    dev_config_path: str = DEFAULT_DEV_CONFIG_PATH,
    *,
    allow_legacy: bool = True,
) -> tuple[dict[str, Any], Path | None, Path | None, bool]:
    """Load user config and optional dev config, return merged + paths used."""
    user_path, dev_path, legacy_used = resolve_config_paths(
        user_config_path=user_config_path,
        dev_config_path=dev_config_path,
        allow_legacy=allow_legacy,
    )

    user_data: dict[str, Any] = {}
    if user_path.exists():
        user_data = read_yaml_file(user_path)

    dev_data: dict[str, Any] = {}
    if dev_path is not None:
        dev_data = read_yaml_file(dev_path)

    return (
        deep_merge_dict(user_data, dev_data),
        user_path if user_path.exists() else None,
        dev_path,
        legacy_used,
    )


def write_yaml_atomic(path: str | Path, data: dict[str, Any]) -> None:
    if yaml is None:
        raise RuntimeError("PyYAML 未安装，无法写入配置文件。")

    output_path = to_project_path(path)
    tmp_path = output_path.with_name(output_path.name + ".tmp")
    try:
        tmp_path.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        tmp_path.replace(output_path)
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
