"""
日志工具模块（增强版）

目标：
- 控制台 + 文件双通道输出，文件自动轮转与保留
- 兼容 loguru 与标准 logging，统一格式和上下文
- 支持上下文绑定（如 session_id/user_id），方便跨线程/协程排查
- 捕获标准库 logging 与 warnings，减少日志割裂
"""

from __future__ import annotations

import logging
import os
import sys
import warnings
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import IO
from typing import Any, Dict, List, Optional

try:
    from loguru import logger as loguru_logger

    HAS_LOGURU = True
except ImportError:
    HAS_LOGURU = False
    loguru_logger = None

DEFAULT_LEVEL = os.getenv("MINTCHAT_LOG_LEVEL", "INFO")
DEFAULT_LOG_DIR = Path(os.getenv("MINTCHAT_LOG_DIR", "logs"))
DEFAULT_LOG_FILE = os.getenv("MINTCHAT_LOG_FILE", "mintchat.log")
DEFAULT_JSON_FILE = os.getenv("MINTCHAT_JSON_LOG_FILE", "mintchat.jsonl")
DEFAULT_ROTATION = os.getenv("MINTCHAT_LOG_ROTATION", "50 MB")
DEFAULT_RETENTION = os.getenv("MINTCHAT_LOG_RETENTION", "14 days")

# Keep original stdio references so we can safely wrap stdout/stderr without
# causing recursive logging (loguru console sink should always write to the
# original stream).
_ORIG_STDOUT: IO[str] = sys.stdout
_ORIG_STDERR: IO[str] = sys.stderr
DEFAULT_QUIET_LIBS = [
    # Silence root/third-party INFO logs by default (ModelScope/FunASR is very noisy on init).
    "root",
    "modelscope",
    "funasr",
    "transformers",
    "httpx",
    "asyncio",
    "urllib3",
    "charset_normalizer",
    "multipart.multipart",
    "httpcore",
    "openai",
    "chromadb",
    "posthog",
    "langchain",
    "src.agent.performance_optimizer",
]
DEFAULT_QUIET_LEVEL = os.getenv("MINTCHAT_LOG_QUIET_LEVEL", "WARNING")
DEFAULT_DROP_KEYWORDS = [
    "Request options:",
    "Sending HTTP Request:",
    "HTTP Response:",
    "receive_response_body.started",
    "receive_response_headers.started",
    "send_request_headers.started",
    "send_request_body.started",
    "插入消息:",
    "已显示",
    # ModelScope/FunASR model download noise (mostly path-heavy INFO logs)
    "download models from model hub",
    "downloading model from https://www.modelscope.cn",
    "loading pretrained params from",
    "ckpt:",
    "loading ckpt:",
    "load_pretrained_model:",
    "all keys matched successfully",
    "trust_remote_code:",
    "funasr version:",
    "scope_map:",
    "excludes:",
    "modelscope\\hub\\models",
]
ENV_DROP = os.getenv("MINTCHAT_LOG_DROP_KEYWORDS")
if ENV_DROP:
    DEFAULT_DROP_KEYWORDS.extend([kw.strip() for kw in ENV_DROP.split(",") if kw.strip()])

LOG_CONTEXT: ContextVar[Dict[str, Any]] = ContextVar("log_context", default={})
_loguru_base = None
_current_config: "LoggerConfig" | None = None


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() not in {"0", "false", "no", "off"}


def _configure_warning_filters() -> None:
    """Suppress known noisy warnings without hiding actionable errors."""
    # pydub: ffmpeg/avconv missing warning is expected in our default setup.
    # torchaudio will be used.
    warnings.filterwarnings(
        "ignore",
        message=r".*Couldn't find ffmpeg or avconv.*",
        category=RuntimeWarning,
    )
    # FunASR (paraformer_streaming): torch.cuda.amp.autocast deprecation is harmless noise.
    warnings.filterwarnings(
        "ignore",
        message=r".*torch\.cuda\.amp\.autocast\(.*\).*deprecated\..*",
        category=FutureWarning,
    )


@dataclass
class LoggerConfig:
    """日志配置容器"""

    level: str = DEFAULT_LEVEL
    log_dir: Path = DEFAULT_LOG_DIR
    log_file: str = DEFAULT_LOG_FILE
    json_file: str = DEFAULT_JSON_FILE
    rotation: str = DEFAULT_ROTATION
    retention: str = DEFAULT_RETENTION
    enable_json: bool = _env_flag("MINTCHAT_LOG_JSON", True)
    colorize: bool = _env_flag("MINTCHAT_LOG_COLOR", True)
    enqueue: bool = _env_flag("MINTCHAT_LOG_ENQUEUE", True)
    backtrace: bool = _env_flag("MINTCHAT_LOG_BACKTRACE", False)
    diagnose: bool = _env_flag("MINTCHAT_LOG_DIAGNOSE", False)
    capture_warnings: bool = _env_flag("MINTCHAT_CAPTURE_WARNINGS", True)
    extra: Dict[str, Any] = field(default_factory=dict)
    quiet_libs: List[str] = field(default_factory=lambda: list(DEFAULT_QUIET_LIBS))
    quiet_level: str = DEFAULT_QUIET_LEVEL
    drop_keywords: List[str] = field(default_factory=lambda: list(DEFAULT_DROP_KEYWORDS))

    def normalized_level(self) -> str:
        return str(self.level).upper()


class _LegacyLoggerAdapter:
    """
    兼容标准 logging `%s`/`%.0f` 风格与 exc_info 语义，保证旧调用不需要改动
    """

    __slots__ = ("_logger",)

    def __init__(self, logger):
        self._logger = logger

    @staticmethod
    def _format_message(message: Any, args: tuple[Any, ...]) -> str:
        if not args:
            return str(message)
        try:
            return str(message) % args
        except Exception:
            try:
                return str(message).format(*args)
            except Exception:
                joined = " ".join(str(arg) for arg in args)
                return f"{message} {joined}"

    def _log(self, method: str, message: Any, *args: Any, **kwargs: Any) -> None:
        # 快速级别判断：在日志级别未开启时避免做字符串格式化（热路径优化）
        level_name = str(method or "").upper()
        if level_name == "EXCEPTION":
            level_name = "ERROR"
        if hasattr(self._logger, "is_enabled"):
            try:
                if not self._logger.is_enabled(level_name):
                    return
            except Exception:
                pass
        elif hasattr(self._logger, "isEnabledFor"):
            try:
                level_no = getattr(logging, level_name, None)
                if isinstance(level_no, int) and not self._logger.isEnabledFor(level_no):
                    return
            except Exception:
                pass
        elif hasattr(self._logger, "_core") and hasattr(self._logger, "level"):
            # loguru 不提供标准 logging 的 isEnabledFor() 接口；使用其内部 min_level 做快速 gating。
            try:
                min_level = getattr(getattr(self._logger, "_core", None), "min_level", None)
                level_no = self._logger.level(level_name).no
                if (
                    isinstance(min_level, int)
                    and isinstance(level_no, int)
                    and level_no < min_level
                ):
                    return
            except Exception:
                pass

        exc_info = kwargs.pop("exc_info", None)
        extra = kwargs.pop("extra", None)
        formatted = self._format_message(message, args)
        target = self._logger

        if hasattr(target, "opt"):
            # 修复：wrapped logger 的调用位置（function/line）应指向业务代码，而不是本适配器。
            opt_kwargs: Dict[str, Any] = {"depth": 2}
            if exc_info:
                opt_kwargs["exception"] = True if exc_info is True else exc_info
            try:
                target = target.opt(**opt_kwargs)
            except Exception:
                pass

            if isinstance(extra, dict) and extra and hasattr(target, "bind"):
                try:
                    target = target.bind(**extra)
                except Exception:
                    pass

            log_callable = getattr(target, method, None)
            try:
                if callable(log_callable):
                    log_callable(formatted)
                else:
                    target.log(level_name, formatted)
            except Exception:
                try:
                    target.log("INFO", formatted)
                except Exception:
                    pass
            return

        # 标准 logging 兜底（无 loguru）
        call_kwargs: Dict[str, Any] = {}
        if exc_info:
            call_kwargs["exc_info"] = exc_info
        if isinstance(extra, dict) and extra:
            call_kwargs["extra"] = extra

        log_callable = getattr(target, method, None)
        if callable(log_callable):
            log_callable(formatted, **call_kwargs)
            return
        try:
            level_no = getattr(logging, level_name, logging.INFO)
            target.log(level_no, formatted, **call_kwargs)
        except Exception:
            try:
                target.log(formatted)
            except Exception:
                pass

    def bind(self, **kwargs: Any) -> "_LegacyLoggerAdapter":
        if hasattr(self._logger, "bind"):
            return _LegacyLoggerAdapter(self._logger.bind(**kwargs))
        return self

    def debug(self, message: Any, *args: Any, **kwargs: Any) -> None:
        self._log("debug", message, *args, **kwargs)

    def info(self, message: Any, *args: Any, **kwargs: Any) -> None:
        self._log("info", message, *args, **kwargs)

    def warning(self, message: Any, *args: Any, **kwargs: Any) -> None:
        self._log("warning", message, *args, **kwargs)

    def error(self, message: Any, *args: Any, **kwargs: Any) -> None:
        self._log("error", message, *args, **kwargs)

    def exception(self, message: Any, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("exc_info", True)
        self._log("exception", message, *args, **kwargs)

    def critical(self, message: Any, *args: Any, **kwargs: Any) -> None:
        self._log("critical", message, *args, **kwargs)

    def log(self, level: str, message: Any, *args: Any, **kwargs: Any) -> None:
        self._log(level.lower(), message, *args, **kwargs)

    # 兼容标准 logging 接口（用于外部 isEnabledFor 调用）
    def isEnabledFor(self, level: Any) -> bool:  # pragma: no cover - 兼容性辅助
        """返回指定级别是否开启，兼容标准 logging API。"""

        def _normalize_level_name(value: Any) -> str:
            if isinstance(value, str):
                return value.upper()
            if isinstance(value, int):
                if value >= logging.CRITICAL:
                    return "CRITICAL"
                if value >= logging.ERROR:
                    return "ERROR"
                if value >= logging.WARNING:
                    return "WARNING"
                if value >= logging.INFO:
                    return "INFO"
                if value >= logging.DEBUG:
                    return "DEBUG"
                return "TRACE"
            try:
                return str(value).upper()
            except Exception:
                return "INFO"

        # 优先使用底层 logger 的同名方法
        if hasattr(self._logger, "isEnabledFor"):
            try:
                if isinstance(level, str):
                    return bool(
                        self._logger.isEnabledFor(getattr(logging, level.upper(), logging.INFO))
                    )
                if isinstance(level, int):
                    return bool(self._logger.isEnabledFor(level))
                return bool(
                    self._logger.isEnabledFor(
                        getattr(logging, _normalize_level_name(level), logging.INFO)
                    )
                )
            except Exception:
                pass

        # 兼容 loguru 的 is_enabled
        if hasattr(self._logger, "is_enabled"):
            try:
                return bool(self._logger.is_enabled(_normalize_level_name(level)))
            except Exception:
                pass
        if hasattr(self._logger, "_core") and hasattr(self._logger, "level"):
            try:
                min_level = getattr(getattr(self._logger, "_core", None), "min_level", None)
                if not isinstance(min_level, int):
                    raise TypeError("min_level")
                if isinstance(level, int):
                    return level >= min_level
                level_name = _normalize_level_name(level)
                level_no = None
                try:
                    level_no = self._logger.level(level_name).no
                except Exception:
                    level_no = getattr(logging, level_name, None)
                if isinstance(level_no, int):
                    return level_no >= min_level
            except Exception:
                pass

        # 最后兜底为 True，避免业务代码因缺少方法而异常
        return True


class _InterceptHandler(logging.Handler):
    """把标准 logging 流量引导到 loguru，保证日志口径统一"""

    def emit(self, record: logging.LogRecord) -> None:
        if not HAS_LOGURU:
            return

        try:
            level = loguru_logger.level(record.levelname).name
        except Exception:
            level = record.levelno

        frame, depth = logging.currentframe(), 0
        while frame:
            filename = frame.f_code.co_filename
            is_logging = filename == logging.__file__
            is_frozen = "importlib" in filename and "_bootstrap" in filename
            if depth > 0 and not (is_logging or is_frozen):
                break
            frame = frame.f_back
            depth += 1

        try:
            message = record.getMessage()
        except Exception:
            msg = getattr(record, "msg", "")
            message = str(msg) if msg is not None else ""

        target = _loguru_base or loguru_logger
        target.bind(logger_name=record.name).opt(depth=depth, exception=record.exc_info).log(
            level, message
        )


class _ContextInjectFilter(logging.Filter):
    """为标准 logging 路径注入 context_str，避免格式化 KeyError。"""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            context = LOG_CONTEXT.get({})
        except Exception:
            context = {}
        if not isinstance(context, dict):
            context = {}
        record.context_str = _format_context(context)
        return True


def _ensure_context_filter() -> None:
    root = logging.getLogger()
    try:
        if any(isinstance(f, _ContextInjectFilter) for f in getattr(root, "filters", [])):
            return
    except Exception:
        pass
    root.addFilter(_ContextInjectFilter())


def _format_context(context: Dict[str, Any]) -> str:
    if not context:
        return ""
    try:
        return " ".join(f"{k}={v}" for k, v in context.items())
    except Exception:
        return ""


def _inject_context(record: Dict[str, Any]) -> Dict[str, Any]:
    context = LOG_CONTEXT.get({})
    extra = record.get("extra")
    if not isinstance(extra, dict):
        extra = {}
    extra.setdefault("context", context if isinstance(context, dict) else {})
    extra.setdefault("context_str", _format_context(extra["context"]))
    extra.setdefault("logger_name", extra.get("logger_name") or record.get("name") or "mintchat")
    record["extra"] = extra
    return record


def _normalize_drop_keywords(keywords: List[str]) -> List[str]:
    try:
        return [str(kw).strip().lower() for kw in keywords if str(kw).strip()]
    except Exception:
        return []


def _should_drop(message: str, keywords: List[str]) -> bool:
    if not message or not keywords:
        return False
    try:
        lower_msg = message.lower()
        for kw in keywords:
            if kw and kw in lower_msg:
                return True
    except Exception:
        return False
    return False


def _parse_rotation_bytes(rotation: str) -> int:
    """仅用于标准 logging 轮转的简易解析"""
    try:
        value, unit = rotation.split()
        value = float(value)
        unit = unit.lower()
        if unit.startswith("kb"):
            return int(value * 1024)
        if unit.startswith("mb"):
            return int(value * 1024 * 1024)
        if unit.startswith("gb"):
            return int(value * 1024 * 1024 * 1024)
    except Exception:
        pass
    return 10 * 1024 * 1024


def _merge_config(config: Optional[LoggerConfig], overrides: Dict[str, Any]) -> LoggerConfig:
    base = config or _current_config or LoggerConfig()
    merged = {**base.__dict__, **{k: v for k, v in overrides.items() if v is not None}}
    merged["log_dir"] = Path(merged["log_dir"])
    merged["level"] = str(merged["level"]).upper()
    merged["quiet_level"] = str(merged.get("quiet_level", DEFAULT_QUIET_LEVEL)).upper()
    # 防止覆盖 quiet_libs 为空导致失效
    if "quiet_libs" in overrides and overrides["quiet_libs"] is not None:
        merged["quiet_libs"] = list(overrides["quiet_libs"])
    if "drop_keywords" in overrides and overrides["drop_keywords"] is not None:
        merged["drop_keywords"] = list(overrides["drop_keywords"])
    return LoggerConfig(**merged)


def _ensure_utf8_stdio() -> None:
    """
    尝试将标准输出/错误编码设置为 UTF-8，避免中文变问号。
    仅在支持 reconfigure 的环境生效。
    """
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                # 如果不支持则忽略，避免启动失败
                pass


class _FilteringTextStream:
    """A minimal text stream wrapper that drops noisy lines by keyword.

    This is used to suppress third-party *print* noise (e.g. ModelScope download
    messages) which bypasses our logging pipeline and therefore cannot be
    filtered by loguru sinks.
    """

    __slots__ = ("_stream", "_drop_keywords", "_buffer")

    def __init__(self, stream: IO[str], drop_keywords: List[str]) -> None:
        self._stream = stream
        self._drop_keywords = list(drop_keywords or [])
        self._buffer = ""

    def write(self, s: str) -> int:  # pragma: no cover - exercised indirectly via GUI
        try:
            text = str(s)
        except Exception:
            text = ""
        if not text:
            return 0

        self._buffer += text
        written = 0

        while True:
            if "\n" not in self._buffer and "\r" not in self._buffer:
                break

            # Handle both newline and carriage-return style progress outputs.
            n_idx = self._buffer.find("\n")
            r_idx = self._buffer.find("\r")
            idx_candidates = [i for i in (n_idx, r_idx) if i >= 0]
            if not idx_candidates:
                break
            idx = min(idx_candidates)
            line = self._buffer[: idx + 1]
            self._buffer = self._buffer[idx + 1 :]

            stripped = line.strip()
            if stripped and _should_drop(stripped, self._drop_keywords):
                continue
            try:
                written += int(self._stream.write(line))
            except Exception:
                # Best-effort: don't break the app on logging issues.
                pass
        return int(written)

    def flush(self) -> None:  # pragma: no cover - trivial
        try:
            if self._buffer:
                stripped = self._buffer.strip()
                if stripped and not _should_drop(stripped, self._drop_keywords):
                    try:
                        self._stream.write(self._buffer)
                    except Exception:
                        pass
                self._buffer = ""
        finally:
            try:
                self._stream.flush()
            except Exception:
                pass

    def isatty(self) -> bool:  # pragma: no cover - passthrough
        try:
            return bool(self._stream.isatty())
        except Exception:
            return False

    def fileno(self) -> int:  # pragma: no cover - passthrough
        try:
            return int(self._stream.fileno())
        except Exception:
            return -1

    @property
    def encoding(self) -> str:  # pragma: no cover - passthrough
        return getattr(self._stream, "encoding", "utf-8")


def _install_stdio_drop_filter(drop_keywords: List[str]) -> None:
    if not _env_flag("MINTCHAT_LOG_FILTER_STDIO", True):
        return
    try:
        if not isinstance(sys.stdout, _FilteringTextStream):
            sys.stdout = _FilteringTextStream(
                _ORIG_STDOUT, drop_keywords
            )  # type: ignore[assignment]
    except Exception:
        pass
    try:
        if not isinstance(sys.stderr, _FilteringTextStream):
            sys.stderr = _FilteringTextStream(
                _ORIG_STDERR, drop_keywords
            )  # type: ignore[assignment]
    except Exception:
        pass


def setup_logger(config: Optional[LoggerConfig] = None, **overrides: Any) -> _LegacyLoggerAdapter:
    """
    初始化/重置日志系统，可重复调用以应用新配置
    """
    global _loguru_base, _current_config

    cfg = _merge_config(config, overrides)
    _current_config = cfg
    cfg.log_dir.mkdir(parents=True, exist_ok=True)
    _ensure_utf8_stdio()
    drop_keywords = _normalize_drop_keywords(cfg.drop_keywords)

    if HAS_LOGURU:
        loguru_logger.remove()
        # 关键修复：确保即使第三方库直接使用 loguru.logger 也能拿到默认 extra 字段，
        # 否则 format 中的 {extra[logger_name]} 会触发 KeyError。
        try:
            loguru_logger.configure(patcher=_inject_context)
            _loguru_base = loguru_logger.bind(app="MintChat", **cfg.extra)
        except Exception:
            _loguru_base = loguru_logger.bind(app="MintChat", **cfg.extra).patch(_inject_context)

        _loguru_base.add(
            _ORIG_STDERR,
            level=cfg.normalized_level(),
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{extra[logger_name]}</cyan> | "
                "<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                "<level>{message}</level> {extra[context_str]}"
            ),
            colorize=cfg.colorize,
            enqueue=cfg.enqueue,
            backtrace=cfg.backtrace,
            diagnose=cfg.diagnose,
            filter=lambda record, kws=drop_keywords: not _should_drop(
                record.get("message", ""), kws
            ),
        )

        _loguru_base.add(
            cfg.log_dir / cfg.log_file,
            level=cfg.normalized_level(),
            format=(
                "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
                "{extra[logger_name]} | {function}:{line} | {message} {extra[context_str]}"
            ),
            rotation=cfg.rotation,
            retention=cfg.retention,
            encoding="utf-8",
            enqueue=cfg.enqueue,
            backtrace=cfg.backtrace,
            diagnose=cfg.diagnose,
            filter=lambda record, kws=drop_keywords: not _should_drop(
                record.get("message", ""), kws
            ),
        )

        if cfg.enable_json:
            _loguru_base.add(
                cfg.log_dir / cfg.json_file,
                level=cfg.normalized_level(),
                rotation=cfg.rotation,
                retention=cfg.retention,
                encoding="utf-8",
                enqueue=cfg.enqueue,
                serialize=True,
                filter=lambda record, kws=drop_keywords: not _should_drop(
                    record.get("message", ""), kws
                ),
            )

        logging.basicConfig(
            handlers=[_InterceptHandler()],
            level=getattr(logging, cfg.normalized_level(), logging.INFO),
            force=True,
        )
        if cfg.capture_warnings:
            logging.captureWarnings(True)
            _configure_warning_filters()

        set_library_log_levels({name: cfg.quiet_level for name in cfg.quiet_libs})
        _install_stdio_drop_filter(drop_keywords)
        return _LegacyLoggerAdapter(_loguru_base.bind(logger_name="mintchat"))

    numeric_level = getattr(logging, cfg.normalized_level(), logging.INFO)
    _ensure_context_filter()
    logging.basicConfig(
        level=numeric_level,
        format=(
            "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | "
            "%(message)s %(context_str)s"
        ),
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(_ORIG_STDERR)],
        force=True,
    )

    file_handler = RotatingFileHandler(
        cfg.log_dir / cfg.log_file,
        maxBytes=_parse_rotation_bytes(cfg.rotation),
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(
        logging.Formatter(
            (
                "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | "
                "%(message)s %(context_str)s"
            ),
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    class _DropFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            return not _should_drop(getattr(record, "msg", ""), drop_keywords)

    drop_filter = _DropFilter()
    for handler in logging.getLogger().handlers:
        handler.addFilter(drop_filter)
    file_handler.addFilter(drop_filter)
    logging.getLogger().addHandler(file_handler)
    set_library_log_levels({name: cfg.quiet_level for name in cfg.quiet_libs})
    _install_stdio_drop_filter(drop_keywords)
    return _LegacyLoggerAdapter(logging.getLogger("mintchat"))


def apply_settings(settings: Any) -> None:
    """根据 Settings 实例动态刷新日志配置"""
    try:
        # 默认使用内置 quiet/drop 规则；用户配置为空列表时不要覆盖为“关闭过滤”。如果需要完全关闭，
        # 请用环境变量（例如：MINTCHAT_LOG_FILTER_STDIO=0）或显式提高 log_level。
        quiet_libs = getattr(settings, "log_quiet_libs", None)
        if not isinstance(quiet_libs, list) or not quiet_libs:
            quiet_libs = DEFAULT_QUIET_LIBS

        user_drop_keywords = getattr(settings, "log_drop_keywords", None)
        if isinstance(user_drop_keywords, list) and user_drop_keywords:
            drop_keywords = list(DEFAULT_DROP_KEYWORDS) + list(user_drop_keywords)
        else:
            drop_keywords = DEFAULT_DROP_KEYWORDS

        setup_logger(
            level=getattr(settings, "log_level", DEFAULT_LEVEL),
            log_dir=Path(getattr(settings, "log_dir", DEFAULT_LOG_DIR)),
            rotation=getattr(settings, "log_rotation", DEFAULT_ROTATION),
            retention=getattr(settings, "log_retention", DEFAULT_RETENTION),
            enable_json=getattr(settings, "log_json", True),
            quiet_libs=quiet_libs,
            quiet_level=getattr(settings, "log_quiet_level", DEFAULT_QUIET_LEVEL),
            drop_keywords=drop_keywords,
        )
    except Exception as exc:
        logging.warning(f"应用日志配置失败，使用默认日志: {exc}")


def set_log_level(level: str) -> None:
    """运行时调整日志级别"""
    setup_logger(level=level)


def set_library_log_levels(level_map: Dict[str, str], default_level: Optional[str] = None) -> None:
    """
    批量设置第三方库日志级别，减少噪声

    Args:
        level_map: 名称 -> 级别 映射
        default_level: 未在映射中的默认级别（可选）
    """
    for name, level in level_map.items():
        try:
            logging.getLogger(name).setLevel(level)
        except Exception:
            continue
    if default_level:
        logging.getLogger().setLevel(default_level)


def bind_context(**kwargs: Any) -> None:
    """绑定全局上下文，适用于跨线程/协程"""
    current = LOG_CONTEXT.get({})
    updated = current.copy()
    updated.update(kwargs)
    LOG_CONTEXT.set(updated)


@contextmanager
def log_context(**kwargs: Any):
    """上下文管理器版的 bind_context"""
    token = LOG_CONTEXT.set({**LOG_CONTEXT.get({}), **kwargs})
    try:
        yield
    finally:
        LOG_CONTEXT.reset(token)


def clear_context() -> None:
    """清理已绑定的上下文"""
    LOG_CONTEXT.set({})


def get_logger(name: str) -> Any:
    """获取带模块名的 logger"""
    if HAS_LOGURU and _loguru_base is not None:
        return _LegacyLoggerAdapter(_loguru_base.bind(logger_name=name))
    if HAS_LOGURU:
        base = loguru_logger.bind(logger_name=name).patch(_inject_context)
        return _LegacyLoggerAdapter(base)
    return logging.getLogger(name)


# 初始化默认日志，确保早期导入也有输出
logger = setup_logger()
