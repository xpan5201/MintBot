# MintChat — AGENTS.md（维护 / 升级 / 代码质量规范）

这份文档是 **MintChat 项目长期维护的“操作规范 + 代码质量检查清单”**。之后对项目的修复/优化/升级，默认以本文件为准执行与验收。

> 目标：可长期维护、可验证、可演进；稳定优先，性能优化必须“非破坏式”（不牺牲正确性与体验）。

---

## 0) 每轮对话必做流程（Mandatory）

每次开始处理用户需求时，必须按以下流程执行（**不能跳步**）：

1. **先分析需求**：明确目标、影响范围、约束条件、验收标准、潜在风险/回滚点；不清楚就先问。
2. **熟读 AGENTS.md**：每次对话开始都要重新阅读本文件，确认执行流程与规范（防止上下文丢失导致“乱改/乱加”）。
3. **开始执行**：按本文件的 **MCP 工具链 + 变更 SOP** 定位 → 修改 → 验证 → 交付。

### 0.1 MCP 工具链（必须使用/必须做出选择）

本项目默认使用 MCP 工具链提升定位精度与交付质量（避免“凭记忆猜 API”，避免破坏性优化）。

**强制项（每次任务都要用）**

- **Serena**：语义级代码检索 + 精准编辑（定位符号、追踪引用、替换方法体，避免大范围误改）。
- **ripgrep（rg）**：本地超快文本搜索（快速定位入口/配置键/日志/调用链）。
- **Git**：查看 `diff/log/show/blame`，保证改动最小、可回滚、删除冗余。
- **Filesystem**：受控读写文件（读/写/列目录/搜索；修改前先确认路径在允许范围）。

**补充强制项（依赖频繁更新，必须遵守）**

- **每次任务必须实际使用 MCP 工具链定位与验证**：至少调用一次 Serena/rg/Git/Filesystem（不可只口头说明）。
- **Phase/Gate 类计划期间，MCP Research Loop 视为强制项**：每轮必须实际调用 Context7 + tavily_local + Fetch（若 Fetch 被 403/阻断则改用 tavily-extract），并把关键来源链接与取舍结论写入该计划的归档目录（`archives/plans/<plan_id>/docs/decision_record_*.md`），禁止“凭记忆猜”。（历史：去 LangChain 计划已归档到 `archives/plans/2026-01_de_langchain_phase0-7/`）
- **查询类 MCP 资料必须“领域/方向相关”（核心硬规范）**：使用 Context7/tavily_local/Fetch 获取的资料，必须直接服务于 MintChat 的方向（AI 伴侣 / 角色扮演型智能体：低延迟流式体验、角色一致性与情绪表达、可控工具调用、隐私与本地优先、多模态/GUI 不阻塞、以及“关系/偏好/事件”类记忆）。禁止为了“看起来先进”引入偏离方向的技术路线（例如把记忆系统默认等同于 RAG/知识库问答）。若确需引入跨领域技术，必须在对应 `decision_record_phase*.md` 中写清：为何适配本项目方向、替代方案对比、以及不采纳方案的理由；并在可能引入行为改变/大重构前先与 Owner 确认。
- **第三方依赖/接口禁止“凭记忆猜”**：涉及第三方库/API/迁移/报错/行为不确定时，优先 Context7；不足再用 tavily_local + Fetch。
- **工具不可用必须说明与替代**：若某 MCP 工具暂时不可用，最终回复必须记录原因，并给出替代定位/验证步骤。

**按需强制项（满足条件时必须用）**

- **Context7**：涉及第三方库/版本/API 示例/迁移时必须使用（先 `resolve-library-id` 再 `get-library-docs`，以最新文档为准）。
- **tavily_local + Fetch**：遇到报错、行为不确定、需要最新资料时必须使用（先 tavily 搜索，再用 Fetch 抓取并提炼关键段落）。

> 交付要求：每次最终回复必须包含 “本次使用了哪些 MCP 工具/哪些不需要”的记录（哪怕是简单任务）。

### 0.2 MCP 工具说明（What / When / How）

以下为本项目约定的 MCP 工具用法（写代码前先选对工具）：

- **Serena（语义级检索 + 精准编辑）**
  - **作用**：在不通读整个文件的前提下，按“符号/引用/结构”定位与修改代码，减少误伤。
  - **何时用**：需要理解某段实现、找调用方、做方法级/类级替换、跨文件追踪引用时。
  - **推荐做法**：`get_symbols_overview` → `find_symbol(include_body)` → `find_referencing_symbols` → 小步 `replace_symbol_body/insert_*`；修改前后用 `think_about_*` 自检。

- **ripgrep（rg，本地字符串搜索）**
  - **作用**：极快定位字符串/关键字出现位置，辅助确定入口与影响范围。
  - **何时用**：找配置键、日志文本、UI 文案、类名/方法名片段、临时排查“谁在调用”。
  - **推荐做法**：优先 `rg -n "pattern" src/ tests/`；需要跨平台/编码容错时加 `-S`。

- **Filesystem（受控读写文件）**
  - **作用**：安全读取/写入文件、列目录、批量读文件；适合文档/配置/脚本与小块文本编辑。
  - **何时用**：需要读取/写入非代码文件、批量读取多个文件、做小范围文本替换时。
  - **推荐做法**：先 `list_allowed_directories`/`list_directory` 再读写；改动尽量用最小 diff。

- **Git（diff / history / blame）**
  - **作用**：审阅改动、定位回归原因、理解历史决策；避免“改着改着越改越多”。
  - **何时用**：任何可能影响行为的改动前后；回归问题排查；需要确认“是否真的删得掉”时。
  - **推荐做法**：`git status -sb` → `git diff` → 必要时 `git log -n 20`/`git show`/`git blame`。

- **tavily_local（联网搜索/库文档/报错）**
  - **作用**：获取最新资料（报错、库升级、最佳实践、平台差异、已知坑）。
  - **何时用**：遇到不确定的报错/行为、需要确认最新版本差异、需要官方/权威来源支持时。
  - **推荐做法**：先搜索再筛选权威来源（优先官方文档/仓库/issue）；必要时限制域名。

- **Fetch（抓取网页并适配 LLM）**
  - **作用**：把具体页面内容抓取成可读文本/markdown，便于精准引用与实现。
  - **何时用**：tavily 选中目标页面后，需要阅读细节（API 参数、示例代码、迁移说明）。
  - **推荐做法**：先 tavily 再 Fetch；只提炼与当前需求相关的段落，避免照搬大段文本。

- **Context7（最新依赖文档/示例）**
  - **作用**：用“版本化文档”解决训练数据过时问题，获取正确的 API 与最佳实践。
  - **何时用**：涉及 LangChain/LangGraph、PyQt6、FunASR、OpenAI SDK 等第三方库接口或升级。
  - **推荐做法**：先 `resolve-library-id` 再 `get-library-docs(topic=...)`；以文档为准再落地代码。

### 0.3 最终回复模板（必须）

每次任务结束时，最终回复末尾必须包含以下记录（可简写，但不可省略）：

- **MCP 使用记录**：Serena=用/不用(原因)；rg=用/不用；Filesystem=用/不用；Git=用/不用；Context7=用/不用；tavily_local=用/不用；Fetch=用/不用
- **验证**：pytest=通过/未跑(原因)；black/flake8/mypy=通过/未跑(原因)
- **风险/回滚点**：如果改动可能影响行为/兼容性，写清回滚点（文件/开关/commit/配置）

---

## 1) 项目结构（Project Structure）

MintChat 是一个 **Python 3.13+** 项目（LangChain/LangGraph + PyQt6，多模态 + 工具 + 记忆 + Live2D）。

- 核心代码：`src/`
  - `agent/`：智能体编排（chat/chat_stream、memory、tools、路由）
  - `multimodal/`：TTS / ASR / VAD / Vision
  - `gui/`：PyQt6 UI（主入口：`MintChat.py`）
  - `auth/`：登录/会话
  - `character/`：角色/人设数据
  - `config/`：配置与 settings（例如：`src/config/settings.py`）
  - `utils/`：通用工具（日志、缓存、依赖检测、性能工具等）
  - `version.py`：版本元数据
- 示例：`examples/`
- 脚本：`scripts/`
- 测试：`tests/`（共享 fixture：`tests/conftest.py`）
- 运行产物（git 忽略）：`data/`、`logs/`
- 文档：`docs/`

---

## 2) 环境与依赖（Python 3.13 + uv + .venv）

本仓库使用 **uv** 管理依赖，并使用项目级虚拟环境 **`.venv/`**。

- 依赖声明（source of truth）：`pyproject.toml`
- 锁文件（必须提交）：`uv.lock`
- 创建/同步环境：
  - 运行环境：`uv sync --locked --no-install-project`
  - 含开发工具：`uv sync --locked --group dev --no-install-project`

### 2.1 运行方式（无需激活 venv）

- Windows：`.\.venv\Scripts\python.exe MintChat.py`
- macOS/Linux：`./.venv/bin/python MintChat.py`
- 也可使用 uv：`uv run python MintChat.py`

### 2.2 PyTorch（CUDA / cu130）

- Windows/Linux 固定使用 CUDA 13.0 wheels：`torch==2.9.1+cu130`（见 `pyproject.toml` 的 `[tool.uv.sources]` / `[[tool.uv.index]]`）
- macOS：使用 CPU 版：`torch==2.9.1`
- 验证：
  - Windows：`.\.venv\Scripts\python.exe -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())"`

### 2.3 可选能力（extras）

- ASR（语音识别 / FunASR 等较重依赖）：`uv sync --locked --no-install-project --extra asr`

### 2.4 依赖更新流程（必须可回滚）

1. 修改 `pyproject.toml`
2. 执行 `uv lock`
3. 执行 `uv sync --locked --no-install-project`（需要开发工具则加 `--group dev`）
4. 若入口/命令变更，更新 `README.md` / 相关脚本说明

---

## 3) 常用命令（Build/Test/Quality Gates）

推荐（不依赖 Makefile）：

- 安装：`uv sync --locked --no-install-project`
- 开发依赖：`uv sync --locked --group dev --no-install-project`
- 测试：
  - Windows：`.\.venv\Scripts\python.exe -m pytest -q`
  - macOS/Linux：`./.venv/bin/python -m pytest -q`
- 覆盖率：
  - Windows：`.\.venv\Scripts\python.exe -m pytest --cov=src --cov-report=html --cov-report=term tests/`
  - macOS/Linux：`./.venv/bin/python -m pytest --cov=src --cov-report=html --cov-report=term tests/`
- 格式化：
  - Windows：`.\.venv\Scripts\python.exe -m black src/ tests/ examples/`
  - macOS/Linux：`./.venv/bin/python -m black src/ tests/ examples/`
- Lint：
  - Windows：`.\.venv\Scripts\python.exe -m flake8 src/ tests/ examples/ --max-line-length=100 --ignore=E203,W503`
  - macOS/Linux：`./.venv/bin/python -m flake8 src/ tests/ examples/ --max-line-length=100 --ignore=E203,W503`
- 类型检查：
  - Windows：`.\.venv\Scripts\python.exe -m mypy src/ --ignore-missing-imports`
  - macOS/Linux：`./.venv/bin/python -m mypy src/ --ignore-missing-imports`

Makefile 快捷（可选）：`make install` / `make dev` / `make test` / `make lint` / `make format` / `make type-check` / `make clean`

---

## 4) “优秀代码逻辑”检查清单（MintChat 维护版）

一个“优秀的代码逻辑”不是某种写法，而是一组可长期维护、可验证、可演进的性质。以下是本项目的默认验收清单。

### 4.1 正确性可被证明或验证（Correctness）

- 关键路径有明确输入/输出/边界条件（空值、长度、编码、设备、超时）
- 重要不变量（invariants）必须落地到：
  - 代码断言/校验（对外部输入、配置、工具返回），或
  - 单元测试/回归测试（尤其是历史 bug）
- 失败方式明确：
  - 什么时候抛异常、什么时候返回空、什么时候降级、什么时候重试
  - 超时/取消要可控（避免 GUI 卡死、避免流式输出“空回复”）

### 4.2 可读性（Readability）

- 代码像“叙述”一样可读：先做什么、再做什么、为什么
- 命名准确表达意图（intent），避免误导（不要用实现细节命名）
- 控制流不过度嵌套：早返回、拆分函数、降低圈复杂度
- 同类问题同类解法：错误处理/返回约定/日志结构保持一致

### 4.3 单一职责 + 清晰边界（SRP / Boundaries）

- 一个函数只做一件事，一个模块聚焦一个领域
- I/O 与纯逻辑分离：网络/文件/DB/模型调用尽量放在边界层
- 外部依赖集中在适配层（adapter），核心逻辑尽量“纯”（便于测试与复用）

### 4.4 可测试性（Testability）

- 倾向纯函数化：核心逻辑不依赖全局状态/时间/随机数/环境变量
- 依赖注入：把客户端/模型/存储作为参数传入（或在构造时注入）
- 固定数据形状：优先使用 `dataclasses.dataclass` / `pydantic.BaseModel`（配置/事件/协议），避免匿名 dict 传播
- 测试覆盖关键分支：正常、边界、异常、超时/重试/降级
- 新增功能必须配套测试；修 bug 必须补回归测试

### 4.5 可维护与可扩展（Evolvability）

- 新需求优先通过“新增模块/策略/实现”完成，而不是到处塞 if/else
- 用表驱动/映射/注册表替代硬编码分支（尤其工具系统、事件系统）
- 避免过度耦合：改 A 不牵连 B；接口更稳定，实现可迭代

### 4.6 健壮性（Robustness）

- 对不可信输入防御：类型、范围、空值、编码、长度、路径、权限
- 可恢复：可重试、可降级、可超时、可取消
- 资源管理严谨：文件/连接/线程/进程必须确保关闭；优先使用 `with` / 上下文管理器；后台任务要可取消
- 日志可定位问题：关键参数、耗时、错误上下文（避免刷屏，热路径限频）

### 4.7 性能意识但不过早优化（Performance, non-destructive）

- 优先选择正确的数据结构与算法（先解决 O(n²)）
- 热路径减少重复计算：缓存/预编译/惰性加载（要有失效策略）
- 任何“性能优化”不得破坏语义/体验：
  - 不允许为了“更快”删功能、吞异常、改变输出契约
  - 如果必须改变行为，先写测试/文档并显式说明

### 4.8 一致性与风格统一（Python 3.13）

参考：PEP 8 / Google Python Style Guide / Black。

- 格式：以 `black` 为准（`pyproject.toml` 中 `line-length = 100`）
- 命名：`snake_case`（函数/变量/模块），`PascalCase`（类），`UPPER_SNAKE_CASE`（常量）
- 类型标注：优先使用现代语法（`list[str]`、`X | Y`、`type Alias = ...`）
- 文档字符串：公共/复杂函数必须写 docstring，说明语义与边界；实现细节写行内注释即可

### 4.9 项目特定的“边界纪律”（MintChat 特别重要）

- **GUI 主线程禁止阻塞 I/O**：LLM/检索/ASR/TTS/网络/磁盘等必须在后台线程或异步循环中执行
- 线程生命周期必须可控：任何 QThread/后台 worker 必须在退出时 `quit()` + `wait()`，避免 `QThread: Destroyed while thread is still running`
- 流式输出/工具调用/可选依赖必须可降级：缺依赖/超时不允许导致空回复或卡死

---

## 5) 测试规范（Testing）

- Pytest 自动发现：`tests/test_*.py`、`Test*` 类
- 共享 fixture：`tests/conftest.py`
- 长耗时：`@pytest.mark.slow`
- 集成路径：`@pytest.mark.integration`

新增/修复建议：

- 工具系统：覆盖“正常/超时/异常/空结果/降级” + 最终回复语义
- GUI/线程：覆盖“启动/停止/取消/异常退出”基本行为（尽可能用最小替身或隔离）
- 多模态：覆盖“缺依赖降级”与关键路径输入输出（不要做脆弱的端到端）

---

## 6) 配置与安全（Config & Security）

- `config.user.yaml` 为本机私有配置（git 忽略），禁止提交任何密钥
- `config.user.yaml.example` 为提交模板：新增/变更用户配置项必须同步更新（`config.yaml.example` 为 legacy 单文件模板，可选维护）
- `config.dev.yaml` 为开发者/调试配置（允许提交到 git），**必须保持不含密钥/账号/敏感信息**；如需密钥请使用环境变量或 `config.user.yaml`
- 约定：已允许 Codex 在维护/调试时直接修改 `config.dev.yaml`（不含密钥）；如涉及共享配置变更可直接更新并提交该文件
- `.env` 同样忽略；敏感覆盖优先使用环境变量
- 不要把 token / key / 账号写入代码、测试、日志、示例

---

## 7) 变更流程（维护升级 SOP）

每次修复/优化/升级默认按以下流程执行（与 “0) 每轮对话必做流程” 配套，**不能跳步**）：

1. **先分析需求**：目标、影响范围、约束、验收标准、风险/回滚点；不清楚就先问。
2. **熟读 AGENTS.md**：每次对话开始都要重新阅读本文件，确认规范与工具链（防止上下文丢失导致偏航）。
3. **定位与影响面评估（必须用 MCP）**：优先 Serena 做语义级定位/引用追踪；配合 rg 快速扫关键字；必要时用 Git `log/show/blame` 查历史与回归点。
4. **获取外部资料（按需强制）**：涉及第三方库/API/版本差异/报错时，先 Context7；不足再用 tavily_local 搜索 + Fetch 抓取并提炼关键段落。
5. **最小化改动实现修复**：优先修根因；避免无关重构；删除无用代码/文件；严禁破坏性优化（不吞异常、不改输出契约）。
6. **跑质量门禁**：`pytest` 必须过；按需 `black` / `flake8` / `mypy`（至少保证不引入明显风格与类型退化）。
7. **更新文档/示例**：入口/命令/配置变更时必须同步更新，并写清迁移/回滚步骤。
8. **交付说明必须包含**：原因、改动点、验证方式、潜在风险/回滚点 + 本次 MCP 工具使用记录（用/不用都要说明）。
9. **范围内打扫（必须）**：本轮维护会由用户指定“抽象范围”（例如：登录-注册-修改密码）。在完成功能后，必须对该范围内做一次收尾整理：删除冗余/未引用代码与文件、统一样式与命名、补充必要注释/类型/测试（按需）、确认无破坏性改动与可回滚点。
10. **范围策略（重要）**：用户给定范围是为了减少大幅度的跨文件操作与误伤风险，而不是为了“偷懒”。在定位/实现过程中若发现真实问题（尤其是检索 bug、崩溃、明显错误、回归），必须修复，即使超出范围；严禁遗留“已发现但未修复”的问题。若修复将引入大范围行为变更/大重构，应先与用户确认再推进。

11. **计划归档（重要）**：凡是 Phase/Gate 类的长期计划，在完成验收后必须归档：\n+    - 产物进入 `archives/plans/<plan_id>/`（文档/脚本/测试数据/规划图等）\n+    - 用 SQLite 档案库索引登记到 `archives/archive.sqlite3`（见 `archives/README.md` 与 `scripts/archive_manager.py`）\n+    - 归档完成后清理运行时产物（`*.egg-info`、`__pycache__`、`.pytest_cache`、`.mypy_cache` 等），保持仓库整洁
