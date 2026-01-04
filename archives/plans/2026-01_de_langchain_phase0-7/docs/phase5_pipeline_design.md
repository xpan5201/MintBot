# Phase 5 设计草案：自研 Pipeline（替代 LangChain middleware）

> 目的：在实施 Phase 5 前，把“接口形状/阶段职责/迁移步骤”写清楚，便于最小风险落地与回滚。
>
> 注意：本文件是“设计草案”，不等同于实施；待你确认后才开始编码接入。

## 1) Pipeline 的最小协议（建议）

### PipelineRequest（建议字段）

- `messages`: list[Message]（自研 message 协议）
- `tools`: list[ToolSpec]（OpenAI tools schema）
- `runtime`: dict（运行时上下文：例如 tool_profile）
- `config`: dict（超时/阈值/熔断等）

### PipelineResponse（建议字段）

- `events`: Iterator[StreamEvent]（流式输出）
- `final_text`: str（非流式输出）

## 2) Stage 职责与顺序（建议）

建议顺序（从“更安全/纯逻辑”到“有副作用”）：

1. `ToolTraceStage`（只做记录/裁剪，不改变模型输入）
2. `PermissionScopedToolsStage`（纯过滤：按 profile 裁剪 tools）
3. `ToolHeuristicPrefilterStage`（纯过滤：按关键词/类别缩小 tools）
4. `ToolLLMSelectorStage`（可选：额外一次短超时 LLM 调用；失败必须降级）
5. `ContextEditingStage`（裁剪历史 tool uses；不改 user/system 文本）
6. `ToolCallLimitStage`（强约束：限制 tool-loop 的“可继续轮数/可调用次数”）
7. `StreamScrubberStage`（流式输出清洗：过滤 structured 噪声、工具 trace 外泄）

## 3) 与现有实现的对齐点（Gate#5 验收维度）

- 与 `MintChatToolSelectorMiddleware` 对齐：
  - fast_mode 默认跳过 LLM 筛选（只启发式预筛选）
  - 超时/异常熔断，避免阻塞首包
- 与 `ContextEditingMiddleware + ClearToolUsesEdit` 对齐：
  - 只裁剪“历史工具痕迹”，避免污染人格/记忆提示
- 与 `ToolCallLimitMiddleware` 对齐：
  - 避免无限工具自旋（现有 Gate#4 已有 `max_tool_rounds`，Phase 5 可进一步细化）
- 与 `ToolTraceMiddleware` 对齐：
  - 记录工具调用轨迹，供 watchdog 保活与空回复兜底重写使用

## 4) 实施顺序（建议：小步可回滚）

1. 只实现 Pipeline 协议 + No-op stages（不改行为），并加单测
2. 接入到 `llm_backend=native` 路径，增加 `native_pipeline_enabled`（默认 false）
3. 先迁移 **PermissionScopedToolsStage + HeuristicPrefilterStage**（低风险）
4. 再迁移 **ContextEditingStage + ToolCallLimitStage**（中风险）
5. 最后迁移 **ToolLLMSelectorStage**（高风险：额外 LLM 调用，需严格超时/熔断/缓存）
6. Golden 对比 + GUI 冒烟 + 全量门禁，通过后再进入下一 Gate

