# 日志系统指南

## 功能概览
- 统一入口：优先使用 loguru，缺失时自动降级到标准 logging，格式保持一致。
- 双通道输出：控制台彩色日志 + 文件日志（默认 `logs/mintchat.log`），支持大小/时间轮转与保留。
- 结构化输出：可选 JSON 行日志（默认开启，`logs/mintchat.jsonl`），方便分析与上报。
- 上下文绑定：支持 `session_id`、`user_id` 等上下文透传，跨线程/协程排查更方便。
- 兼容捕获：自动接管标准库 logging 与 `warnings`，减少割裂的日志源。

## 配置项（config.user.yaml / config.dev.yaml）
- `log_level`：日志级别，默认 `INFO`。
- `log_dir`：日志目录，默认 `logs/`。
- `log_rotation`：轮转条件（loguru 语法，如 `50 MB`、`1 week`）。
- `log_retention`：保留时间（loguru 语法，如 `14 days`）。
- `log_json`：是否输出 JSON 行日志，默认 `true`。
- `log_quiet_libs`：需降噪的第三方 logger 列表；为空/未设置时使用内置默认列表（见 `src/utils/logger.py` 的 `DEFAULT_QUIET_LIBS`）；设置非空列表会覆盖默认列表。
- `log_quiet_level`：降噪级别，默认 `WARNING`（作用于 `log_quiet_libs`）。
- `log_drop_keywords`：附加丢弃关键词列表；为空/未设置时仅使用内置默认（见 `src/utils/logger.py` 的 `DEFAULT_DROP_KEYWORDS`）；设置非空列表会在默认基础上追加。

> 可用环境变量快速覆盖：`MINTCHAT_LOG_LEVEL`、`MINTCHAT_LOG_DIR`、`MINTCHAT_LOG_ROTATION`、`MINTCHAT_LOG_RETENTION`、`MINTCHAT_LOG_JSON` 等。

## 在代码里使用
```python
from src.utils.logger import get_logger, log_context, bind_context, set_log_level

logger = get_logger(__name__)
logger.info("启动中")

# 临时绑定上下文（推荐）
with log_context(session_id=session.id, user_id=user.id):
    logger.info("处理请求")

# 全局绑定/更新上下文
bind_context(request_id="abc123")

# 运行时提升日志级别
set_log_level("DEBUG")
```

## 文件位置与轮转
- 文本日志：`logs/mintchat.log`
- JSON 日志：`logs/mintchat.jsonl`（可通过 `log_json` 关闭）
- 默认轮转：`50 MB`，默认保留：`14 days`

如需调整，将配置写入 `config.user.yaml`（或 `config.dev.yaml`）或设置对应环境变量，程序启动时会自动应用。
