# MintChat — AGENTS.md（维护 / 升级 / 代码质量规范）

> 目标：稳定优先；可长期维护、可验证、可回滚、可演进。任何“性能优化”必须非破坏式（不牺牲正确性与体验）。

## 0) 分区约定（先读）

- `archives/`：**已完成计划**与历史冗余回收的“墓地/纪念馆”（默认只读）。
  - **未经 Owner 明确授权：禁止**在 `archives/` 下新增/修改任何文件（包括 plans、scripts、golden、data 等）。
- `plans/`：**进行中计划**的工作区（Owner 同意后才创建/写入）。
- 流程图：Owner 指定的计划流程图文件（本仓库当前为 `flowchart_TD.txt`，位于项目根目录）。

## 1) 每轮对话必做流程（不能跳步）

1. **先分析需求**：目标、影响范围、约束、验收标准、风险/回滚点；不清楚先问。
2. **重读规范**：重新阅读本文件；若涉及计划，必须同步阅读对应流程图（例如 `flowchart_TD.txt`）。
3. **开始执行**：按 “定位 → 修改 → 验证 → 交付” 的 SOP 推进。

## 2) 计划文档规范（Phase/Gate）

每个 Phase **只允许 2 个 Markdown**（除非 Owner 明确要求更多）：

- `plans/<plan_id>/phase<N>_dev.md`：给 Agent 用（最佳实现方案 + 行动轨迹 + Research Loop 结论与链接）。
- `plans/<plan_id>/phase<N>_checklist.md`：给 Owner 用（进度/验收清单）。

规则：

- **不要**在进行中计划里创建 `decision_record_*.md`、`summary.md`、`touchpoints.md` 等额外文档；这些内容应并入当期 `phase<N>_dev.md` / `phase<N>_checklist.md`。
- `plans/` 只放上述 2 个 Markdown；计划期产生的脚本/测试/数据/基线资产必须落在项目目录（如 `src/`、`tests/`、`scripts/`），不要塞进 `plans/`。
- 计划完成/废弃后，若 Owner 要求归档：再把 `plans/<plan_id>/` 迁移到 `archives/plans/<plan_id>/`（见第 6 节）。

## 3) MCP 工具链（每次任务都要实际使用）

### 3.1 必用（每次至少用一次）

- Serena：语义级检索与精准改动（符号/引用/结构）。
- rg：快速字符串搜索定位入口/配置/日志/调用链。
- Git：`status/diff/log/blame`，保证改动最小且可回滚。
- Filesystem：受控读写/列目录/批量读文件。

### 3.2 Phase/Gate 额外强制（Research Loop）

当任务属于流程图里的 Phase/Gate 时，每轮必须实际调用：

- Context7 + tavily_local + Fetch（若 Fetch 403/阻断 → 用 tavily-extract）。

并把关键**来源链接**、**取舍结论**、**不变量/风险/回滚点**写入当期 `plans/<plan_id>/phase<N>_dev.md`（不要写进 `archives/`）。

硬规范：

- 查询资料必须服务于 MintChat 方向（AI 伴侣/角色扮演：低延迟流式体验、角色一致性/情绪表达、可控工具调用、隐私与本地优先、多模态/GUI 不阻塞、关系/偏好/事件类记忆）。
- 第三方依赖/API/迁移/报错：禁止“凭记忆猜”；优先 Context7，不足再 tavily+Fetch。
- 工具不可用：必须说明原因与替代步骤。

## 4) 代码质量与边界（必须）

- 正确性：关键路径要有清晰输入/输出/边界；失败方式明确（异常/空结果/降级/重试/超时/取消）。
- GUI 主线程：禁止阻塞 I/O（LLM/检索/ASR/TTS/网络/磁盘必须后台执行）；线程生命周期必须可控（`quit()` + `wait()`）。
- 流式体验：不中断/不卡死；外部服务或可选依赖不可用时必须自动降级（不允许“空回复”）。
- 测试：新增功能必须配套测试；修 bug 必须补回归测试；避免脆弱端到端。
- 风格：以 `black` 为准（line-length=100）；命名与类型标注保持一致，避免无意义重构。
- 安全：禁止提交密钥；`config.user.yaml` 为本机私有；`config.dev.yaml` 可提交但必须不含敏感信息；优先用环境变量覆盖。

## 5) 项目结构（速查）

- 代码：`src/`
  - `src/agent/`：智能体编排（chat/chat_stream、memory、tools、路由）
  - `src/multimodal/`：TTS/ASR/VAD/Vision
  - `src/gui/`：PyQt6 UI（入口：`MintChat.py`）
  - `src/config/`：配置与 settings（`src/config/settings.py`）
- 测试：`tests/`
- 脚本：`scripts/`
- 文档：`docs/`

## 6) 环境与常用命令（Python 3.13 + uv + .venv）

- 依赖源：`pyproject.toml`
- 锁文件：`uv.lock`（必须提交）

```powershell
uv sync --locked --no-install-project
uv sync --locked --group dev --no-install-project
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m black src tests examples
.\.venv\Scripts\python.exe -m flake8 src tests examples --max-line-length=100 --ignore=E203,W503
.\.venv\Scripts\python.exe -m mypy src/ --ignore-missing-imports
```

## 7) 变更 SOP（维护/升级）

1. 需求分析（目标/范围/约束/验收/风险回滚点）。
2. 重读规范（AGENTS + 流程图）。
3. 定位与影响面评估（Serena + rg + Git）。
4. 外部资料（按需；Phase/Gate 强制 Research Loop）。
5. 最小化改动实现（优先根因；不做无关重构；不吞异常；不改输出契约）。
6. 验证：`pytest` 必须过；`black/flake8/mypy` 至少不引入退化（mypy 若受环境影响，需写明运行参数与原因）。
7. 更新必要文档/示例（入口/命令/配置变更必须同步）。
8. 交付说明：原因/改动点/验证方式/风险回滚点 + MCP 使用记录。
9. 范围内打扫：删除冗余/未引用代码与文件、统一样式与命名、补充必要测试（按需）。
10. **归档（仅在 Owner 明确要求“计划完成/废弃可归档”后执行）**：
    - `plans/<plan_id>/` → `archives/plans/<plan_id>/`
    - 若启用档案索引：登记到 `archives/archive.sqlite3`（见 `archives/README.md` 与 `scripts/archive_manager.py`）
    - 清理运行时产物：`*.egg-info`、`__pycache__`、`.pytest_cache`、`.mypy_cache` 等

## 8) 最终回复模板（必须）

- MCP 使用记录：Serena=用/不用(原因)；rg=用/不用；Filesystem=用/不用；Git=用/不用；Context7=用/不用；tavily_local=用/不用；Fetch=用/不用
- 验证：pytest=通过/未跑(原因)；black/flake8/mypy=通过/未跑(原因)
- 风险/回滚点：写清回滚点（文件/开关/配置/commit）
