# MintChat - 多模态猫娘女仆智能体

<div align="center">

**一个基于 LangChain / LangGraph 的沉浸式多模态智能体，带 PyQt6 GUI。**

[![Python Version](https://img.shields.io/badge/python-3.13%2B-blue.svg)](https://www.python.org/downloads/)
[![LangChain](https://img.shields.io/badge/LangChain-1.0%2B-green.svg)](https://docs.langchain.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-2.60.6-brightgreen.svg)](docs/CHANGELOG.md)

</div>

## 特性

- Agent 编排：LangChain / LangGraph
- 多模态：图像 / 音频（可选启用 ASR/TTS；ASR 默认 SenseVoiceSmall）
- 记忆系统：短期 / 长期 / 核心记忆（实现细节见 `src/agent/`）
- GUI：PyQt6（入口 `MintChat.py`）

## 快速开始（uv + .venv）

### 0) 前置条件

- Windows / macOS / Linux
- Python 3.13+（uv 可自动下载/管理 Python）
- 安装 uv
- （可选）NVIDIA GPU + 驱动（如需 torch CUDA 加速；本项目 Windows/Linux 锁定 cu130）

### 1) 安装 uv

Windows（PowerShell）:

```powershell
pipx install uv
```

macOS / Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2) 安装依赖（创建 `.venv`）

```bash
uv sync --locked --no-install-project
```

> Windows 提示：执行 `uv sync` / `uv lock` / `--reinstall-package` 前，建议先关闭正在运行的 MintChat，避免 `numpy/*.pyd` 等文件被占用导致环境不完整。

### (可选) GPU 加速（PyTorch CUDA 13.0 / cu130）

Windows/Linux 环境下，本项目锁定使用 `torch==2.9.1+cu130`（来自 PyTorch 官方索引）。

验证是否生效：

```bash
# Windows
.\.venv\Scripts\python.exe -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())"

# macOS / Linux
./.venv/bin/python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())"
```

### 3) 配置（生成本地 `config.user.yaml`）

```bash
# Windows
copy config.user.yaml.example config.user.yaml

# macOS / Linux
cp config.user.yaml.example config.user.yaml
```

`config.user.yaml` 已在 `.gitignore` 中忽略，请不要提交真实 key；提交模板请使用 `config.user.yaml.example`。
`config.dev.yaml` 可提交到 git（必须保持不含密钥/敏感信息），用于调试与便于他人理解项目。

### (可选) 启用语音输入 ASR（SenseVoiceSmall）

```bash
uv sync --locked --no-install-project --extra asr
```

然后在 `config.user.yaml` 中打开 `ASR.enabled: true`（其余参数可参考 `config.user.yaml.example` / `config.dev.yaml`）。

实时语音输入已内置轻量 RMS-VAD + 停顿自动结束（如 `ASR.endpoint_silence_ms`、`ASR.silence_threshold_mode`、`ASR.pre_roll_ms`），可根据环境噪声与使用习惯微调。

### 4) 启动

GUI（推荐）:

```bash
# Windows
.\.venv\Scripts\python.exe MintChat.py

# macOS / Linux
./.venv/bin/python MintChat.py
```

Windows 也可以直接双击 `MintChat.bat` / `2.启动MintChat.bat`。

命令行示例菜单：

```bash
# Windows
.\.venv\Scripts\python.exe scripts/start.py

# macOS / Linux
./.venv/bin/python scripts/start.py
```

直接运行示例：

```bash
# Windows
.\.venv\Scripts\python.exe examples/basic_chat.py
.\.venv\Scripts\python.exe examples/tool_usage.py
.\.venv\Scripts\python.exe examples/multimodal_demo.py

# macOS / Linux
./.venv/bin/python examples/basic_chat.py
./.venv/bin/python examples/tool_usage.py
./.venv/bin/python examples/multimodal_demo.py
```

## 开发

安装开发依赖：

```bash
uv sync --locked --group dev --no-install-project
```

常用命令（Makefile）：

```bash
make dev
make test
make lint
make format
make type-check
```

无 make 的等价命令：

```bash
# Windows
.\.venv\Scripts\python.exe -m pytest tests/ -v
.\.venv\Scripts\python.exe -m flake8 src/ tests/ examples/ --max-line-length=100 --ignore=E203,W503
.\.venv\Scripts\python.exe -m black src/ tests/ examples/
.\.venv\Scripts\python.exe -m mypy src/ --ignore-missing-imports

# macOS / Linux
./.venv/bin/python -m pytest tests/ -v
./.venv/bin/python -m flake8 src/ tests/ examples/ --max-line-length=100 --ignore=E203,W503
./.venv/bin/python -m black src/ tests/ examples/
./.venv/bin/python -m mypy src/ --ignore-missing-imports
```

## 项目结构

```
MintChat/
├── src/                 # 核心代码（import 路径为 src.*）
├── examples/            # 示例脚本
├── scripts/             # 启动脚本与工具脚本
├── docs/                # 文档与变更日志
├── MintChat.py          # GUI 入口
├── pyproject.toml       # 依赖与项目元数据（uv 源）
├── uv.lock              # 锁文件（可复现安装）
├── config.user.yaml.example  # 可提交的用户配置模板
├── config.dev.yaml           # 开发者/调试配置（可提交，不含密钥）
├── config.yaml.example       # legacy 单文件模板（可选）
└── config.user.yaml          # 本地用户配置（已被 git 忽略）
```

## 常见问题

### `pkg_resources is deprecated as an API`

这是依赖链里较旧用法导致的提示，通常不影响功能。若想消除：

```bash
uv sync --locked --no-install-project
uv pip install --upgrade setuptools
```

### ASR 报错：`FunAudioLLM/SenseVoiceSmall is not registered`

这是 FunASR 在 HuggingFace 仓库布局下无法解析 `model` 配置导致的。请改用 ModelScope 的 SenseVoiceSmall：

- `config.user.yaml`（或 `config.dev.yaml`）中设置：
  - `ASR.model: "iic/SenseVoiceSmall"`
  - `ASR.hub: "ms"`
- 然后执行：`uv sync --locked --no-install-project --extra asr`

### 第一次 `uv sync` 下载较大/较慢

项目依赖包含部分较大的科学计算/模型相关包（例如 `torch`），首次安装可能耗时较久；确保网络稳定即可。

## 文档

- `docs/README.md`：文档索引
- `docs/CHANGELOG.md`：版本变更记录
- `scripts/README.md`：脚本说明

## 许可证

MIT，见 `LICENSE`。
# MintBot
