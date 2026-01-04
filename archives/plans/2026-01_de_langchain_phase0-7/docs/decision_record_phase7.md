# 决策记录：Phase 7（彻底移除 LangChain/LangGraph 依赖 + 零残留）

日期：2026-01-02

## 背景 / 目标

- Gate#6 已验收：检索层（Chroma/embeddings）已去 LangChain wrapper 并加固稳定性。
- Phase 7 目标：彻底移除 `langchain*` / `langgraph*` / `langsmith*` 依赖与代码残留，使项目后端 **只保留 native(OpenAI-compatible) 实现**，并保持桌面端稳定可运行（AI 伴侣/角色扮演方向：低延迟流式、工具可控、记忆可靠、GUI 不阻塞）。

## 范围 / 非目标

- 范围：
  - 代码：`src/` / `tests/` / `examples/` / `scripts/` 中对 `langchain*` / `langgraph*` / `langsmith*` 的引用清零
  - 依赖：从 `pyproject.toml` 与 `uv.lock` 移除相关依赖，并确保 `uv sync --locked` 可复现
- 非目标：
  - 不新增功能（仅做“删除 + 自研路径收敛”）
  - 不引入新的外部编排框架替代（坚持自研 Pipeline/Tool-loop）

## MCP Research Loop（Phase 7）

完成日期：2026-01-02

1. Context7（uv 官方文档）
   - 依赖移除推荐使用 `uv remove ...`，可同时更新 `pyproject.toml` + `uv.lock` + 环境，减少“手改后不同步”的风险。
2. tavily_local（补充权威入口）
   - 验证 uv 的“项目工作流/lockfile 行为”与常见踩坑（lock 不同步、CI 用 --locked/--frozen 等）。
3. Fetch（抓取细节）
   - 读取 uv 的 “Working on projects” 文档，确认 `uv.lock` 由 uv 管理、应提交、且不应手改；依赖变更推荐走 `uv add/uv remove`。

参考来源（本轮实际使用）：
- https://context7.com/astral-sh/uv
- https://raw.githubusercontent.com/astral-sh/uv/main/docs/guides/projects.md
- https://docs.astral.sh/uv/guides/projects/

## MCP Research Loop（Phase 7 - Round 2：OpenAI Tool Calling Schema）

完成日期：2026-01-02

背景：Phase 7 将彻底移除 LangChain，因此工具系统必须直接对齐 OpenAI-compatible `tools` schema（低延迟流式 + 可控工具调用）。

1. Context7（OpenAI Python SDK）
   - 确认 `chat.completions.create(..., tools=[...], tool_choice=...)` 的参数形状与工具调用/流式事件能力。
   - 了解 `pydantic_function_tool()` + `chat.completions.parse()` 需要 `strict: true` 的约束（仅作为参考，不强制引入）。
2. tavily_local（权威指南）
   - OpenAI 官方 function calling 指南指出：启用 `strict` 时，`parameters` 中每个 object 需要 `additionalProperties: false`，且 `properties` 字段需要全部出现在 `required`；可选字段通过 `type` 增加 `null` 表示。
3. Fetch（抓取细节）
   - `https://platform.openai.com/docs/guides/function-calling` Fetch 403，已按规范改用 tavily-extract 获取正文。

参考来源（本轮实际使用）：
- https://context7.com/openai/openai-python
- https://platform.openai.com/docs/guides/function-calling

## MCP Research Loop（Phase 7 - Round 3：OpenAI SDK 超时/重试/Streaming Helpers）

完成日期：2026-01-03

背景：Phase 7 已彻底移除 LangChain/LangGraph，因此 native(OpenAI-compatible) backend 需要在稳定性与低延迟流式体验上进一步对齐官方 SDK 的最佳实践（尤其是超时/重试/连接池与流式事件处理），同时保持对“多提供商兼容”的优先级。

1. Context7（OpenAI Python SDK）
   - 确认 SDK 支持在 client 级别设置 `timeout` / `max_retries`，并支持使用 `httpx.Timeout(...)` 进行 connect/read/write/pool 的细粒度控制。
   - 确认支持通过 `http_client=DefaultHttpxClient(...)` 传入自定义 httpx client（例如代理、transport 等），以及使用 `client.with_options(...)` 做 per-request 覆盖。
2. tavily_local（权威入口定位）
   - 定位到 openai-python 仓库的 README 与 helpers 文档，作为 SDK 行为的权威参考（streaming、资源回收、以及推荐 API 方向）。
3. Fetch（抓取细节）
   - 从 README 确认：SDK 的“主要推荐”是 Responses API，但 Chat Completions API “supported indefinitely”；并提供 SSE streaming 示例。
   - 从 helpers 文档确认：`.chat.completions.stream()` 是对 `.create(stream=True)` 的更高层封装，提供更细粒度 event（含 tool_calls arguments delta/done），并要求 context manager 以避免响应泄漏。

本轮取舍（对齐项目方向：低延迟流式 + 多提供商兼容）：
- 继续以 Chat Completions 作为默认协议层（多数 OpenAI-compatible 提供商的最小公约数），并保留未来逐步对齐 Responses API 的空间。
- 维持现有的“自研流式解析/聚合”，但参考 `.stream()` 的事件语义（尤其是 tool call arguments delta/done）来校验我们的聚合逻辑与资源释放策略。
- 超时/重试/连接池策略继续走“保守默认 + 开发配置可调”，避免网络抖动导致 GUI 流式体验退化。

参考来源（本轮实际使用）：
- https://context7.com/openai/openai-python
- https://raw.githubusercontent.com/openai/openai-python/main/README.md
- https://raw.githubusercontent.com/openai/openai-python/main/helpers.md

## MCP Research Loop（Phase 7 - Round 4：Vision 输入格式（Chat Completions）与“必须是 VLM 模型”）

完成日期：2026-01-03

背景：用户反馈“图片/视觉功能不可用”。Phase 7 已统一走 OpenAI-compatible 后端，需确认：
1) 图片输入的 message schema 是否符合 Chat Completions 的 OpenAI-compatible 形状；
2) 失败是否来自“模型本身不支持 vision（非 VLM）”的配置问题。

1. Context7（OpenAI API 文档镜像）
   - 确认 Chat Completions Vision 的 `messages[].content` 支持 `[{type:'text'},{type:'image_url',image_url:{url,detail}}]`，并允许使用 `data:image/jpeg;base64,...` 的 data URL。
2. tavily_local（权威入口定位）
   - 定位到 OpenAI 官方 “Images and vision” 指南与 Chat Completions API reference（用于核对“Chat Completions 也支持图像输入”以及模型/模态说明入口）。
3. Fetch / tavily-extract（抓取细节）
   - OpenAI 官方站点对 Fetch 返回 403，按规范改用 tavily-extract 提取关键段落（仅用于 schema/能力确认，不照抄实现）。

本轮结论（对齐项目方向：多模态输入可用、GUI 不阻塞、失败可解释）：
- 项目当前 `image_url` block 的 JSON 形状与 OpenAI Chat Completions Vision 示例一致；“无法使用”更可能来自模型选择（非 VLM）或 Key 为空导致的 401/400。
- 为降低误配置成本：VISION_LLM 的空字符串配置视为“未配置”，自动回退到主 LLM 的 key/api/model；并在运行时捕获“not a VLM”类错误，给出可操作的配置提示。

参考来源（本轮实际使用）：
- https://github.com/context7/platform_openai/blob/main/guides/vision.md
- https://platform.openai.com/docs/guides/images-vision
- https://platform.openai.com/docs/api-reference/chat/create

## MCP Research Loop（Phase 7 - Round 5：Streaming Event API 校验与工具语义一致性）

完成日期：2026-01-03

背景：Phase 7 善后阶段需要“零残留”清理代码文案，同时保持流式输出与工具事件的语义稳定（AI 伴侣/角色扮演：低延迟连续输出、工具调用可控、失败可解释）。

1. Context7（OpenAI Python SDK）
   - 复核 `.chat.completions.stream()` 的 event 语义（`content.delta`、`tool_calls.function.arguments.delta/done`），用于校验自研 tool-call delta 聚合与资源释放策略。
2. tavily_local（权威入口定位）
   - 定位 openai-python 官方 helpers 文档与 Chat Completions API reference（用于核对 stream/event 相关入口）。
3. Fetch（抓取细节）
   - 抓取 openai-python `helpers.md` 原文，提炼 “stream 需要 context manager、防止响应泄漏；tool call arguments delta/done 事件” 等要点。

参考来源（本轮实际使用）：
- https://context7.com/openai/openai-python
- https://raw.githubusercontent.com/openai/openai-python/main/helpers.md
- https://platform.openai.com/docs/api-reference/chat

## MCP Research Loop（Phase 7 - Round 6：pytest import-mode 与清理安全性）

完成日期：2026-01-03

背景：Phase 7 收尾阶段需要逐步删除未使用模块/过期注释，并通过门禁保证项目稳定。为避免测试导入行为
“意外通过/意外失败”，需要明确 pytest 的 import-mode 与 sys.path 行为。

1. Context7（pytest）
   - 复核 `--import-mode=prepend/append/importlib` 的差异，以及 `importlib` 模式不修改 `sys.path` 的优点与限制。
2. tavily_local（权威入口定位）
   - 定位 pytest 官方文档页 “pytest import mechanisms and sys.path/PYTHONPATH” 作为 import-mode 的权威解释。
3. Fetch（抓取细节）
   - 抓取 stable 文档页，确认 `importlib` 模式的优缺点（不改 sys.path、测试模块名可重复；但 tests 间
     互相 import/测试工具模块导入受限）。

本轮结论（对齐项目方向：稳定优先、可回滚）：
- 本仓库采用 `src/` 包布局，测试显式 `import src.*`；删除模块后以 `pytest -q` 作为最终判据即可。
- 若后续在“删模块/改包结构”过程中出现导入歧义，可考虑在 CI/本地设置 `--import-mode=importlib` 以减少
  `sys.path` 侧效应，但需同步调整 tests 内互相 import 的方式（倾向通过 `conftest.py`/应用代码承载测试工具）。

参考来源（本轮实际使用）：
- https://context7.com/pytest-dev/pytest
- https://docs.pytest.org/en/stable/explanation/pythonpath.html

## MCP Research Loop（Phase 7 - Round 7：uv scripts 与仓库脚本安全边界）

完成日期：2026-01-03

背景：Phase 7 善后阶段需要清理 `scripts/` 中的冗余入口与“一次性修复脚本”。为避免误操作破坏
`uv.lock`/环境可复现性或造成大范围文件改写，需要对齐 uv 的官方脚本运行与环境管理建议。

1. Context7（uv）
   - 复核 `uv run`/`uv run --no-project`/`uv run --with` 的推荐用法，以及“不要手动改项目环境（如 `uv pip install`）”
     的指导（项目依赖用 `uv add` 管理，一次性依赖用 `uv run --with` 或 `uvx`）。
2. tavily_local（权威入口定位）
   - 定位到 uv 官方文档 “Running scripts” 页作为脚本运行的权威参考。
3. Fetch（抓取细节）
   - 抓取 “Running scripts | uv” 页面，确认：`uv run` 用于运行脚本，依赖应声明化（project 或 inline metadata），并说明
     `--no-project` 的语义（在项目中运行脚本时可跳过安装当前项目）。

本轮结论（对齐项目方向：稳定优先、可回滚）：
- `scripts/` 仅保留“可复现/非破坏性”的入口与工具；涉及“自动改代码/改依赖/批量移动文档”的一次性脚本删除，
  以免误触造成行为漂移或环境不可复现。
- 需要跑维护脚本时，优先使用 `uv run`（必要时 `--no-project` / `--with`），而不是脚本内调用 `pip install/upgrade`。

参考来源（本轮实际使用）：
- https://context7.com/astral-sh/uv
- https://docs.astral.sh/uv/guides/scripts/

## MCP Research Loop（Phase 7 - Round 8：文档清理与 CHANGELOG 维护规范）

完成日期：2026-01-03

背景：Phase 7 善后阶段开始对 `docs/` 做“重复/过期说明”的大扫除，目标是降低误导信息与维护成本，同时保留
可追溯性（decision records/gate checklists 不删）。

1. Context7（Keep a Changelog）
   - 复核 changelog 的核心原则：应为“面向人”的变更摘要；避免把 git log 直接倾倒进 changelog；并减少噪音（例如移除
     空章节、避免过期的手动版本标记导致误导）。
2. tavily_local（权威入口定位）
   - 定位 Keep a Changelog 官方站点与相关最佳实践入口，用于校验 changelog 结构与维护建议。
3. Fetch（抓取细节）
   - 抓取 Keep a Changelog v1.1.0 的规范文本，确认示例结构（含 `[Unreleased]`）与“不要把 git logs 倒进 changelog”的建议。

本轮结论（对齐项目方向：稳定优先、可回滚）：
- `docs/README.md` 不应维护“手动版本号/更新日期”，避免长期漂移；改为稳定的索引 + 最短启动路径即可。
- `docs/CHANGELOG.md` 明确标注为 legacy 摘录：内容可能包含已在 Phase 7 移除/替换的组件；当前迁移与验收以
  `archives/plans/2026-01_de_langchain_phase0-7/docs/` 为准，避免误导用户/贡献者。

参考来源（本轮实际使用）：
- https://context7.com/olivierlacan/keep-a-changelog
- https://keepachangelog.com/en/1.1.0/
## 关键设计决策（以稳定/可回滚为基底）

1. “零引用”验收范围
   - Gate#7 的“零引用扫描”限定为代码层（`src/tests/examples/scripts`），不强制抹掉文档中的历史描述（否则会破坏迁移记录与可追溯性）。
   - 使用 `archives/plans/2026-01_de_langchain_phase0-7/scripts/de_langchain_audit_touchpoints.py --fail-if-found` 作为最终验收工具，避免人工漏扫。
2. 依赖移除策略（最小风险）
   - 优先使用 `uv remove` 移除 `langchain*` / `langgraph*` / `langsmith*` 及相关 provider 包，确保 `pyproject.toml` 与 `uv.lock` 同步更新。
   - 依赖移除分批进行：先清代码引用 → 再删依赖并重锁 → 再跑门禁；避免“先删依赖导致全仓 ImportError”。
3. 回滚策略
   - 每步保持可回滚：使用 `git diff` 审核变更，Gate#7 未通过前不做不可逆清理（例如删除数据目录）。

## 本轮落地（与 Research Loop 对齐）

- MCP 工具适配：移除 LangChain `StructuredTool` 依赖，改为输出带 `name/description/__tool_parameters__` 的 plain callable，供 ToolRegistry 导出 OpenAI ToolSpec。
- Schema 策略：默认保持 `additionalProperties: false`（更安全、更接近 strict 要求），但运行时不默认启用 `strict`（避免不同提供商对 strict/nullable 的兼容差异）；后续若启用 strict，需要按官方约束补齐 required/nullable 语义。

## 风险 / 回滚点

- 风险：仍有代码路径在启动/测试时 import 到 langchain 兼容模块导致 ImportError。
  - 缓解：先做“代码引用清零”与审计脚本；再移除依赖。
- 风险：配置项遗留导致用户误以为仍可切换 langchain 后端。
  - 缓解：收敛配置面（移除 `Agent.llm_backend` 或保持兼容但无副作用），并更新示例与文档。
- 回滚点：
  - 任何阶段都可以通过 `git checkout -- <files>` 回退到上一稳定状态；
  - Gate#7 通过前不删除用户数据目录（`data/`）。

## 执行记录（2026-01-03）

本轮目标：完成 Gate#7 的“零引用 + 删依赖 + 门禁全绿”。

1) MCP Research Loop（uv remove / lock check）
- Context7：确认 `uv remove ...` 会同步更新 `pyproject.toml` + `uv.lock` + 环境；以及 `uv lock --check` 用于校验 lockfile 与项目元数据一致。
- tavily_local：辅助定位 uv 的官方项目工作流文档入口。
- Fetch：抓取 `Working on projects | uv`，确认依赖管理推荐使用 `uv add/uv remove`，且 `uv.lock` 由 uv 管理不应手改。

2) 落地动作（可回滚、稳定优先）
- 代码层：`src/tests/examples/scripts` 对旧依赖触点扫描为 0（`archives/plans/2026-01_de_langchain_phase0-7/scripts/de_langchain_audit_touchpoints.py --fail-if-found` + `rg`）。
- 依赖层：执行 `uv remove ...` 移除旧依赖，并通过 `uv lock --check`。
- 门禁：`pytest` / `black` / `flake8` / `mypy` 全绿（Owner GUI 冒烟待确认）。

3) Phase 7 善后：src/ “大扫除”（文案零残留 + 最小风险重构）
- `src/` 内 `langchain/langgraph/langsmith` 文案残留清零（仅文本与注释清理，不改对外契约）。
- 保留 legacy 同步流式入口 `MintChatAgent._stream_llm_response()`，但将实现收敛为“后台线程 + 看门狗 + scrubbing”最小版本（避免阻塞/污染 UI，且通过多模式跳过用例）。
- 门禁复跑：`pytest` / `black` / `flake8` / `mypy` 全绿。

4) Phase 7 善后：继续 src/ 大扫除（过期注释/未使用模块）
- 删除确认无引用的模块（rg + Serena 验证）：`src/utils/async_config_loader.py`、`src/utils/async_vector_search.py`。
- 清理过期文案：`src/llm_native/agent_runner.py` 去除“gate”相关描述；`black` 格式化 `src/config/settings.py`。
- 门禁：`pytest` / `black` / `flake8` / `mypy` 全绿（Windows 11，Python 3.13.9）。

5) Phase 7 善后：scripts/ “大扫除”（冗余脚本/入口）
- 删除破坏性“一次性修复脚本”（不再鼓励脚本内 `pip install/upgrade` 或批量改写仓库内容）：
  - `scripts/fix_pkg_resources_warning.py`
  - `scripts/fix_code_style.py`
  - `scripts/optimize_gui_code.py`
  - `scripts/organize_docs.py`
  - `scripts/remove_version_comments.py`
  - `scripts/replace_emoji_icons.py`
  - `scripts/fix_encoding.py`
  - `scripts/fix_emoji_upload.py`
- 文档：`scripts/README.md` 补充去 LangChain 相关脚本说明与“稳定优先”原则。
- 门禁：`pytest` / `black` / `flake8` / `mypy` 全绿（Windows 11，Python 3.13.9）。

6) Phase 7 善后：docs/ “大扫除”（重复/过期说明）
- `docs/README.md`：移除会长期过期的手动版本/日期，保留索引 + 跨平台最短启动路径。
- `docs/CHANGELOG.md`：标注为 legacy 摘录，避免与 Phase 7 当前状态冲突造成误导。
- `docs/LOGGING.md`：移除尾部残留标记（`***`）。
- `archives/plans/2026-01_de_langchain_phase0-7/docs/README.md`：更正标题为 Phase 0-7 产物清单。
- 门禁：`pytest` / `black` / `flake8` / `mypy` 全绿（Windows 11，Python 3.13.9）。

7) Phase 7 末尾检查：再验收（end-state re-audit）

- MCP Research Loop（OpenAI SDK streaming/timeout + tool-call delta/strict schema 复核）
  - Context7：`openai-python` v1.68.0（超时可用 `httpx.Timeout(...)` 细粒度配置；`max_retries` 可 client 级/每请求覆盖；stream helper 事件类型包含 `content.delta` 与 `tool_calls.function.arguments.delta/done`）。
  - tavily_local：定位到 openai-python 的 README/helpers 与 OpenAI 官方 function calling 指南（Fetch 403 的页面改用 tavily-extract）。
  - Fetch：抓取 openai-python README/helpers（raw）；function calling 指南 Fetch 403 → tavily-extract 获取正文。
  - 取舍（对齐项目方向：低延迟流式 + 多提供商 OpenAI-compatible）：继续以 Chat Completions 作为最小公约数；参考 SDK `.stream()` 的 “必须用 context manager 关闭响应” 语义，校验我们自研 stream 的资源释放与 tool-call arguments delta 聚合逻辑；`strict` 约束保持在 schema 导出层，不默认强启以避免不同提供商兼容差异。
  - 参考来源（本轮实际使用）：
    - https://context7.com/openai/openai-python
    - https://raw.githubusercontent.com/openai/openai-python/main/helpers.md
    - https://raw.githubusercontent.com/openai/openai-python/main/README.md
    - https://platform.openai.com/docs/guides/function-calling

- End-state audits：`archives/plans/2026-01_de_langchain_phase0-7/scripts/de_langchain_audit_touchpoints.py --fail-if-found`=0；rg=0；`uv lock --check` 通过。
- 门禁复跑：`pytest`（313 passed）/ `black --check` / `flake8` / `mypy` 全绿（Windows 11，Python 3.13.9）。
