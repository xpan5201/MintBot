# 去 LangChain 计划数据（本机生成）

本目录用于存放去 LangChain/LangGraph 计划的**审计/对比**输出数据（JSON），例如触点扫描报告。

生成 touchpoints 报告：

```powershell
.\.venv\Scripts\python.exe archives\plans\2026-01_de_langchain_phase0-7\scripts\de_langchain_audit_touchpoints.py `
  --json data\de_langchain\touchpoints.json `
  --fail-if-found
```

