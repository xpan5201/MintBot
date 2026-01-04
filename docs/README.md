# MintChat 文档索引

## 文档列表

- `CHANGELOG.md`：版本变更记录
- `LOGGING.md`：日志系统说明
- `gui_blueprint.md`：GUI 设计/蓝图
- `archives/`：项目档案库（计划归档索引 + 计划产物）

## 快速开始（uv + .venv）

更完整的安装/启动说明请看仓库根目录 `README.md`。这里给出最短路径：

- Windows（PowerShell）：

```powershell
uv sync --locked --no-install-project
Copy-Item config.user.yaml.example config.user.yaml -Force
.\.venv\Scripts\python.exe MintChat.py
```

- macOS/Linux：

```bash
uv sync --locked --no-install-project
cp config.user.yaml.example config.user.yaml
./.venv/bin/python MintChat.py
```

说明：
- `config.user.yaml`：用户私有配置（含密钥，禁止提交）。
- `config.dev.yaml`：开发者/调试配置（不含密钥，可提交）。
