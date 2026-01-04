# MintChat 档案库（Archives）

本目录用于**长期归档项目的重大维护/升级计划**（例如：Phase/Gate 迁移计划），目标是：

- 可追溯：能快速定位某次计划的决策、验收与产物
- 可查询：用 SQLite 统一索引（便于脚本化检索）
- 可回滚：归档不会影响运行时代码路径

## 目录结构

- `archives/archive.sqlite3`：档案库索引（SQLite，建议提交到 git）
- `archives/plans/<plan_id>/`：某次计划的归档目录（文档/脚本/测试数据等）
  - 例：`archives/plans/2026-01_de_langchain_phase0-7/`

## 使用方式

初始化数据库：

```powershell
.\.venv\Scripts\python.exe scripts\archive_manager.py init
```

添加计划记录（示例）：

```powershell
.\.venv\Scripts\python.exe scripts\archive_manager.py add-plan `
  --id 2026-01_de_langchain_phase0-7 `
  --title "去 LangChain/LangGraph 迁移计划（Phase 0-7）" `
  --start-date 2026-01-01 `
  --end-date 2026-01-03 `
  --summary-file archives/plans/2026-01_de_langchain_phase0-7/summary.md
```

扫描并登记归档产物（会记录文件路径/大小/sha256）：

```powershell
.\.venv\Scripts\python.exe scripts\archive_manager.py scan-artifacts `
  --plan-id 2026-01_de_langchain_phase0-7 `
  --root archives/plans/2026-01_de_langchain_phase0-7
```

查看计划：

```powershell
.\.venv\Scripts\python.exe scripts\archive_manager.py show --plan-id 2026-01_de_langchain_phase0-7
```

