# Gate#2 Checklist（Phase 2 完成标准）

> Gate#2 的定位：**把 LangChain 封装进 `LangChainBackend(Adapter)`**，让调用方逐步只依赖
> `ChatBackend/Message/ToolSpec/StreamEvent`，并通过 Golden 对比确保“行为等价/差异可解释”。

验证记录：

- ✅ 2026-01-01：进入 Phase 2（从 Message/叶子模块开始），新增 LangChainBackend + message 转换，并通过门禁
- ✅ 2026-01-01：运行 `archives/plans/2026-01_de_langchain_phase0-7/scripts/de_langchain_capture_golden.py` 生成基线（Owner 已验证）
- ✅ 2026-01-01：GUI 冒烟通过（Owner 已验证）

## 1) LangChainBackend 适配器（必须）

- [x] `src/llm_native/langchain_messages.py`：`Message` ↔ LangChain message 转换
- [x] `src/llm_native/langchain_backend.py`：`LangChainBackend(ChatBackend)`（complete/stream）
- [x] **边界清晰**：LangChain 相关 import 仅存在于 `src/llm_native/*`（调用方不再直连 LangChain）

## 2) 调用方改造（优先叶子模块）

- [x] `src/multimodal/vision.py`：不再直接构造 LangChain `HumanMessage`（改用自研 `Message`）
- [x] `src/utils/chroma_helper.py`：不再使用 LangChain 的 Chroma/OpenAIEmbeddings wrapper（改为直连 chromadb + OpenAI-compatible embeddings）
- [x] 工具协议层：`ToolRegistry.get_tool_specs()`（导出 OpenAI-compatible `ToolSpec`，为 Phase 3+ native 后端铺路）
- [ ] 其他叶子模块逐步迁移（每次只改 1-2 个，保证可回滚）

## 3) Golden 对比（必须）

- [x] 运行 `archives/plans/2026-01_de_langchain_phase0-7/scripts/de_langchain_capture_golden.py` 生成基线（LangChain 后端，Owner 已验证）
- [x] 运行 `archives/plans/2026-01_de_langchain_phase0-7/scripts/de_langchain_compare_golden.py`（或新增对比逻辑）验证差异可解释（Owner 已验证）
- [x] GUI 冒烟：流式输出无明显卡顿/断流回归（主线程不阻塞，Owner 已验证）

## 4) 质量门禁（必须全绿）

```powershell
.\\.venv\\Scripts\\python.exe -m pytest -q
.\\.venv\\Scripts\\python.exe -m black src\\ tests\\ examples\\
.\\.venv\\Scripts\\python.exe -m flake8 src\\ tests\\ examples\\ --max-line-length=100 --ignore=E203,W503
.\\.venv\\Scripts\\python.exe -m mypy src\\ --ignore-missing-imports
```

## 5) Owner 验收点（必须确认）

- [x] 迁移范围可接受：未出现大范围行为变更（Owner 已验证）
- [x] 可回滚：`settings.agent.llm_backend=langchain` 仍可无损运行（Owner 已验证）
