# 归档摘要：去 LangChain/LangGraph 迁移计划（Phase 0-7）

Plan ID：`2026-01_de_langchain_phase0-7`  
时间：2026-01-01 ～ 2026-01-03  

## 目标

- 彻底移除 `langchain*` / `langgraph*` / `langsmith*` 依赖与代码触点
- 统一走 OpenAI-compatible 接口（多提供商接入），保留低延迟流式体验与工具调用语义
- 稳定优先：门禁（pytest/black/flake8/mypy）全绿 + GUI/流式/工具/记忆冒烟

## 主要产物（已归档）

- 文档：`archives/plans/2026-01_de_langchain_phase0-7/docs/`（decision records、gate checklists、touchpoints、provider matrix）
- 脚本：`archives/plans/2026-01_de_langchain_phase0-7/scripts/`（golden 录制/对比、触点审计）
- 测试数据：`archives/plans/2026-01_de_langchain_phase0-7/data/`（touchpoints JSON、golden JSON）
- 规划图：`archives/plans/2026-01_de_langchain_phase0-7/flowchart_TD.txt`

## 验收（摘要）

- 触点清零：审计脚本 + rg 快检 0 命中
- 依赖移除：`uv lock --check` 通过
- 质量门禁：`pytest`/`black`/`flake8`/`mypy` 全绿

## 回滚点

- 代码回滚：以 `git diff`/`git checkout -- <path>` 为准；归档目录不参与运行时路径
- 档案库：`archives/archive.sqlite3` 可整体删除并重新生成（不会影响运行）

