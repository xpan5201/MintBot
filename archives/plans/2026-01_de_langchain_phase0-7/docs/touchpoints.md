# LangChain/LangGraph 触点清单（Phase 0）

> 用途：Phase 0 盘点；Phase 1+ 迁移顺序；Phase 7 “零引用验收”的基准清单。  
> 生成方式：Serena/rg 扫描 + 人工复核（避免漏网之鱼）。

自动化辅助：

- `archives/plans/2026-01_de_langchain_phase0-7/scripts/de_langchain_audit_touchpoints.py`：可输出 JSON 报告（便于后续 Gate/CI 验收）

## 1) 依赖范围（来自 `pyproject.toml`）

需要最终移除的依赖（Phase 7 才做“删依赖 + uv lock”）：

- `langchain`
- `langchain-core`
- `langchain-community`
- `langgraph`
- `langchain-openai`
- `langchain-anthropic`
- `langchain-google-genai`
- `langchain-chroma`
- `langsmith`

需要保留/替换策略明确的依赖（不属于“去 LangChain”本身）：

- `openai`（Phase 3 的 native 后端基础）
- `chromadb`（Phase 6 直接对接）
- `httpx`（网络与连接池基础）

## 2) 代码触点（当前扫描命中）

### Agent 核心

- `src/agent/core.py`
  - ✅ Phase 2：移除直接 `langchain*/langgraph*` import，统一改为 `src/llm_native/*`
  - 通过 `src/llm_native/langchain_agent.py` 封装 `create_agent` + middleware
  - 通过 `src/llm_native/langchain_providers.py` 封装 provider ChatModel（OpenAI/Anthropic/Google）
  - 通过 `src/llm_native/langchain_messages.py` 统一 LangChain message types 入口

### 工具系统

- `src/agent/tools.py` / `src/agent/builtin_tools.py`
  - ✅ Phase 2：移除直接 `langchain*.tools` import，统一改为 `src/llm_native/langchain_tools.py`
  - ✅ Phase 2：新增 `ToolRegistry.get_tool_specs()`（导出 OpenAI-compatible `ToolSpec`，供 Phase 3+ native 后端使用）
- `src/agent/mcp_manager.py`
  - ✅ Phase 2：移除直接 `langchain_core.tools.StructuredTool` import，统一改为 `src/llm_native/langchain_tools.py`
- `src/agent/tool_selector_middleware.py`
  - ✅ Phase 2：移除直接 import，统一改为 `src/llm_native/langchain_tool_selector.py`
- `src/agent/tool_trace_middleware.py`
  - ✅ Phase 2：移除直接 import，统一改为 `src/llm_native/langchain_agent.py` / `src/llm_native/langchain_messages.py` / `src/llm_native/langgraph_types.py`

### LLM 工厂

- `src/llm/factory.py`
  - ✅ Phase 2：移除直接 `langchain_openai` import，统一改为 `src/llm_native/langchain_providers.py`

### 多模态

- `src/multimodal/vision.py`
  - ✅ Phase 2：已改为自研 `Message`（通过 `src/llm_native/langchain_messages.py` 适配到 LangChain）

### 检索/向量库

- `src/utils/chroma_helper.py`
  - ✅ Phase 2：已改为直连 `chromadb`（移除 langchain-chroma wrapper）
  - ✅ Phase 2：已改为使用 `openai` SDK 调用 OpenAI-compatible embeddings 接口（移除 langchain-openai embeddings wrapper）

### 其他（噪声/依赖检测）

- `src/utils/dependency_checker.py`：langchain 依赖映射
- `src/utils/logger.py`：quiet libs 列表包含 `langchain`

## 3) 迁移顺序建议（叶子 → 主干）

1. 检索/embeddings（`src/utils/chroma_helper.py`）→ 直接对接 `chromadb` + 自研 EmbeddingClient
2. 工具协议层（`src/agent/*tools*`）→ ToolSpec/ToolRegistry（自研）
3. LLM 工厂（`src/llm/factory.py`）→ OpenAICompatibleBackend
4. middleware（`src/agent/tool_*middleware.py`）→ Pipeline stages
5. Agent 核心编排（`src/agent/core.py`）→ AgentRunner + ToolLoop（最后替换）
