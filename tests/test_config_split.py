from __future__ import annotations

from pathlib import Path

from src.config.settings import load_settings


def test_load_settings_merges_user_and_dev_configs(tmp_path: Path) -> None:
    user_cfg = tmp_path / "config.user.yaml"
    dev_cfg = tmp_path / "config.dev.yaml"

    user_cfg.write_text(
        "log_level: INFO\n" "Agent:\n" "  enable_streaming: true\n",
        encoding="utf-8",
    )
    dev_cfg.write_text(
        "log_level: DEBUG\n" "Agent:\n" "  enable_streaming: false\n",
        encoding="utf-8",
    )

    settings = load_settings(
        user_config_path=str(user_cfg),
        dev_config_path=str(dev_cfg),
        use_cache=False,
        allow_legacy=False,
    )

    assert settings.log_level == "DEBUG"
    assert settings.agent.enable_streaming is False


def test_load_settings_ignores_invalid_dev_config(tmp_path: Path) -> None:
    user_cfg = tmp_path / "config.user.yaml"
    dev_cfg = tmp_path / "config.dev.yaml"

    user_cfg.write_text("log_level: INFO\n", encoding="utf-8")
    dev_cfg.write_text(":\n", encoding="utf-8")  # invalid YAML

    settings = load_settings(
        user_config_path=str(user_cfg),
        dev_config_path=str(dev_cfg),
        use_cache=False,
        allow_legacy=False,
    )

    assert settings.log_level == "INFO"
