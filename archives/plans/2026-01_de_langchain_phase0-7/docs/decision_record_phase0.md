# 决策记录（Phase 0）

> 范围：去 LangChain/LangGraph 计划的 Phase 0（盘点&冻结）。  
> 目标：建立“护栏”，确保后续 Phase 1+ 的自研替换可灰度、可回滚、可验证。

## 0) 已确认的项目级决策（来自 owner 确认）

1. **彻底移除依赖范围**：最终不再依赖 `langchain* / langgraph*`（以及相关 provider 包）。
2. **统一走 OpenAI API 兼容接口**：`base_url + api_key + model` 作为唯一接入配置。
3. **双后端稳定期**：周期/阈值 TBD（由 owner 后续确认）。
4. **“功能等价”硬指标**：每个阶段必须先做 MCP 研究、形成取舍记录，再自研落地（不是照抄）。

## 1) Phase 0 不变量（必须保留的体验/语义）

- **流式输出语义**：chunk 合并/节流/首包超时/空回复兜底/取消与清理必须一致。
- **工具调用语义**：选择/执行/回填/错误处理/输出裁剪必须一致。
- **记忆系统语义**：短期/长期/核心记忆的写入与检索路径不回归（含后台 deferral）。
- **多模态边界纪律**：GUI 主线程不阻塞（网络/磁盘/LLM/ASR/TTS 必须在后台）。

## 2) OpenAI-compatible API 统一策略（Phase 0 结论）

### 2.1 Canonical：以 Chat Completions 作为兼容基座

- OpenAI 官方 SDK 已把 `Responses API` 作为主要入口，但 **OpenAI-compatible 生态**（多提供商/自建网关）对 `Responses` 的支持并不一致。
- 因此 Phase 3 的 `native` 后端：**优先实现 `chat.completions`**（兼容面最大），并在架构上保留未来增加 `responses` 的空间。

### 2.2 Streaming：以“delta → StreamEvent”映射为核心

- Chat Completions streaming 会返回 `ChatCompletionChunk`，需要将：
  - `delta.content` → 文本增量
  - `delta.tool_calls[]` → 工具调用增量（**arguments 需要按 index 聚合**）
- 后续 Phase 1 会引入项目自研 `StreamEvent` 协议（TextDelta/ToolCallDelta/ToolResult/Error/Done），并要求：
  - 可取消/可超时
  - 事件级指标（首包延迟/吞吐/失败率）

### 2.3 Tools：严格 JSON schema

- 工具 schema 采用 strict JSON schema（`additionalProperties=false`），减少模型“自造字段”的不确定性。
- Python 侧可优先使用 Pydantic 生成 JSON schema（Phase 1/4 决策再细化）。

## 3) 网络与可靠性（SDK/HTTP 客户端）

- 统一使用 OpenAI Python SDK 作为客户端基础（Phase 3），支持：
  - `base_url`（OpenAI-compatible）
  - `timeout`（可全局/可 per-request 覆盖）
  - `max_retries`（可全局/可 per-request 覆盖）
  - 自定义 `http_client`（httpx 连接池/代理/transport）

## 4) 已落地的 Phase 0 交付（代码层）

- **总开关（占位）**：`Agent.llm_backend = langchain | native`（当前 `native` 回退到 `langchain`，不改行为）
  - `src/config/settings.py` 增加 `AgentConfig.llm_backend`
  - `src/agent/core.py` 读取并做容错回退
  - `config.dev.yaml` 更新开发者配置示例项
- **Golden 基线录制脚本**：`archives/plans/2026-01_de_langchain_phase0-7/scripts/de_langchain_capture_golden.py`

## 5) 下一步（仍在 Phase 0 内）

1. 产出 `provider_matrix.md` 并开始填充：至少先把本项目当前使用的 provider（以及计划接入的）列为事实表。
2. 增加“触点审计脚本”：自动扫描 `langchain/langgraph` 引用并输出报告（为 Phase 7 零引用验收铺路）。
3. 录制 1~3 组 golden：覆盖纯文本流式、工具调用、异常兜底三条主链路（不污染长期记忆）。

## 6) 参考资料（Phase 0 MCP Research 摘要）

> 说明：OpenAI 平台文档页在本环境 Fetch 可能出现 403；本项目以 Context7 与 GitHub 原文为准做提炼。

- OpenAI Python SDK README：`https://raw.githubusercontent.com/openai/openai-python/main/README.md`
- OpenAI Python SDK helpers：`https://raw.githubusercontent.com/openai/openai-python/main/helpers.md`
- Context7：`/openai/openai-python`、`/websites/platform_openai`
