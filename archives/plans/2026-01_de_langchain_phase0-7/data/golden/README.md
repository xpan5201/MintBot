# Golden 资产（本机生成）

本目录用于存放去 LangChain/LangGraph 计划中的 **Golden 录制/对比** 资产（JSON）。

说明：
- Golden 需要依赖本机配置 LLM key 与网络环境，因此本仓库可能不会长期保存所有录制文件。
- `archives/plans/2026-01_de_langchain_phase0-7/scripts/de_langchain_capture_golden.py` 默认输出到本目录。

常用命令（示例）：

```powershell
.\.venv\Scripts\python.exe archives\plans\2026-01_de_langchain_phase0-7\scripts\de_langchain_capture_golden.py --runner backend
.\.venv\Scripts\python.exe archives\plans\2026-01_de_langchain_phase0-7\scripts\de_langchain_capture_golden.py --runner backend --tools
.\.venv\Scripts\python.exe archives\plans\2026-01_de_langchain_phase0-7\scripts\de_langchain_capture_golden.py --runner backend --tools --pipeline
```

对比（Gate#5 preset）：

```powershell
.\.venv\Scripts\python.exe archives\plans\2026-01_de_langchain_phase0-7\scripts\de_langchain_compare_golden.py --preset gate5-native-pipeline
```

