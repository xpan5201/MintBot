"""
Vision LLM 工厂测试

确保视觉模型（VISION_LLM）与主 LLM 解耦时的行为符合预期：
- disabled 时 get_vision_llm() 返回 None
- enabled 时可构建一个可调用的 chat model（不发起网络请求）
"""

import yaml

from src.config.settings import Settings
from src.llm import factory


def _write_yaml(path, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def test_get_vision_llm_disabled_returns_none(sample_config_dict, temp_dir, monkeypatch):
    config = sample_config_dict.copy()
    config["VISION_LLM"] = {"enabled": False, "model": "vision-model"}
    config_path = temp_dir / "vision_disabled.yaml"
    _write_yaml(config_path, config)

    settings = Settings.from_yaml(str(config_path))
    monkeypatch.setattr(factory, "settings", settings)
    factory.reset_llm_cache()

    assert factory.get_vision_llm() is None


def test_get_vision_llm_enabled_builds_model(sample_config_dict, temp_dir, monkeypatch):
    config = sample_config_dict.copy()
    config["VISION_LLM"] = {"enabled": True, "model": "vision-model"}
    config_path = temp_dir / "vision_enabled.yaml"
    _write_yaml(config_path, config)

    settings = Settings.from_yaml(str(config_path))
    monkeypatch.setattr(factory, "settings", settings)
    factory.reset_llm_cache()

    llm = factory.get_vision_llm()
    assert llm is not None
    assert callable(getattr(llm, "complete", None))


def test_get_vision_llm_empty_key_falls_back_to_llm_key(sample_config_dict, temp_dir, monkeypatch):
    config = sample_config_dict.copy()
    config["VISION_LLM"] = {"enabled": True, "model": "vision-model", "key": ""}
    config_path = temp_dir / "vision_empty_key.yaml"
    _write_yaml(config_path, config)

    settings = Settings.from_yaml(str(config_path))
    monkeypatch.setattr(factory, "settings", settings)
    factory.reset_llm_cache()

    llm = factory.get_vision_llm()
    assert llm is not None
    assert (
        getattr(getattr(llm, "config", None), "api_key", None) == sample_config_dict["LLM"]["key"]
    )
