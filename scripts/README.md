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

- `setup_config.py`：缺失时用 `config.user.yaml.example` 生成 `config.user.yaml`（开发者配置请直接编辑仓库内的 `config.dev.yaml`）
- `check_install.py`：依赖自检
- `clean.py`：清理缓存/测试产物
- `neo4j_graph_smoke.py`：L4 心智云图 Neo4j 写入烟测（需 `--enabled` 或 `NEO4J_SMOKE_ENABLED=1`，可配 `NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD/NEO4J_DATABASE`）
- `neo4j_graph_queue_smoke.py`：graph_queue 端到端烟测（enqueue → worker → Neo4j；需 `--enabled` 或 `NEO4J_QUEUE_SMOKE_ENABLED=1`）

## 计划归档（Archives）

- `archive_manager.py`：档案库索引管理（SQLite）与计划产物登记

## 已归档计划：去 LangChain（Phase/Gate）

> 去 LangChain/LangGraph 迁移计划已归档（含 Golden/触点审计脚本与 Gate 文档）：`archives/plans/2026-01_de_langchain_phase0-7/`。

## 说明（稳定优先）

- 已移除一次性/破坏性“自动修复”脚本（例如自动改代码/改依赖的 `fix_*`/`optimize_*`/`organize_*`）。
- 代码质量与格式化请使用：`make format` / `make lint` / `make type-check` / `make test`（或直接运行 black/flake8/mypy/pytest）。

运行方式统一建议：

```bash
uv sync --locked --no-install-project
./.venv/bin/python scripts/<script>.py
```
