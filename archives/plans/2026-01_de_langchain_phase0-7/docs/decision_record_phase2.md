# 决策记录：Phase 2（Message 模块起步）

日期：2026-01-01

## 背景 / 目标

- 进入 Phase 2：实现 `LangChainBackend(Adapter)`，并从 **Message/叶子模块** 开始改造，逐步降低调用方对 LangChain 的直接依赖。

## MCP Research（摘要）

- Context7：确认 LangChain streaming tool calls 的 `AIMessageChunk.tool_call_chunks` / `AIMessage.tool_calls` 形状与示例用法。
- tavily_local + Fetch：确认 LangChain 生态中存在 **content/arguments 为 `None` 导致校验错误** 的已知问题与讨论（见 langchain-ai/langchain issue #31536）。
- Context7：确认 Chroma Python API（PersistentClient/Collection.add/query/get/delete）与 OpenAI Python embeddings 接口用法（OpenAI-compatible）。

## 关键取舍

1. **assistant message 的 “tool-only” 语义**
   - 现状：项目 `Message(content=None, tool_calls=[...])` 合理表示“无文本，仅工具调用”。
   - 适配到 LangChain：当前环境中 `AIMessage/AIMessageChunk` 对 `content=None` 会触发校验失败，因此统一归一化为 `content=\"\"`。

2. **工具调用参数（args）解析策略**
   - `ToolCall.arguments_json` → LangChain `tool_calls[].args`：best-effort `json.loads`，失败则落 `{}`（避免流式中断）。

## 落地项（本轮）

- 新增 `src/llm_native/langchain_messages.py`：Message ↔ LangChain message 转换（含 tool_calls 解析）
- 新增 `src/llm_native/langchain_backend.py`：`LangChainBackend(ChatBackend)`（complete/stream）
- 叶子模块迁移：`src/multimodal/vision.py` 改用自研 `Message`，通过转换层再调用 `llm.invoke()`
- 叶子模块迁移：`src/utils/chroma_helper.py` 移除 `langchain-chroma/langchain-openai` wrapper，改为直连 `chromadb` + `openai` embeddings
- 工具协议层补齐：新增 `ToolRegistry.get_tool_specs()` 导出 OpenAI-compatible `ToolSpec`，为 Phase 3+ native 后端铺路
- 触点收敛：将 `src/**` 内所有 `langchain*/langgraph*` import 收敛到 `src/llm_native/*`（保留行为不变，降低后续迁移面）
- Golden 工具：新增 `archives/plans/2026-01_de_langchain_phase0-7/scripts/de_langchain_compare_golden.py`（对比两份 golden，输出差异摘要）

## 风险 / 回滚点

- 回滚策略：保持 `settings.agent.llm_backend=langchain`（默认），如有回归可直接回退 `src/multimodal/vision.py` 的改动并暂不启用 Phase2 适配器。
- 检索回滚：如发现 Chroma 直连不稳定，可回退 `src/utils/chroma_helper.py` 到旧版（LangChain wrapper）并保持对外接口不变（短期过渡用）。
