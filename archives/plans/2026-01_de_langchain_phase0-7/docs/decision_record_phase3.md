# 决策记录：Phase 3（Native OpenAI-compatible 后端）

日期：2026-01-01

## 背景 / 目标

- 进入 Phase 3：在不移除旧实现的前提下，新增 `OpenAICompatibleBackend`（自研后端），用于接入**任意 OpenAI API 兼容**的第三方 LLM 提供商。
- 该阶段目标是“并行灰度 + Golden 对比”：默认仍走 `langchain` 后端，`native` 后端仅在显式开启时生效，确保可回滚。

## MCP Research（摘要）

1. Context7
   - 解析并使用 `openai/openai-python`（`/openai/openai-python`）文档：
     - Chat Completions streaming：`client.chat.completions.create(..., stream=True)`，通过 `chunk.choices[0].delta.content` 获取增量文本
     - SDK 也提供 `client.chat.completions.stream(...)` 的事件接口（`event.type == "content.delta"` 等），但 Phase 3 先以 `create(stream=True)` 为共同交集实现

2. tavily_local
   - 检索到可用资料：
     - `openai/openai-python`（官方 SDK 仓库，包含 Chat Completions 与流式示例入口）
     - OpenAI Developer Community 讨论：流式 function/tool calls 的 chunk/delta 结构与“增量拼接”策略

3. Fetch
   - `platform.openai.com` 文档抓取返回 `403`（无法直接用 Fetch 阅读官方文档细节）。
   - 作为替代：
     - Fetch 读取 `openai/openai-python` 仓库首页（可获取 SDK 的基本用法与 streaming 概览）
     - Fetch 读取 OpenAI Developer Community 线程（可获取 `ChatCompletionChunk` 的 `delta.tool_calls` 形状与拼接方式）

## 关键结论（用于落地实现）

1. **优先采用 Chat Completions API（OpenAI-compatible 的共同交集）**
   - 许多第三方提供商实现的是 `/v1/chat/completions`，而非 Responses API。
   - 因此 Phase 3 后端以 `client.chat.completions.create(..., stream=True)` 为主。

2. **流式输出解析策略**
   - 文本：`chunk.choices[0].delta.content` → `TextDeltaEvent`
   - 工具调用：`chunk.choices[0].delta.tool_calls`（可能分多段返回，且 id/name/arguments 可能只在部分 chunk 出现）
     - 输出 `ToolCallDeltaEvent(index, tool_call_id?, name?, arguments_delta?)`
     - Phase 4 再引入“聚合器”把 delta 拼回最终 tool_call（与 LangChain 无关）
   - 兼容旧/偏差实现：`delta.function_call` 作为降级路径（部分兼容网关仍在使用）

3. **base_url 兼容策略**
   - 对“只给 host”的配置做规范化：自动补 `/v1`，避免用户配置差异导致 404。
   - 维持现有 `src/llm/factory.py` 的 base_url 规则一致性，减少迁移风险。

4. **Gate#3 的 Golden 验收策略**
   - Phase 3 仍未把 `native` 后端接入主 Agent（`Agent.llm_backend=native` 仍是占位），因此 Golden 以 ChatBackend 层为准（`archives/plans/2026-01_de_langchain_phase0-7/scripts/de_langchain_capture_golden.py --runner backend`）。
   - 为了降低随机性、提升可复现性：backend runner 默认使用 `temperature=0`（可用 `--temperature` 覆盖）。

## 风险 / 回滚点

- 风险：不同提供商对 tool_calls 的 streaming 形状存在差异（例如 index 缺失、id 为空、arguments 分片等）。
- 回滚点：保持默认 `settings.agent.llm_backend=langchain`；如 `native` 回归，直接切回 `langchain` 即可。
