from __future__ import annotations

from pathlib import Path

import yaml

from src.config.config_surface import DEV_EXAMPLE_REQUIRED_PATHS, USER_EXAMPLE_REQUIRED_PATHS, has_config_path


def _load_yaml_mapping(path: Path) -> dict:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    assert isinstance(raw, dict)
    return raw


def test_user_config_example_covers_required_surface() -> None:
    data = _load_yaml_mapping(Path("config.user.yaml.example"))
    missing = [p for p in USER_EXAMPLE_REQUIRED_PATHS if not has_config_path(data, p)]
    assert not missing, f"missing keys: {missing}"


def test_dev_config_example_covers_required_surface() -> None:
    data = _load_yaml_mapping(Path("config.dev.yaml.example"))
    missing = [p for p in DEV_EXAMPLE_REQUIRED_PATHS if not has_config_path(data, p)]
    assert not missing, f"missing keys: {missing}"

