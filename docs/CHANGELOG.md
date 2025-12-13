# MintChat 更新日志

本文档记录MintChat项目的最近更新和变更。

> 完整历史版本日志已归档，仅保留最近5个版本的详细信息。

---
## [2.60.6] - 2025-11-21

### 🧠 Agent 主系统再升级 + 记忆/日志全面加固

- **日志系统回归兼容写法**  
  - 新增 `_LegacyLoggerAdapter`，在 loguru 场景下也能兼容 `%s` / `%.0f` 占位符和 `exc_info` 语义，TTS、记忆等模块的告警不再出现原始格式串。  
- **记忆检索实时自愈**  
  - `ConcurrentMemoryRetriever` 恢复 per-source 熔断与 EMA 动态超时策略，`asyncio.wait_for` + 轻量看门狗确保任何单源卡顿都会快速跳过，并同步记录每类记忆的最新延迟。  
- **Agent 主流程 Context7 化**  
  - 引入 `AgentConversationBundle` 统一 chat/chat_stream/chat_stream_async 的上下文构建，图片描述/来源、角色状态与压缩策略一次成型，`_invoke_with_failover()` 在初次超时时自动尝试压缩上下文。  
  - 重新挂载 Context7 推荐的工具中间件链（LLMToolSelector、ContextEditing、ToolLimit、PermissionScoped），默认即可裁剪工具集、限制连环调用并按 profile 控制权限。  
  - `_stream_llm_response()` / `_astream_llm_response()` 共享 `LLMStreamWatchdog`，异步/同步流式都能记录首包/总耗时，出现异常时回退到温柔提示而不会悬停。  

---
## [2.60.5] - 2025-11-21

### 🤖 Agent 看门狗与记忆检索修复

- **LLM 看门狗回归**  
  - `_invoke_agent_with_timeout()` 重新接管同步推理，保留首包 / 总耗时统计，超时立即降级为温柔提示。  
  - 新增 `LLMTimeouts` 与 `LLMStreamWatchdog`，统一管理首包、空闲与总时长阈值。
- **流式/异步流式全面防护**  
  - `_stream_llm_response()` 基于后台线程 + `Queue` 拉取流式结果，主线程按 LangChain 指南进行增量输出，并在超时后及时中断。  
  - `chat_stream_async()` 使用 `asyncio.wait_for` 与同一看门狗策略，首包/总耗时都会记录到日志。
- **上下文构建与压缩优化**  
  - `_prepare_messages_async()` 重新启用历史摘要窗口（默认保留最近 6 条），遵循 Context7 记忆压缩最佳实践。  
  - 历史摘要、状态上下文与并发记忆检索结果一次性拼接，减少重复字符串构造。
- **记忆检索稳定性**  
  - `ConcurrentMemoryRetriever` 恢复 per-source 超时与 `asyncio.wait_for` 限制，任何单源卡顿都会快速回退。  
  - 修复 loguru 不支持 `isEnabledFor` 的问题，日志自动按级别过滤并补充 `last_latency_ms` 指标。
- **统一收尾动作**  
  - `_post_reply_actions()` 再次封装保存/巩固/TTS 预取/情感衰减逻辑，chat/stream/async 全通路一致，避免遗漏。

### 📝 文档与版本

- 更新 `docs/CHANGELOG.md`，记录本轮 Agent 核心深度优化内容。  
- `src/version.py` 同步至 `2.60.5`，仅保留最近 5 个版本历史，保持版本记录简洁。

---
## [2.60.4] - 2025-11-21

### ⚡ Agent系统全方面深度优化 + TTS性能提升

- **TTS性能优化**  
  - `GPTSoVITSClient.synthesize()` 减少日志噪音：仅在严重超时（超过阈值2倍）时记录警告，成功日志改为debug级别。  
  - 优化请求日志：仅在重试时记录debug日志，减少正常请求的日志输出。  
- **TTS预取机制优化**  
  - `_prefetch_tts_segments()` 改进预取策略：仅预取前3个句子以减少资源消耗，提升预取效率。  
  - 优化错误处理：静默处理正常关闭和事件循环异常，减少日志噪音。  
- **记忆检索系统优化**  
  - `ConcurrentMemoryRetriever` 使用MD5哈希优化缓存键生成，减少内存占用。  
  - 仅在debug模式下记录详细日志，减少日志输出。  
- **代码质量提升**  
  - 清理冗余版本号注释，移除过时的版本标记。  
  - 优化上下文构建逻辑，使用海象运算符简化代码。  
  - 提升代码可读性和执行效率。

---
## [2.60.3] - 2025-11-21

### 🐛 TTS 错误处理增强 + Agent 系统深度优化

- **修复 TTS 错误日志问题**  
  - `GPTSoVITSClient.synthesize()` 改进异常信息记录，确保错误类型和详情正确输出，解决空错误日志问题。  
  - 区分正常关闭和异常错误，正常关闭仅记录 debug 日志，异常错误记录完整信息（包括错误类型）。  
- **Agent 核心系统性能优化**  
  - `_extract_core_memories()` 使用类级 `frozenset` 缓存关键词集合，避免每次调用创建列表，使用 `any()` 和生成器表达式提升匹配性能。  
  - `_build_retrieval_plan()` 使用字典推导式优化返回值构建，减少循环开销。  
  - `_build_memory_context()` 优化字符串拼接，使用列表一次性构建所有部分，减少中间字符串对象。  
- **代码质量提升**  
  - 移除冗余代码，优化字符串操作和上下文构建逻辑。  
  - 提升代码可读性和执行效率。

---

## [2.60.2] - 2025-11-21

### 🐛 TTS 客户端生命周期修复 + Agent 系统优化

- **修复 TTS 客户端关闭错误**  
  - `GPTSoVITSClient.synthesize()` 在每次请求前检查客户端关闭状态，如已关闭则自动重建连接，彻底解决 "Cannot send a request, as the client has been closed" 报错。  
  - 异常处理增强：捕获客户端关闭和事件循环关闭异常，自动重建客户端并重试，避免因窗口关闭或线程清理导致的 TTS 失败。  
- **TTS 预取任务错误处理优化**  
  - `_prefetch_tts_segments()` 改进异常处理逻辑，优雅处理客户端关闭、事件循环异常等情况，仅记录 debug 日志，不影响主流程。  
  - 区分正常关闭（窗口关闭）和异常错误，避免不必要的错误日志刷屏。  
- **Agent 系统性能优化**  
  - 精简代码逻辑，移除冗余检查，提升响应速度。  
  - 优化错误处理流程，提升系统稳定性。

---
