# 决策记录：Phase 4（自研 Tool-Loop / AgentRunner）

日期：2026-01-02

## 背景 / 目标

- 进入 Phase 4：替代 LangChain Agent 循环（工具调用与回填），逐步解除对 `langchain.agents/*` 的依赖。
- 该阶段目标是先把“工具协议 + 工具执行 + 回填循环”拆出来，形成**可测试、可回滚**的自研 Tool-Loop。
- 默认产品路径仍保持 `langchain`，新实现必须 **feature flag** 控制，避免破坏性变更。

## MCP Research（摘要）

1. Context7
   - `openai/openai-python`：
     - 工具调用：Chat Completions 的 `tools` 参数与 `message.tool_calls` 形状
     - Streaming：工具调用会以增量形式出现在 `delta.tool_calls[*].function.arguments` 中，需要按 `index` 聚合
     - SDK 提供 `.chat.completions.stream()` 事件流（含 `tool_calls.function.arguments.delta/done`），但为兼容多提供商，本项目继续使用 `create(stream=True)` 作为共同交集
   - `platform.openai`：
     - `tool_choice` 支持 `none/auto/required/指定工具` 的控制策略
     - Streaming tool_call delta 聚合示例与注意事项

2. tavily_local
   - 参考官方文档与社区经验：Streaming 下 tool_calls 需要按 `index` 聚合，`id/name` 可能只在首段出现；并发 tool_calls 时可能交错出现

3. Fetch
   - 抓取 `openai/openai-python` 的 `helpers.md`（Streaming Events / tool_calls delta/done 说明），用于实现与对齐

## 关键结论（用于落地实现）

1. **工具调用的消息回填顺序（Chat Completions 兼容）**
   - 当模型发起工具调用：需要在历史消息中追加一条 `assistant` 消息（`tool_calls=[...]`，通常 `content=None`）
   - 执行工具后：对每个 tool_call_id 追加一条 `tool` 消息（`role=tool` + `tool_call_id` + `content`）
   - 再次请求模型：带上上述消息，直到模型结束（`finish_reason=stop`）

2. **Streaming tool_calls 的聚合策略**
   - 需要按 `tool_call.index` 聚合 `arguments_delta`，并补齐 `tool_call_id/name`
   - 并发 tool_calls（多 index）时可能交错出现，必须支持“多路聚合”

3. **稳定性护栏**
   - 必须有 `max_tool_rounds`（防止工具循环无穷）
   - 工具执行必须有超时（并把超时/参数解析失败等错误作为 tool 输出回填，允许模型自我修正）
   - 取消必须可控（在工具调用边界点检查 `cancel_event`）

## 落地实现（本轮新增）

- `src/llm_native/tool_runner.py`：`ToolRunner`（解析 arguments JSON → 调用现有 `ToolRegistry.execute_tool` → 产出 tool messages）
- `src/llm_native/agent_runner.py`：`NativeToolLoopRunner`（使用 `ChatBackend.stream` + `ToolCallAccumulator` 驱动 tool-loop）
- `src/agent/core.py`：主链路接入 `llm_backend=native`（默认仍为 `langchain`），并复用现有流式 watchdog/节流/兜底逻辑
- `src/llm_native/messages.py`：补齐 `messages_from_openai()`（dict→Message 转换），用于主链路构建原生请求
- `src/llm_native/openai_backend.py`：当 `LLM.key` 为空时不传空字符串给 SDK（允许通过环境变量提供 key）
- `tests/test_llm_native_agent_runner_tool_loop.py`：覆盖“工具调用→回填→继续生成”基本链路与“非法 JSON 参数”降级

## 风险 / 回滚点

- 风险：不同提供商的 `tool_calls` streaming 形状存在差异（缺失 id/name、arguments 分片顺序不同等）。
- 回滚点：`settings.agent.llm_backend=langchain`（默认值）；native 初始化失败也会自动回退到 langchain。
