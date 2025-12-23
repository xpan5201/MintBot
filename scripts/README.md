# scripts/ 说明

本目录包含 MintChat 的启动脚本与各类维护/诊断脚本。

## 推荐启动方式（uv + .venv）

优先使用仓库根目录的入口：

- Windows：双击 `MintChat.bat`（或 `2.启动MintChat.bat`）
- Linux/macOS：`bash MintChat.sh`
- 纯命令行：`.\.venv\Scripts\python.exe MintChat.py`（Windows）/ `./.venv/bin/python MintChat.py`（macOS/Linux）

## 启动脚本

- `start.py`：交互式菜单（运行 examples 下的示例）
  - 运行：`.\.venv\Scripts\python.exe scripts/start.py` / `./.venv/bin/python scripts/start.py`
- `quick_start.py`：快速进入基础对话
  - 运行：`.\.venv\Scripts\python.exe scripts/quick_start.py` / `./.venv/bin/python scripts/quick_start.py`
- `run.bat` / `run.sh`：命令行版本启动脚本（会自动 `uv sync --locked --no-install-project`）
- `mintchat_light_gui.py`：浅色主题 GUI 启动器
  - 运行：`.\.venv\Scripts\python.exe scripts/mintchat_light_gui.py` / `./.venv/bin/python scripts/mintchat_light_gui.py`
  - 或：`run_light_gui.bat` / `run_light_gui.sh`

## 工具脚本

- `setup_config.py`：缺失时用 `config.yaml.example` 生成 `config.yaml`
- `check_install.py`：依赖自检
- `clean.py`：清理缓存/测试产物

运行方式统一建议：

```bash
uv sync --locked --no-install-project
./.venv/bin/python scripts/<script>.py
```
