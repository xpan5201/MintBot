# 决策记录：Phase 6（去 langchain-chroma/embeddings → 检索层加固）

日期：2026-01-02

## 背景 / 目标

- Gate#5 已完成：native(OpenAI-compatible) + 自研 tool-loop + pipeline 已可用，并通过门禁与 GUI 冒烟。
- Phase 6 的目标是把“长期记忆/检索层”从 LangChain 生态中彻底解耦，保证在 **AI 伴侣/角色扮演型智能体**方向下：
  - 稳定优先：检索失败不影响对话主链路（fail-open），不会造成“空回复/崩溃/卡死”。
  - 低延迟优先：向量写入/embedding 不应阻塞 GUI 流式输出体验（后台线程 + 保守超时）。
  - 本地优先：默认持久化在本地磁盘（用户重启后仍可记住）。

## 范围 / 非目标

- 范围：`src/utils/chroma_helper.py`（ChromaDB 持久化 + Embeddings 接入）及其单元测试与 Phase6 文档资产。
- 非目标：
  - 不引入“知识库问答/RAG”路线作为默认记忆实现（本项目记忆以“关系/偏好/事件/对话片段”为主）。
  - 不引入新的远端向量数据库部署（保持桌面端本地可运行）。
  - 不在本阶段做 Phase 7 的“删依赖 + uv lock”。

## 现状盘点

- Phase 2 已完成“移除 langchain-chroma/OpenAIEmbeddings wrapper”：`src/utils/chroma_helper.py` 直连 `chromadb` + OpenAI-compatible `/embeddings`。
- 仍需加固点（Gate#6 关注）：
  - 多线程/并发访问下的稳定性（Windows + SQLite 文件锁风险）。
  - embedding 请求的重复成本与抖动（同一句文本被反复 embed 会增加延迟/失败概率）。
  - 检索链路异常时的降级策略（不能影响对话主流程）。

## MCP Research Loop（Phase 6）

完成日期：2026-01-02

1. Context7
   - Chroma（`/chroma-core/chroma`）：
     - `chromadb.PersistentClient(path=...)` + `get_or_create_collection(...)` 的标准用法；
     - `PersistentClient` 的官方定位更偏“测试/开发”（本项目桌面本地持久化场景可接受）。
   - OpenAI Python SDK（`/openai/openai-python`）：
     - embeddings 统一接口：`client.embeddings.create(model=..., input=[...])`；
     - 响应包含 `data[].index`，可用于按输入顺序还原。
2. tavily_local（优先官方/权威来源）
   - Chroma v0.4 博文：明确说明 Chroma 针对多线程访问增加了粗粒度锁，提升线程安全（适合桌面端多线程调用的心理预期）。
3. Fetch
   - SQLite threadsafe 文档：在 multi-thread 模式下，**同一个连接对象不能跨线程同时使用**；默认 serialized 模式可序列化对象级访问。
   - 结合本项目“多线程 + 本地 SQLite/持久化文件”的风险，采用“调用侧串行锁 + 批量写入节流”的保守策略。

参考来源（本轮实际使用）：  
- https://context7.com/chroma-core/chroma  
- https://context7.com/openai/openai-python  
- https://www.trychroma.com/blog/chroma_0.4.0  
- https://sqlite.org/threadsafe.html  

## 关键设计决策（以稳定/体验为基底，非照抄）

1. 向量库直连与边界
   - 继续维持 `chromadb.PersistentClient(path=...)` 本地持久化，不使用 `langchain-chroma` wrapper。
   - 通过 `ChromaVectorStore` 封装最小必要能力：`add_texts()` / `similarity_search_with_score()` / `get()` / `delete_collection()`。
2. 线程安全：粗锁优先（防御式）
   - `ChromaVectorStore` 内部新增 `RLock`，对 `collection.add/query/get/delete` 做串行化保护，避免上层调用方忘记加锁导致偶发数据损坏/锁冲突。
   - embedding 计算不纳入该锁（避免在锁内等待网络请求，放大阻塞）。
3. EmbeddingClient（OpenAI-compatible）加固
   - `OpenAIEmbeddingClient` 统一走 `OpenAI().embeddings.create(model=..., input=[...])`。
   - 去重批量请求：同一次 `embed_documents()` 内对重复文本去重，减少 API 调用与 token 消耗。
   - 结果顺序还原：按 `data[].index` 排序后回填到原输入顺序。
4. 降级策略（fail-open）
   - `similarity_search_with_score()`：embedding/query 任一环节失败 → 返回空结果 `[]`（并仅打 debug 日志），避免影响对话主链路与 GUI 流式输出。
5. 低延迟与阻塞控制
   - 为 embeddings 请求设置保守 `timeout/max_retries` 默认值，避免后台线程长时间挂起造成堆积：
     - 默认：`timeout=10s`、`max_retries=1`
     - 允许通过 `settings.llm.extra_config` 覆盖（不新增配置键）：`embedding_timeout_s` / `embedding_max_retries`。
6. 重复 embedding 成本：内存 LRU 缓存
   - `OpenAIEmbeddingClient` 内部提供可选 LRU 缓存（默认开启，最多 1024 条），避免同一句短文本被重复 embed（对“角色口癖/常见句式/工具输出摘要”等非常常见）。
   - 缓存为内存级，不落盘（避免隐私/敏感文本落盘 + 版本兼容负担）。

## 风险 / 回滚点

- 风险：缓存占用内存、或在“模型更换/提供商更换”时产生误用预期。
  - 缓解：client 的复用缓存 key 已包含 `model/base_url/api_key/enable_cache`；LRU 限制为 1024 条。
- 风险：Windows 下同一路径多进程/多 client 同时打开导致 SQLite 文件锁冲突。
  - 缓解：设计上保持“单进程单 client”，并通过调用侧/封装侧串行锁减少并发写入。
- 回滚点：
  - 运行时：调用 `create_chroma_vectorstore(..., enable_cache=False)` 关闭 embedding 缓存（保守退回）。
  - 代码级：回滚 `src/utils/chroma_helper.py` 的 Phase6 加固改动（不会影响 Phase 5 的 native/pipeline 主链路）。

## 补充：流式首包超时误判（空 chunk）

### 现象

- 部分 OpenAI-compatible / OpenAI 官方的 Chat Completions streaming 会先返回“空内容 chunk”（例如只有 `delta.role` 或 `delta={}`，`delta.content` 为空字符串/缺失），随后才开始输出真正的文本增量。
- 如果上层把“首包”定义为“首个可见文本 delta”，就会在网络已建立但尚未输出文本时误判为“首包超时”，触发兜底重试，导致整体更慢（例如 18s 超时 + 兜底再等 20~60s）。

### MCP Research（本轮新增）

- OpenAI API Reference（Chat Completions streaming）：示例 chunk 明确包含 `delta.role` 且 `content` 可能为空字符串；末尾 chunk 可能 `delta={}`。  
  - https://platform.openai.com/docs/api-reference/chat-streaming
- OpenAI Python SDK（Streaming Helpers）：`ChunkEvent` 会“为每个 chunk”触发（即使该 chunk 不包含新内容）。  
  - https://raw.githubusercontent.com/openai/openai-python/main/helpers.md

### 决策与落地（不改变可见输出契约）

- 决策：把“首包/心跳”定义为“收到任意 chunk”，而不是“收到首个非空文本”。  
  上层 watchdog 只用它判断连接是否活跃；可见文本仍以非空 `TextDeltaEvent.delta` 为准。
- 实现：`src/llm_native/openai_backend.py` 在解析到某个 chunk 内没有产生任何 `TextDeltaEvent`/`ToolCallDeltaEvent` 时，补发 `TextDeltaEvent(delta=\"\")` 作为心跳（上层会将其视为 heartbeat，不进入 UI）。  
  - 回归测试：`tests/test_llm_native_openai_backend.py::test_openai_backend_stream_emits_heartbeat_for_role_only_chunks`

## Owner 验收建议（Gate#6）

- 重启后仍保留长期记忆：Chroma `PersistentClient(path=...)` 会自动持久化并在启动时自动加载（只要 path 不变）。  
  参考：Chroma Persistent Client 文档（官方仓库）。  
  - https://raw.githubusercontent.com/chroma-core/chroma/main/docs/docs.trychroma.com/markdoc/content/docs/run-chroma/persistent-client.md
- 断网/网络不稳定冒烟：embedding 请求应设置“保守 timeout + 小重试”，避免后台任务长时间挂起堆积；OpenAI Python SDK 支持 `timeout=float` 或 `httpx.Timeout(...)` 细粒度配置。  
  参考：OpenAI Python SDK README（timeouts/retries）。  
  - https://github.com/openai/openai-python/blob/main/README.md
