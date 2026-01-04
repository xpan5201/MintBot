# Gate#7 Checklist（Phase 7 完成标准）

> Gate#7 的定位：彻底移除 langchain*/langgraph*/langsmith* 依赖与代码残留，保持项目稳定可运行（native 后端为唯一实现）。
>
> 约束：稳定优先；任何回归必须可回滚（git）；严禁“带病删依赖”导致运行时 ImportError/空回复/GUI 卡死。

前置条件：

- [x] Gate#6 Owner 验收通过（见 `gate6_checklist.md`）
- [x] Phase 7 MCP Research Loop 完成（Context7 + tavily_local + Fetch）并形成《决策记录》（见 `decision_record_phase7.md`）

## 1) 零引用扫描（必须）

> 说明：此处“零引用”指 **代码层**（`src/tests/examples/scripts`），不强制清理文档里对“迁移历史/决策”的引用。

- [x] 审计脚本：`archives/plans/2026-01_de_langchain_phase0-7/scripts/de_langchain_audit_touchpoints.py --fail-if-found` 为 0 命中
- [x] rg 快检（仅限代码）：`rg -n "\\blangchain\\b|\\blangchain[_-]\\w+|\\blanggraph\\b|\\blangsmith\\b" src tests examples scripts` 为 0 命中

## 2) 依赖移除（必须）

- [x] `pyproject.toml` 移除（至少）：`langchain*`、`langgraph*`、`langsmith*` 及相关 provider 包
- [x] 使用 `uv remove ...` 或等价方式同步更新 `pyproject.toml` + `uv.lock`
- [x] `uv lock` / `uv lock --check` 通过（锁文件与 pyproject 一致）

## 3) 运行时行为（必须）

- [x] `Agent.llm_backend` 相关逻辑清理：不再存在 “langchain 回退/兼容层” 路径
- [x] `config.dev.yaml` / `config.user.yaml` 不再暴露无效配置键（必要时保留兼容映射但必须无副作用）
- [x] 运行时无 ImportError（尤其是 GUI 启动、首轮对话、工具调用、记忆写入/检索）

## 4) 测试与门禁（必须全绿）

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m black src\ tests\ examples\
.\.venv\Scripts\python.exe -m flake8 src\ tests\ examples\ --max-line-length=100 --ignore=E203,W503
.\.venv\Scripts\python.exe -m mypy src\ --ignore-missing-imports
```

## 5) Owner 冒烟（必须确认）

- [x] GUI 启动/关闭正常；聊天流式输出连续性 OK
- [x] 至少 1 次工具调用链路可用（tool-loop → tool.result → 最终回复）
- [x] 记忆写入/检索不阻塞主线程、重启后仍可读到长期记忆

## 6) 验证记录

- [x] 2026-01-02：里程碑：完成 Phase 7 决策记录与工具系统适配（脱离 LangChain `StructuredTool`）。
- [x] 2026-01-03：Gate#7 自动化门禁通过（touchpoints=0、uv lock check 通过、pytest/black/flake8/mypy 全绿）。
- [x] 2026-01-03：Owner：Gate#7 验收通过（GUI/工具/记忆冒烟）。
- [x] 2026-01-03：末尾检查：复跑 touchpoints/rg + pytest/black/flake8/mypy 通过（Phase 7 善后确认）。
