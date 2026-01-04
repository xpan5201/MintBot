# 决策记录：Phase 5（去 LangGraph/middleware → 自研 Pipeline）

日期：2026-01-02

## 背景 / 目标

- Gate#4 已完成：native(OpenAI-compatible) + 自研 Tool-Loop 已接入主链路，并通过 Owner 验收。
- Phase 5 的目标是在不破坏体验的前提下，逐步移除 native 路径对 LangGraph/middleware 的依赖，把关键能力迁移为自研 Pipeline stages：
  - 工具筛选（tool selector）
  - 上下文编辑（context editing / tool uses trim）
  - 工具调用限制（tool call limit）
  - 工具权限裁剪（permission scoped tools）
  - 工具追踪（tool trace）

## 范围 / 非目标

- 范围：仅针对 `llm_backend=native` 的推理链路逐步替换；默认 `langchain` 仍保持稳定不动。
- 非目标：本阶段不做 Phase 7 的“删依赖 + uv lock”；不做大规模 prompt/角色系统重构。

## 现状盘点（需要替换的职责映射）

现有 LangChain Agent middleware 栈（`src/agent/core.py::_build_agent_middleware_stack`）：

1. `ToolTraceMiddleware`：记录工具调用轨迹 + 裁剪输出（用于 watchdog/兜底重写）
2. `MintChatToolSelectorMiddleware`：工具预筛选 + LLM 结构化筛选（短超时/熔断/缓存）
3. `ContextEditingMiddleware + ClearToolUsesEdit`：裁剪历史工具调用痕迹，降低 token 消耗
4. `ToolCallLimitMiddleware`：限制单轮工具连环调用次数
5. `PermissionScopedToolMiddleware`：按运行时 profile 裁剪工具集合

Phase 5 计划把上述职责迁移为 pipeline stages（native 路径），并保留可回滚开关。

## MCP Research Loop（Phase 5）

完成日期：2026-01-02

1. Context7
   - OpenAI Python SDK（`/openai/openai-python`）确认两条可用路径：
     - `client.chat.completions.create(stream=True)`：返回 SSE chunks（`choices[0].delta.content`）。
     - `client.chat.completions.stream(...)`：对 `.create(stream=True)` 的包装，提供更细粒度事件 API，且会自动累积 delta。
   - Tool calling 在 streaming 下需要“累积 arguments delta”；SDK 的事件流会提供：
     - `tool_calls.function.arguments.delta` / `tool_calls.function.arguments.done`（含累积后的 `arguments`）。
   - 超时/重试是客户端级能力：`OpenAI(max_retries=..., timeout=...)`；`timeout` 可用 `httpx.Timeout` 进行分项控制。
2. tavily_local（优先官方来源）
   - OpenAI Function calling guide：明确“工具调用 5 步流程”，并说明 streaming 下会以 `arguments delta` 分段输出，需要在应用侧聚合。
   - openai/openai-python README：Chat Completions 属于“previous standard（supported indefinitely）”，因此本项目继续以 Chat Completions 作为 OpenAI-compatible 兼容基线是合理的（尤其是为了覆盖第三方提供商）。
3. Fetch
   - 已 Fetch（raw）openai/openai-python 文档：
     - `helpers.md`：`.chat.completions.stream()` 的事件类型清单（含 tool-call arguments delta/done 事件）。
     - `README.md`：明确 Chat Completions “supported indefinitely”。
   - 直接 Fetch `platform.openai.com` 在当前环境返回 403（禁止抓取），改用 `tavily-extract` 提炼 Function calling guide 的关键段落。

4. tavily_local + Fetch（Golden 资产方法）
   - Golden/Approval Testing 的核心是：把系统输出落盘为“可人工审阅的基线”，后续改动用对比工具验证回归；产出文件应便于 review/定位差异，并避免把“不可读的大块输出”当成测试通过标准。
   - 本项目采用“手动录制 + 量化对比”的 Golden：用 `archives/plans/2026-01_de_langchain_phase0-7/scripts/de_langchain_capture_golden.py` 录制 JSON（文本 chunks + 首包/耗时 + tool 事件摘要），用 `archives/plans/2026-01_de_langchain_phase0-7/scripts/de_langchain_compare_golden.py` 做阈值化对比（文本相似度/首包差异/事件要求/Stage 要求），用于守护“流式体验稳定性”。  

5. Context7 + tavily_local + Fetch（LangGraph 类型对照，用于 Gate#5 §4 去依赖）
   - Gate#5 的目标是让 native 路径不再依赖 LangGraph/middleware；但为了保证“可解释且可回滚”，需要确认 LangGraph 中 `Command` / `ToolCallRequest` 的真实语义与字段形状。
   - `Command` 允许把“state update + goto/resume”打包返回（本项目 native tool-loop 不采用该机制，避免耦合与行为漂移）。
   - `ToolCallRequest` 是 tool-call 拦截器请求对象（包含 `tool_call/tool/state/runtime` + `override()` 的不可变替换模式）；本项目 native 路径以自研 `ToolRunner` + `ToolTraceRecorder` 为边界，不再依赖该对象。

参考来源（本轮实际使用）：  
- https://raw.githubusercontent.com/openai/openai-python/main/helpers.md  
- https://raw.githubusercontent.com/openai/openai-python/main/README.md  
- https://platform.openai.com/docs/guides/function-calling（Fetch=403，tavily-extract）  
- https://raw.githubusercontent.com/approvals/go-approval-tests/master/README.md  
- https://www.codurance.com/publications/2012/11/11/testing-legacy-code-with-golden-master  
- https://github.com/langchain-ai/langgraph/blob/main/docs/docs/how-tos/tool-calling.md  
- https://raw.githubusercontent.com/langchain-ai/langgraph/main/libs/langgraph/langgraph/types.py  
- https://raw.githubusercontent.com/langchain-ai/langgraph/main/libs/prebuilt/langgraph/prebuilt/tool_node.py  

落地（由以上资料为基底，非照抄）：  
- `src/llm_native/openai_backend.py` 的 `OpenAICompatibleBackend.stream()`：默认以兼容性优先，所有 OpenAI-compatible 提供商都可走 `.create(stream=True)` 的 raw chunk 迭代；仅当目标为官方 OpenAI 端点（`*.openai.com`）且 SDK 提供 `.chat.completions.stream()` 时，才优先使用该 helper（仅消费 `ChunkEvent` 的 raw chunk，以便复用既有 chunk 解析逻辑，同时保证响应能被正确关闭并受益于上游对异常 SSE 事件的过滤）。另：部分 OpenAI-compatible 网关可能会触发 SDK 的 `AssertionError`（疑似源于 `assert_never` 对未知 streaming 事件类型的防御），因此对官方端点的 helper 路径也实现了“未输出任何 chunk 前”的 best-effort 回退到 `.create(stream=True)`，避免 tool-loop 直接失败并提升鲁棒性。
- `archives/plans/2026-01_de_langchain_phase0-7/scripts/de_langchain_capture_golden.py`：当 `--runner backend --tools` 且未传 `--prompt` 时，使用内置“无副作用”工具 prompt（`get_current_time` + `calculator`）以提高 tool-loop 触发概率，避免 compare 时报 “缺少 tool.result”。  
- `archives/plans/2026-01_de_langchain_phase0-7/scripts/de_langchain_compare_golden.py`：`gate5-native-pipeline` preset 聚焦“pipeline 完整性 + tool-loop 事件”，并允许 live-run 的合理波动（网络抖动/轻微措辞差异）；因此仅在用户未显式传参时放宽默认阈值（`min_text_similarity`/首包延迟差/文本长度与 chunks 差异）。性能回归仍以 Gate#5 的性能条目单独评估与守护。  
- Gate#5 §4 去依赖验证：native 路径不再引用 LangGraph 的 `Command/ToolCallRequest` 或 LangChain 的 `AgentMiddleware/ModelRequest/ModelResponse`；仅保留 `src/llm_native/langgraph_types.py` / `src/llm_native/langchain_*` 作为双后端稳定期的兼容层，直到 Phase 7 再统一清理。  

## 关键设计决策（已确认并落地第一小步）

1. Pipeline 接口边界（先小步落地）
   - 先实现并接入：`pre_model` / `post_model` / `pre_tool_calls` / `post_tool_messages` / `stream_filter`（均默认 no-op）。
   - `post_model` 在 native tool-loop 中用于“模型返回后”的统一观察/可选微调（当前阶段保持默认不改行为）。
2. feature flag
   - 新增 `Agent.native_pipeline_enabled`（默认 `false`），仅影响 `llm_backend=native` 路径。
3. 错误/降级策略（稳定优先）
   - pipeline stage 任何异常：记录 warning（含堆栈）并跳过该 stage，不影响主流程。
4. Phase 5 的第一小步（本轮实施）
   - 只引入 Pipeline 协议层 + 接入点（默认关闭，不改变行为）。
   - 后续 stage 迁移按 `phase5_pipeline_design.md` 的顺序逐步开启与验收。

5. Phase 5 的第二小步（本轮实施）
   - 落地 `PermissionScopedToolsStage`（对齐 `PermissionScopedToolMiddleware` 语义）。
   - 配置键：`Agent.tool_permission_profiles` / `Agent.tool_permission_default` / `Agent.tool_profile`。
   - 稳定优先：如白名单配置错误导致工具集为空，会自动降级为“不过滤”并记录 warning。

6. Phase 5 的第三小步（本轮实施）
   - 落地 `ToolHeuristicPrefilterStage`（无额外 LLM 调用）。
   - 使用配置：`Agent.tool_selector_enabled` / `Agent.tool_selector_min_tools` / `Agent.tool_selector_max_tools` / `Agent.tool_selector_always_include`。
   - 稳定优先：仅在检测到明确工具意图时收缩工具集；不会产生空工具集（空则自动降级为不过滤）。

7. Phase 5 的第四小步（本轮实施）
   - 落地 `ToolCallLimitStage`（对齐 `ToolCallLimitMiddleware` 的 `tool_call_limit_per_run` 语义）。
   - 配置键：`Agent.tool_call_limit_per_run`（0 表示关闭）。
   - 触发时行为：pipeline 发出可控 abort → native tool-loop 输出 `ErrorEvent(ToolCallLimitError)` + `DoneEvent(tool_call_limit)`。
   - 单测：`tests/test_llm_native_pipeline.py`。

8. Phase 5 的第五小步（本轮实施）
   - 落地 `ContextToolUsesTrimStage`（对齐 `ContextEditingMiddleware + ClearToolUsesEdit` 的“裁剪历史 tool uses”目标）。
   - 配置键：`Agent.tool_context_trim_tokens`（0 表示关闭）。
   - 稳定优先：只裁剪 `assistant.tool_calls` + `tool` 消息；保护最近一组 tool-call 结果以确保 tool-loop 正常继续。
   - 单测：`tests/test_llm_native_pipeline.py`。

9. Phase 5 的第六小步（本轮实施）
   - 落地 `ToolTraceStage`（对齐 `ToolTraceMiddleware` 的“工具输出截断”能力）。
   - 配置键：`Agent.tool_output_max_chars`（0 表示不截断）。
   - 说明：工具调用轨迹（参数/输出/错误）由 `ToolRunner` 通过 `tool_trace_recorder_var` 记录；stage 负责在进入下一轮模型调用前截断 tool 消息内容以避免 prompt 膨胀。
   - 单测：`tests/test_llm_native_pipeline.py`。

10. Phase 5 的第七小步（本轮实施）
   - 落地 `ToolLlmSelectorStage`（对齐 `MintChatToolSelectorMiddleware` 的“LLM 选工具”部分）。
   - 配置键：`Agent.tool_selector_enabled` / `Agent.tool_selector_in_fast_mode` / `Agent.tool_selector_min_tools` / `Agent.tool_selector_max_tools` / `Agent.tool_selector_timeout_s` / `Agent.tool_selector_disable_cooldown_s` / `Agent.tool_selector_model`。
   - 约束：fast_mode 默认跳过；工具数 < min_tools 跳过；仅在“用户 turn”的首轮调用启用（避免工具回填后的重复筛选）。
   - 稳定优先：失败/超时/解析失败 → fail-open（不过滤）；并触发熔断（cooldown） + LRU 缓存（相同输入复用）。
   - 实现细节：Selector 调用使用短 timeout + `max_retries=0`；输入仅包含 tool names（不传 schemas）；输出宽松 JSON 解析（提取首个 JSON 片段）。
   - 单测：`tests/test_llm_native_pipeline.py`（过滤、缓存、熔断）。

## 风险 / 回滚点

- 风险：工具筛选或上下文裁剪过度会导致“能力下降/记忆缺失/幻觉增加”。
- 回滚点：
  - 关闭 Phase 5 pipeline 开关（建议默认关闭）；仍可继续使用 Gate#4 的 native tool-loop。
  - 或直接 `settings.agent.llm_backend=langchain` 回退到稳定链路。

---

## 追加记录：Live2D 隐藏指令泄漏修复（2026-01-02）

### 问题

GUI 消息气泡中出现 Live2D 事件戳（例如：`[live2d:{"event":"happy","intensity":0.8,"hold_s":3}]`），影响角色扮演体验与沉浸感。

### 根因

- 既定“隐藏指令”规范为双括号：`[[live2d:...]]`（见 system prompt 约定）。
- 但部分回复会输出单括号形式 `[live2d:...]`（缺失一个 `[` / `]`），导致 GUI 的指令剥离逻辑无法识别，从而把控制指令当作可见文本渲染。

### 修复（稳定优先，最小改动）

- GUI 侧指令解析器兼容单括号形式（仍以双括号为推荐/权威语法）：
  - `src/gui/live2d_state_event.py`：解析/流式过滤同时支持 `[[live2d:...]]` 与 `[live2d:...]`
  - `src/gui/light_chat_window.py`：显式指令检测条件同步兼容
- 单测覆盖：`tests/test_live2d_state_directives.py` 新增单括号与跨 chunk 边界用例。

### 后续最优方向（不在本次落地）

为从根源避免“控制信号混入可见文本”，后续可考虑把 Live2D 指令升级为 **结构化输出/函数工具调用**（在 OpenAI-compatible 后端中以 tool call 或 structured output 承载），做到“文本=纯可见内容、事件=单独通道”。参考：  
- https://raw.githubusercontent.com/openai/openai-python/main/helpers.md（structured outputs / tool call parsing helpers）
