# Gate#0 Checklist（Phase 0 完成标准）

> Gate#0 的定位：**不改现有行为** 的前提下，把“去 LangChain/LangGraph”后续阶段需要的护栏建好。  
> 达标后才进入 Phase 1（自研协议层）。

验证记录：

- ✅ 2026-01-01：owner 已验证 Gate#0 条目无误，允许进入 Phase 1

## 1) 资产完成情况（必须）

- [x] `archives/plans/2026-01_de_langchain_phase0-7/docs/decision_record_phase0.md` 已完成（含不变量/取舍/验证点）
- [x] `archives/plans/2026-01_de_langchain_phase0-7/docs/provider_matrix.md` 已完成并按你的实际 provider 验证
- [x] `archives/plans/2026-01_de_langchain_phase0-7/docs/touchpoints.md` 已完成（触点清单可用于 Phase 7 验收）
- [x] 总开关已落地：`Agent.llm_backend = langchain|native`
  - `native` 仍为占位，不允许改变现有链路
- [x] Golden 基线录制脚本存在：`archives/plans/2026-01_de_langchain_phase0-7/scripts/de_langchain_capture_golden.py`
- [x] 触点审计脚本存在：`archives/plans/2026-01_de_langchain_phase0-7/scripts/de_langchain_audit_touchpoints.py`

## 2) 推荐执行命令（本机）

### 2.1 触点审计（输出报告）

Windows：

```powershell
.\.venv\Scripts\python.exe archives\plans\2026-01_de_langchain_phase0-7\scripts\de_langchain_audit_touchpoints.py --json data\de_langchain\touchpoints.json
```

### 2.2 Golden 基线录制（建议录 3 组）

> 默认不会写入长期记忆，避免污染向量库。如需覆盖记忆链路，用 `--save-long-term`。

```powershell
.\.venv\Scripts\python.exe archives\plans\2026-01_de_langchain_phase0-7\scripts\de_langchain_capture_golden.py --prompt "你好，简单自我介绍一下。"
.\.venv\Scripts\python.exe archives\plans\2026-01_de_langchain_phase0-7\scripts\de_langchain_capture_golden.py --prompt "帮我查一下今天北京天气" --prompt "顺便给出穿衣建议"
.\.venv\Scripts\python.exe archives\plans\2026-01_de_langchain_phase0-7\scripts\de_langchain_capture_golden.py --prompt "给我一个JSON格式的待办清单，包含3项"
```

输出默认写入：`archives/plans/2026-01_de_langchain_phase0-7/data/golden/langchain_stream_golden.json`

## 3) 质量门禁（必须全绿）

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m black src\ tests\ examples\
.\.venv\Scripts\python.exe -m flake8 src\ tests\ examples\ --max-line-length=100 --ignore=E203,W503
.\.venv\Scripts\python.exe -m mypy src\ --ignore-missing-imports
```

## 4) 进入 Phase 1 的前置确认（owner 确认）

- [x] 允许新增 `src/llm_native/`（或类似目录）存放自研协议层/后端抽象（仅新增，不改现有调用）
- [ ] “双后端稳定期” 的验收阈值（TBD）将由你后续给出（例如：连续 N 天/错误预算/首包 P95）
