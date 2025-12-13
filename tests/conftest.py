"""
pytest 配置文件

提供测试所需的 fixtures 和配置
"""

import pytest
import os
import tempfile
from pathlib import Path


@pytest.fixture
def temp_dir():
    """创建临时目录 fixture"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_config_dict():
    """示例配置字典 fixture"""
    return {
        "LLM": {
            "key": "test-api-key",
            "api": "https://api.test.com/v1",
            "model": "test-model",
            "temperature": 0.7,
            "max_tokens": 2000
        },
        "Agent": {
            "enable_streaming": True,
            "max_history_length": 20,
            "enable_tools": True
        },
        "MCP": {
            "enable": False,
            "servers": []
        }
    }


@pytest.fixture
def sample_config_yaml(temp_dir, sample_config_dict):
    """创建示例配置 YAML 文件 fixture"""
    import yaml

    config_path = temp_dir / "config.yaml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(sample_config_dict, f)

    return config_path


@pytest.fixture
def sample_image_path(temp_dir):
    """创建示例图片文件 fixture"""
    from PIL import Image

    # 创建一个简单的测试图片
    img = Image.new('RGB', (100, 100), color='red')
    img_path = temp_dir / "test_image.jpg"
    img.save(img_path)

    return img_path


@pytest.fixture
def sample_audio_path(temp_dir):
    """创建示例音频文件 fixture（占位符）"""
    # 创建一个空的音频文件占位符
    audio_path = temp_dir / "test_audio.mp3"
    audio_path.touch()

    return audio_path


@pytest.fixture(autouse=True)
def reset_environment():
    """每个测试前重置环境变量"""
    original_env = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(original_env)


# pytest 配置
def pytest_configure(config):
    """pytest 配置钩子"""
    config.addinivalue_line(
        "markers", "slow: 标记慢速测试"
    )
    config.addinivalue_line(
        "markers", "integration: 标记集成测试"
    )
    config.addinivalue_line(
        "markers", "unit: 标记单元测试"
    )
