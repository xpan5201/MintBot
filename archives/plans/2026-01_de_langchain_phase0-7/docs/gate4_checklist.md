# Gate#4 Checklist（Phase 4 完成标准）

> Gate#4 的定位：自研 Tool-Loop（ToolRunner + AgentRunner），逐步替代 LangChain Agent 循环；
> 默认仍走 `langchain`，新路径必须可控、可回滚、可验证。

验证记录：

- ✅ 2026-01-02：进入 Phase 4（ToolRunner/AgentRunner 以独立模块形式新增 + 单测）
- ✅ 2026-01-02：主链路接入 `llm_backend=native`（默认仍为 langchain），并跑通 pytest/black/flake8/mypy
- ✅ 2026-01-02：Owner 验收通过（工具链路等价 + GUI 流式连续性）

## 1) ToolRunner（必须）

- [x] `src/llm_native/tool_runner.py`：实现 `ToolRunner`（解析 arguments JSON → 调用项目工具执行器 → 产出 tool messages）
- [x] 输入防御：arguments 非法 JSON 不抛异常（作为 tool 输出回填，便于模型自修正）
- [x] 取消支持：在工具调用边界点检查 `cancel_event`
- [ ] 并发执行（可选）：支持多 tool_call 并发（后续增量实现，必须可控）

## 2) AgentRunner（必须）

- [x] `src/llm_native/agent_runner.py`：实现 `NativeToolLoopRunner`（基于 ChatBackend.stream + ToolCallAccumulator 驱动 tool-loop）
- [x] 护栏：`max_tool_rounds` 防止无限循环
- [x] 失败方式明确：backend 异常 → `ErrorEvent` + `DoneEvent(finish_reason=error)`
- [x] Streaming 语义对齐：主链路复用现有 watchdog/节流/工具直出兜底策略

## 3) 接入策略（必须）

- [x] 脚本级开关：`archives/plans/2026-01_de_langchain_phase0-7/scripts/de_langchain_capture_golden.py --runner backend --tools` 可在本地验证 Tool-Loop
- [x] feature flag：`settings.agent.llm_backend = langchain | native`（默认 langchain；native 仅灰度）
- [x] 回滚：native 初始化失败会自动回退到 langchain；任何回归可手动切回 `langchain`（不改用户配置/数据结构）

## 4) 测试（必须）

- [x] 新增 `tests/test_llm_native_agent_runner_tool_loop.py`：覆盖“工具调用→回填→继续生成”与“非法参数降级”
- [x] pytest 全绿（不回归）

## 5) 质量门禁（必须全绿）

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m black src\ tests\ examples\
.\.venv\Scripts\python.exe -m flake8 src\ tests\ examples\ --max-line-length=100 --ignore=E203,W503
.\.venv\Scripts\python.exe -m mypy src\ --ignore-missing-imports
```

## 6) Owner 验收点（接入主链路后必须确认）

- [x] 工具链路等价（含失败/超时/限频）：输出语义可接受，且不泄露原始 tool trace
- [x] GUI 流式输出连续性 OK：不阻塞主线程、不出现长时间卡顿
