# Gate#3 Checklist（Phase 3 完成标准）

> Gate#3 的定位：新增 `OpenAICompatibleBackend`（native 后端）并以 **Golden 对比 + 性能不退化**
> 的方式完成灰度验证；默认仍走 `langchain`，确保可回滚。

验证记录：

- ✅ 2026-01-01：进入 Phase 3（开始：native 后端 + 单测 + golden 录制能力）
- ✅ 2026-01-02：Gate#3 验证通过（backend runner 录制与对比；对比阈值：`min_text_similarity=0.93`、`max_first_chunk_latency_delta_s=20`）

## 1) Native 后端（必须）

- [x] `src/llm_native/openai_backend.py`：实现 `OpenAICompatibleBackend(ChatBackend)`（complete/stream）
- [x] base_url 兼容：裸 host 自动补 `/v1`，与现有 factory 规则一致
- [x] streaming 解析：
  - [x] `delta.content` → `TextDeltaEvent`
  - [x] `delta.tool_calls` / `delta.function_call` → `ToolCallDeltaEvent`（仅输出 delta，不在本 Gate 聚合）
- [x] 资源管理：提供 best-effort `close()`（不影响主流程）

## 2) 测试（必须）

- [x] 新增 `tests/test_llm_native_openai_backend.py`：覆盖 complete/stream 基本行为与 delta 解析
- [x] 现有测试不回归（pytest 全绿）

## 3) Golden（必须）

- 说明：Phase 3 仍未把 `native` 后端接入主 Agent（`Agent.llm_backend=native` 仍是占位），
  因此 Gate#3 的 Golden **以 ChatBackend 层为准**（`--runner backend`），避免把“Agent 行为差异”误判为“后端差异”。  
- 建议：为了让 Golden 可复现并降低随机性，backend runner 默认会用 `temperature=0`（也可用 `--temperature` 覆盖）。
- 备注：本 Gate 发生时仓库仍包含 `langchain` 后端；当前仓库已完全移除该依赖。  
  本归档目录已保留当时生成的 Golden JSON（见 `data/golden/`），每个文件的 `meta.git_revision` 可用于精确定位对应代码版本；  
  如需复现历史对比，请 checkout 到相应 revision 再运行脚本。
- [x] 生成基线（langchain, backend runner）：`archives/plans/2026-01_de_langchain_phase0-7/data/golden/langchain_backend_stream_golden.json`  
  - 运行（历史命令，仅作记录）：`archives/plans/2026-01_de_langchain_phase0-7/scripts/de_langchain_capture_golden.py --backend langchain --runner backend`
- [x] 生成候选（native, backend runner）：`archives/plans/2026-01_de_langchain_phase0-7/data/golden/native_backend_stream_golden.json`  
  - 运行（历史命令，仅作记录）：`archives/plans/2026-01_de_langchain_phase0-7/scripts/de_langchain_capture_golden.py --backend native --runner backend`
- [x] 对比：运行 `archives/plans/2026-01_de_langchain_phase0-7/scripts/de_langchain_compare_golden.py`（默认会优先选择 `*_backend_stream_golden.json`；必要时用参数调低阈值）

## 4) 质量门禁（必须全绿）

```powershell
.\\.venv\\Scripts\\python.exe -m pytest -q
.\\.venv\\Scripts\\python.exe -m black src\\ tests\\ examples\\
.\\.venv\\Scripts\\python.exe -m flake8 src\\ tests\\ examples\\ --max-line-length=100 --ignore=E203,W503
.\\.venv\\Scripts\\python.exe -m mypy src\\ --ignore-missing-imports
```

## 5) Owner 验收点（必须确认）

- [x] 灰度可控：默认仍 `langchain`，开启 `native` 不影响 GUI 主线程（无卡顿/断流）
- [x] 回滚可用：随时切回 `langchain` 不丢功能、不损坏配置
