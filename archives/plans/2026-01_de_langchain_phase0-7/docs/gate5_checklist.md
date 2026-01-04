# Gate#5 Checklist（Phase 5 完成标准）

> Gate#5 的定位：在不破坏现有体验的前提下，逐步移除 LangGraph/middleware 依赖，
> 将“工具筛选 / 上下文编辑 / 工具限制 / 权限裁剪 / 工具追踪”等能力迁移为 **自研 Pipeline stages**。
>
> 约束：默认链路仍保持 `langchain`；Phase 5 的任何行为变更必须 **feature flag** 可控、可回滚、可验证。

前置条件：

- [x] Gate#4 Owner 验收通过（见 `gate4_checklist.md`）
- [x] Phase 5 MCP Research Loop 完成（Context7 + tavily_local + Fetch）并形成《决策记录》（见 `decision_record_phase5.md`）

## 1) Pipeline 协议层（必须）

- [x] 定义 Pipeline Request/Response 协议（不依赖 langchain/langgraph 类型）
- [x] 定义 Stage 接口（建议按边界拆分；本轮先小步落地一部分，后续补齐）：
  - [x] `pre_model(request) -> request`
  - [x] `post_model(response) -> response`
  - [x] `pre_tool_calls(calls) -> calls`（等价覆盖 pre_tool）
  - [x] `post_tool_messages(results) -> results`（等价覆盖 post_tool）
  - [x] `stream_filter(text_delta) -> text_delta`（可选：流式输出过滤/清洗）
    - [x] 不泄漏“控制指令”到 UI：Live2D 指令 `[[live2d:...]]`（兼容 `[live2d:...]`）必须在显示前剥离并触发事件

## 2) Stage 迁移清单（必须）

目标：与现有 middleware 功能等价（允许差异，但必须可解释且不降低体验）。

- [x] Tool selector stage（对应 `MintChatToolSelectorMiddleware`）
  - [x] 先启发式预筛选（无 LLM 调用、容错；仅在检测到明确意图时才收缩工具集）
  - [x] 再可选 LLM 筛选（短超时、熔断、缓存）
  - [x] fast_mode 下默认跳过（保持首包体验）
- [x] Context editing stage（对应 `ContextEditingMiddleware + ClearToolUsesEdit`）
  - [x] 仅裁剪“历史 tool uses”与结构化噪声，不破坏用户文本与系统提示
  - [x] 预算控制：`tool_context_trim_tokens`
- [x] Tool call limit stage（对应 `ToolCallLimitMiddleware`）
  - [x] 与现有 `tool_call_limit_per_run` 语义对齐（防止自旋）
- [x] Permission scoped tools stage（对应 `PermissionScopedToolMiddleware`）
  - [x] 按 runtime profile 裁剪工具集合（默认 profile 与 fallback 语义一致）
  - [x] 配置键：`Agent.tool_permission_profiles` / `Agent.tool_permission_default` / `Agent.tool_profile`
  - [x] 单测：`tests/test_llm_native_pipeline.py`
- [x] Tool trace stage（对应 `ToolTraceMiddleware`）
  - [x] 对 native tool-loop 保留：记录工具开始/结束、参数、输出/错误（用于 watchdog/兜底重写）
  - [x] 对 langchain path 暂不变（双后端稳定期内不硬切）

## 3) 接入策略（必须）

- [x] feature flag：引入 Phase5 的 pipeline 开关（默认关闭），仅影响 `llm_backend=native` 路径
- [x] 回滚：出现任何回归可立即关闭 pipeline（仍保持 native tool-loop 可用）或切回 `langchain`
- [x] Golden：增加“native+pipeline”对比资产（至少覆盖工具调用/失败/超时/流式连续性）
  - baseline（native tool-loop，不开 pipeline）：
    - 最简（推荐，使用默认输出路径与默认 tool prompt）：  
      - `.\\.venv\\Scripts\\python.exe archives\\plans\\2026-01_de_langchain_phase0-7\\scripts\\de_langchain_capture_golden.py --backend native --runner backend --tools`
    - 或显式指定（便于你自定义 prompt/路径）：  
      - `.\\.venv\\Scripts\\python.exe archives\\plans\\2026-01_de_langchain_phase0-7\\scripts\\de_langchain_capture_golden.py --backend native --runner backend --tools --out archives\\plans\\2026-01_de_langchain_phase0-7\\data\\golden\\native_backend_tool_loop_golden.json --prompt "请使用工具完成一个简单任务（确保触发至少 1 次 tool call）"`
  - candidate（native tool-loop，开启 pipeline）：
    - 最简（推荐，使用默认输出路径与默认 tool prompt）：  
      - `.\\.venv\\Scripts\\python.exe archives\\plans\\2026-01_de_langchain_phase0-7\\scripts\\de_langchain_capture_golden.py --backend native --runner backend --tools --pipeline`
    - 或显式指定（便于你自定义 prompt/路径）：  
      - `.\\.venv\\Scripts\\python.exe archives\\plans\\2026-01_de_langchain_phase0-7\\scripts\\de_langchain_capture_golden.py --backend native --runner backend --tools --pipeline --out archives\\plans\\2026-01_de_langchain_phase0-7\\data\\golden\\native_backend_tool_loop_pipeline_golden.json --prompt "请使用工具完成一个简单任务（确保触发至少 1 次 tool call）"`
  - compare（默认会要求 tool.result 事件 + 关键 pipeline stages 全部出现）：  
    - `.\\.venv\\Scripts\\python.exe archives\\plans\\2026-01_de_langchain_phase0-7\\scripts\\de_langchain_compare_golden.py --preset gate5-native-pipeline`
    - 示例：`records=1 ok=1/1 min_similarity≈0.88`
  - 说明：
    - 当 `--runner backend --tools` 且未传 `--prompt` 时，脚本会使用内置“无副作用”工具 prompt（`get_current_time` + `calculator`）来提高 tool-loop 触发概率，避免 compare 时报 “缺少 tool.result”。
    - 若需要覆盖“失败/超时”，请额外加入会触发工具失败/超时的 prompt（例如：给工具传入非法参数、或调用一个会超时的工具）。  
      该部分因工具集与本机环境不同，建议以 `archives/plans/2026-01_de_langchain_phase0-7/data/golden/*.json` 里的 `records[*].events` 进行人工确认。

## 4) 删除 langgraph/middleware 依赖（Phase 5 目标，但可分步）

- [x] native 路径不再需要 `AgentMiddleware/ModelRequest/ModelResponse/ToolCallRequest/Command`（仅保留 LangChain 兼容层模块）
- [x] `src/llm_native/langgraph_types.py` 在 native 路径不再被引用（保留兼容层直到 Phase 7 清理）

## 5) 测试（必须）

- [x] 单测：Pipeline 协议层接入点（pre_model hook，见 `tests/test_llm_native_pipeline.py`）
- [x] 单测：各 Stage 的输入输出与降级策略（超时/异常/熔断）（见 `tests/test_llm_native_pipeline.py`）
- [x] 集成：native pipeline 下工具调用→回填→继续生成（含多轮工具）（见 `tests/test_llm_native_pipeline.py`）
- [x] 性能：首包/吞吐不退化（与 Gate#4 的指标体系一致）

## 6) 质量门禁（必须全绿）

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m black src\ tests\ examples\
.\.venv\Scripts\python.exe -m flake8 src\ tests\ examples\ --max-line-length=100 --ignore=E203,W503
.\.venv\Scripts\python.exe -m mypy src\ --ignore-missing-imports
```

## 7) Owner 验收点（必须确认）

- [x] GUI 流式输出连续性 OK：不阻塞主线程、不出现长时间卡顿
- [x] 消息气泡不显示 Live2D 控制戳：`[[live2d:...]]` / `[live2d:...]`（只触发 Live2D，不进入可见文本）
- [x] 工具筛选不造成“工具缺失导致能力下降”（必要时自动降级为不过滤）
- [x] 工具/上下文裁剪不导致“记忆/角色设定丢失或幻觉明显增加”

## 8) 验证记录

- 2026-01-02 Owner：Gate#5 已验收通过（GUI 冒烟 + Golden 验证）。
