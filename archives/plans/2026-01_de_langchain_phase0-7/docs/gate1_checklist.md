# Gate#1 Checklist（Phase 1 完成标准）

> Gate#1 的定位：**只新增协议层/抽象**，不改动现有 LangChain 链路。  
> 达标后才进入 Phase 2（LangChainBackend 适配器）或 Phase 3（native 后端实现）。

验证记录：

- ✅ 2026-01-01：已进入 Phase 1，并通过 pytest/flake8/mypy 门禁（详见本轮日志）

## 1) 协议层代码（必须）

- [x] `src/llm_native/messages.py`：Message 协议（对齐 OpenAI-compatible messages）
- [x] `src/llm_native/events.py`：StreamEvent 协议（TextDelta/ToolCallDelta/ToolResult/Error/Done）
- [x] `src/llm_native/tools.py`：ToolSpec/ToolRegistry（strict JSON schema 入口）
- [x] `src/llm_native/backend.py`：ChatBackend 抽象（complete/stream）
- [x] **禁止接入现有链路**：不修改 `src/agent/*` 的运行路径（Phase 2 才开始改调用方）

## 2) 最小单测（必须）

- [x] `tests/test_llm_native_messages.py`
- [x] `tests/test_llm_native_tool_call_accumulator.py`
- [x] `tests/test_llm_native_tools.py`

## 3) 质量门禁（必须全绿）

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m black src\ tests\ examples\
.\.venv\Scripts\python.exe -m flake8 src\ tests\ examples\ --max-line-length=100 --ignore=E203,W503
.\.venv\Scripts\python.exe -m mypy src\ --ignore-missing-imports
```

## 4) 进入 Phase 2 的前置确认（owner 确认）

- [x] 确认 Phase 2 的目标：把 LangChain 封装成 `LangChainBackend(Adapter)`，对外只吐出 `StreamEvent`
- [x] 确认 Phase 2 的改动范围（优先从“叶子模块”开始，避免动 `src/agent/core.py` 主干）

验证记录补充：

- ✅ 2026-01-01：owner 确认进入 Phase 2，且从 Message 模块/叶子模块开始落地
