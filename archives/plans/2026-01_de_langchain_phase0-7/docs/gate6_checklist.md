# Gate#6 Checklist（Phase 6 完成标准）

> Gate#6 的定位：把“检索/向量库/embeddings”从 LangChain 生态中彻底解耦并加固稳定性，确保：
> - 长期记忆写入/检索不阻塞 GUI 流式输出（后台线程 + 保守超时）
> - 多线程/并发访问稳定（锁策略明确）
> - 检索异常 fail-open（不影响对话主链路）

前置条件：

- [x] Gate#5 Owner 验收通过（见 `gate5_checklist.md`）
- [x] Phase 6 MCP Research Loop 完成（Context7 + tavily_local + Fetch）并形成《决策记录》（见 `decision_record_phase6.md`）

## 1) VectorStoreAdapter（必须）

- [x] 直连 `chromadb.PersistentClient(path=...)`（不再使用 `langchain-chroma` wrapper）
- [x] `ChromaVectorStore` 封装最小接口：`add_texts` / `similarity_search_with_score` / `get` / `delete_collection`
- [x] 并发保护：对 collection 的 `add/query/get/delete` 使用内部锁串行化（避免 SQLite/文件锁偶发问题）
- [x] 证明（扫描验收，仅限代码）：`rg -n \"\\blangchain_chroma\\b|\\bOpenAIEmbeddings\\b\" src tests` 为 0 命中

## 2) EmbeddingClient（必须）

- [x] OpenAI-compatible embeddings：使用 `openai` SDK `client.embeddings.create(model=..., input=[...])`
- [x] 批量去重：同一批 `embed_documents()` 内对重复文本去重，减少请求成本
- [x] 顺序还原：按 `data[].index` 排序后回填，保证输入输出顺序一致
- [x] 可选内存缓存：默认启用 LRU（1024 条上限），可通过 `enable_cache=False` 关闭
- [x] 超时/重试：embedding 默认使用保守 `timeout/max_retries`，并允许从 `settings.llm.extra_config` 覆盖（不新增配置键）

## 3) 稳定性/降级（必须）

- [x] 检索 fail-open：embedding/query 异常 → 返回空检索结果（debug 日志），不影响对话主流程
- [x] 避免锁内网络等待：embedding 计算不在 vectorstore 锁内执行
- [x] Owner 冒烟：在网络不稳定/断网情况下，聊天仍可正常进行（只是缺少长期记忆检索增强）

## 4) 测试（必须）

- [x] 单测：embedding client 缓存/去重（`tests/test_chroma_helper_embedding_reuse.py`）
- [x] 单测：`similarity_search_with_score` 异常 fail-open（`tests/test_chroma_helper_embedding_reuse.py`）
- [x] 回归：长期记忆写入/检索相关测试全绿（例如向量库锁/导入导出/裁剪等）

## 5) 质量门禁（必须全绿）

```powershell
.\\.venv\\Scripts\\python.exe -m pytest -q
.\\.venv\\Scripts\\python.exe -m black src\\ tests\\ examples\\
.\\.venv\\Scripts\\python.exe -m flake8 src\\ tests\\ examples\\ --max-line-length=100 --ignore=E203,W503
.\\.venv\\Scripts\\python.exe -m mypy src\\ --ignore-missing-imports
```

## 6) Owner 验收点（必须确认）

- [x] GUI 流式输出连续性 OK：长期记忆写入/embedding 不造成明显卡顿（尤其“首包后突然停顿”）
- [x] 重启后仍保留长期记忆：重启程序后可检索到此前写入的关键偏好/事件（路径/用户隔离正确）
- [x] 多轮对话下不会出现 Chroma “database is locked” 等错误刷屏（必要时应降级并记录一次性 warning）

## 7) 验证记录

- 2026-01-02：已完成代码扫描（`rg -n "\\blangchain_chroma\\b|\\bOpenAIEmbeddings\\b" src tests` 为 0 命中）与质量门禁（pytest/black/flake8/mypy 全绿）。
- 2026-01-02 Owner：Gate#6 已验收通过（离线/重启/长会话冒烟）。
