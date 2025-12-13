# MintChat 测试文档

> **版本**: v2.54.1
> **更新日期**: 2025-11-19

本文档说明 MintChat 项目的测试系统。

---

## 📋 测试概览

MintChat 使用 **pytest** 作为测试框架，提供单元测试和集成测试。

### 测试文件组织

```
tests/
├── __init__.py              # 测试包初始化
├── conftest.py              # pytest 配置和 fixtures
├── README.md                # 测试文档（本文件）
├── test_settings.py         # 配置管理测试
└── test_multimodal.py       # 多模态功能测试
```

---

## 🚀 运行测试

### 运行所有测试

```bash
pytest
```

### 运行特定文件

```bash
pytest tests/test_settings.py
```

### 运行特定测试

```bash
pytest tests/test_settings.py::test_load_config
```

### 显示详细输出

```bash
pytest -v
```

### 显示打印输出

```bash
pytest -s
```

### 生成覆盖率报告

```bash
pytest --cov=src --cov-report=html
```

---

## 📝 测试说明

### test_settings.py

测试配置管理功能：
- 配置文件加载
- 配置验证
- 配置保存

### test_multimodal.py

测试多模态功能：
- 图像格式验证
- 音频格式验证
- 处理器初始化

---

## 🔧 编写测试

### 使用 Fixtures

```python
import pytest

@pytest.fixture
def sample_config():
    """示例配置 fixture"""
    return {
        "llm": {
            "model": "gpt-3.5-turbo",
            "temperature": 0.7
        }
    }

def test_with_fixture(sample_config):
    """使用 fixture 的测试"""
    assert sample_config["llm"]["model"] == "gpt-3.5-turbo"
```

### 测试异常

```python
import pytest

def test_exception():
    """测试异常抛出"""
    with pytest.raises(ValueError):
        raise ValueError("测试错误")
```

### 异步测试

```python
import pytest

@pytest.mark.asyncio
async def test_async_function():
    """异步测试"""
    result = await some_async_function()
    assert result is not None
```

---

## 📊 测试覆盖率

当前测试覆盖的模块：
- ✅ 配置管理 (`src/config/`)
- ✅ 多模态处理 (`src/multimodal/`)

待添加测试的模块：
- ⏳ Agent 核心 (`src/agent/core.py`)
- ⏳ 记忆系统 (`src/agent/memory/`)
- ⏳ 情感引擎 (`src/agent/emotion.py`)
- ⏳ 工具系统 (`src/agent/tools/`)
- ⏳ GUI 组件 (`src/gui/`)

---

## 🎯 测试最佳实践

1. **测试命名**: 使用描述性的测试名称
   ```python
   def test_load_config_from_yaml():
       """测试从 YAML 文件加载配置"""
       pass
   ```

2. **单一职责**: 每个测试只测试一个功能点
   ```python
   def test_config_validation():
       """只测试配置验证"""
       pass
   ```

3. **使用 Fixtures**: 复用测试数据
   ```python
   @pytest.fixture
   def agent():
       return MintChatAgent()
   ```

4. **清理资源**: 使用 fixture 的 yield 清理资源
   ```python
   @pytest.fixture
   def temp_file():
       f = open("temp.txt", "w")
       yield f
       f.close()
       os.remove("temp.txt")
   ```

---

## 📚 参考资源

- [pytest 官方文档](https://docs.pytest.org/)
- [pytest-asyncio 文档](https://pytest-asyncio.readthedocs.io/)
- [pytest-cov 文档](https://pytest-cov.readthedocs.io/)
