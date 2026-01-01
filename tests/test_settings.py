"""
配置管理测试

测试 Settings 类的配置加载、验证和保存功能
"""

import pytest
import yaml
from src.config.settings import Settings


class TestSettings:
    """Settings 类测试"""

    def test_load_config_from_yaml(self, sample_config_yaml):
        """测试从 YAML 文件加载配置"""
        settings = Settings.from_yaml(str(sample_config_yaml))

        assert settings is not None
        assert settings.llm.model == "test-model"
        assert settings.llm.temperature == 0.7
        assert hasattr(settings, "vision_llm")

    def test_load_vision_llm_config(self, sample_config_dict, temp_dir):
        """确保可从 VISION_LLM 读取独立的视觉模型配置（兼容 enable/enabled）。"""
        config = sample_config_dict.copy()
        config["VISION_LLM"] = {
            "enable": True,
            "api": "https://api.vision.test/v1",
            "key": "vision-api-key",
            "model": "vision-model",
        }

        config_path = temp_dir / "vision_config.yaml"
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f)

        settings = Settings.from_yaml(str(config_path))
        assert settings.vision_llm.enabled is True
        assert settings.vision_llm.model == "vision-model"
        assert settings.vision_llm.api == "https://api.vision.test/v1"

    def test_config_validation(self, sample_config_dict, temp_dir):
        """测试配置验证"""
        # 创建无效配置
        invalid_config = sample_config_dict.copy()
        invalid_config["LLM"]["temperature"] = 2.0  # 超出范围

        config_path = temp_dir / "invalid_config.yaml"
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(invalid_config, f)

        # 应该抛出验证错误
        with pytest.raises(Exception):
            Settings.from_yaml(str(config_path))

    def test_config_file_not_found(self):
        """测试配置文件不存在的情况"""
        with pytest.raises(FileNotFoundError):
            Settings.from_yaml("nonexistent_config.yaml")

    def test_config_default_values(self, sample_config_yaml):
        """测试配置默认值"""
        settings = Settings.from_yaml(str(sample_config_yaml))

        # 检查默认值
        assert settings.agent.enable_streaming is True
        assert settings.agent.max_history_length == 20

    def test_save_config_to_yaml(self, sample_config_yaml, temp_dir):
        """测试保存配置到 YAML 文件"""
        # 加载配置
        settings = Settings.from_yaml(str(sample_config_yaml))

        # 修改配置
        settings.llm.temperature = 0.8

        # 保存到新文件
        new_config_path = temp_dir / "new_config.yaml"
        settings.to_yaml(str(new_config_path))

        # 验证保存成功
        assert new_config_path.exists()

        # 重新加载验证
        reloaded_settings = Settings.from_yaml(str(new_config_path))
        assert reloaded_settings.llm.temperature == 0.8


@pytest.mark.unit
class TestLLMConfig:
    """LLM 配置测试"""

    def test_llm_config_fields(self, sample_config_yaml):
        """测试 LLM 配置字段"""
        settings = Settings.from_yaml(str(sample_config_yaml))

        assert hasattr(settings.llm, "key")
        assert hasattr(settings.llm, "api")
        assert hasattr(settings.llm, "model")
        assert hasattr(settings.llm, "temperature")
        assert hasattr(settings.llm, "max_tokens")

    def test_llm_config_types(self, sample_config_yaml):
        """测试 LLM 配置类型"""
        settings = Settings.from_yaml(str(sample_config_yaml))

        assert isinstance(settings.llm.key, str)
        assert isinstance(settings.llm.api, str)
        assert isinstance(settings.llm.model, str)
        assert isinstance(settings.llm.temperature, (int, float))
        assert isinstance(settings.llm.max_tokens, int)


@pytest.mark.unit
class TestAgentConfig:
    """Agent 配置测试"""

    def test_agent_config_fields(self, sample_config_yaml):
        """测试 Agent 配置字段"""
        settings = Settings.from_yaml(str(sample_config_yaml))

        assert hasattr(settings.agent, "enable_streaming")
        assert hasattr(settings.agent, "max_history_length")
        assert hasattr(settings.agent, "enable_tools")

    def test_agent_config_types(self, sample_config_yaml):
        """测试 Agent 配置类型"""
        settings = Settings.from_yaml(str(sample_config_yaml))

        assert isinstance(settings.agent.enable_streaming, bool)
        assert isinstance(settings.agent.max_history_length, int)
        assert isinstance(settings.agent.enable_tools, bool)
