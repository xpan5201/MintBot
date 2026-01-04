# 去 LangChain/LangGraph 计划（规划与验收资产）

本目录用于存放 **去 LangChain/LangGraph（高度自研化）** 的规划与交付资产，目标是：

- 最终彻底移除 `langchain* / langgraph* / langsmith*` 依赖
- 统一走 **OpenAI API 兼容接口**（`base_url + api_key + model`）
- 稳定优先：每阶段可回滚、可验证（pytest/black/flake8/mypy + GUI/流式/工具/记忆冒烟）

本计划的完整流程图见：`archives/plans/2026-01_de_langchain_phase0-7/flowchart_TD.txt`。

## Phase 0-7（盘点→收尾）的产物清单

- `decision_record_phase0.md`：Phase 0 的《决策记录》（取舍/不变量/后续验证点）
- `decision_record_phase2.md`：Phase 2 的《决策记录》（从 Message/叶子模块起步）
- `decision_record_phase3.md`：Phase 3 的《决策记录》（Native OpenAI-compatible 后端）
- `decision_record_phase4.md`：Phase 4 的《决策记录》（自研 Tool-Loop / AgentRunner）
- `decision_record_phase5.md`：Phase 5 的《决策记录》（去 LangGraph/middleware → 自研 Pipeline）
- `decision_record_phase6.md`：Phase 6 的《决策记录》（去 langchain-chroma/embeddings → 检索层加固）
- `provider_matrix.md`：Provider 能力矩阵模板（兼容层入口的事实表）
- `touchpoints.md`：当前 LangChain/LangGraph 触点清单（迁移顺序与 Phase 7 “零引用验收”依据）
- `gate0_checklist.md`：Gate#0 完成标准（进入 Phase 1 的前置门禁）
- `gate1_checklist.md`：Gate#1 完成标准（协议层新增完成）
- `gate2_checklist.md`：Gate#2 完成标准（LangChainBackend 适配器 + 叶子模块迁移）
- `gate3_checklist.md`：Gate#3 完成标准（Native 后端 + Golden 灰度对比）
- `gate4_checklist.md`：Gate#4 完成标准（自研 Tool-Loop / AgentRunner）
- `gate5_checklist.md`：Gate#5 完成标准（去 LangGraph/middleware → 自研 Pipeline）
- `gate6_checklist.md`：Gate#6 完成标准（检索层：Chroma/embeddings 加固）
- `phase5_pipeline_design.md`：Phase 5 的设计草案（接口形状/阶段职责/实施顺序）

## 辅助脚本（Golden / 审计）

- `archives/plans/2026-01_de_langchain_phase0-7/scripts/de_langchain_capture_golden.py`：录制 golden（支持 `--runner agent|backend`；Phase 3 建议用 backend runner）
- `archives/plans/2026-01_de_langchain_phase0-7/scripts/de_langchain_compare_golden.py`：对比两份 golden（langchain vs native），输出差异摘要与阈值判定
- `archives/plans/2026-01_de_langchain_phase0-7/scripts/de_langchain_audit_touchpoints.py`：扫描仓库内 langchain/langgraph/langsmith 触点，输出报告（Phase 0/7 用）

## Windows 运行提示（Troubleshooting）

- 优先用 `uv run` 运行脚本（避免 `.venv\\Scripts\\python.exe` 被系统/杀软阻止执行）：
  - `uv run python archives\\plans\\2026-01_de_langchain_phase0-7\\scripts\\de_langchain_capture_golden.py --backend native --runner backend`
- 若提示“此应用无法在你的电脑上运行 / Access is denied / 不是有效的应用程序”，通常是虚拟环境解释器损坏：
  - 先尝试重新同步：`uv sync --locked --no-install-project`
  - 若仍失败：删除并重建 `.venv/`（或用 `pyvenv.cfg` 的 `home=` 路径恢复 `python.exe` 与 `python313.dll/python3.dll`）

## 执行原则（摘录）

- Phase 0 **禁止贸然改行为**：只允许加护栏（总开关/基线/脚手架/文档），不能引入链路变更。
- 每个 Phase/Gate 之前必须做 MCP Research Loop：Context7 + tavily_local + Fetch → 形成《决策记录》再落地实现。
