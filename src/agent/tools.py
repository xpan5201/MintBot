"""
工具系统模块：注册与执行基础工具（时间、计算、文件、搜索等）。

目标：
- 精简重复逻辑：统一路径验证、表达式校验、线程池复用。
- 提升性能：重用线程池执行工具，减少频繁创建/销毁开销。
- 提升可维护性：集中常量与验证帮助函数，降低重复代码。
"""

import asyncio
import ast
import contextvars
import logging
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from datetime import datetime
from functools import wraps
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    # LangChain < 0.2
    from langchain.tools import tool  # type: ignore
except Exception:  # pragma: no cover - 兼容不同 LangChain 版本
    try:
        # LangChain >= 0.2（工具在 langchain_core）
        from langchain_core.tools import tool  # type: ignore
    except Exception:  # pragma: no cover - 环境依赖差异
        # 允许在缺少 LangChain 的环境下导入本模块（例如仅运行部分测试/工具）
        def tool(func: Callable) -> Callable:  # type: ignore[misc]
            return func

from src.config.settings import settings
from src.utils.logger import get_logger
from src.utils.exceptions import ValidationError, ResourceError
from src.utils.tool_context import tool_timeout_s_var

logger = get_logger(__name__)

# 允许的计算字符集合（减少重复构造）
ALLOWED_EXPR_CHARS = set("0123456789+-*/()., ")
# 文件读写的统一大小限制
MAX_READ_BYTES = 1 * 1024 * 1024  # 1MB
MAX_WRITE_BYTES = 10 * 1024 * 1024  # 10MB
# list_files 输出条目上限，避免超大目录阻塞
LIST_FILES_LIMIT = 200
# 工具执行默认超时（秒）
DEFAULT_TOOL_TIMEOUT = max(0.1, float(getattr(settings.agent, "tool_timeout_s", 30.0)))
# 工具线程池大小（可通过配置覆盖）
DEFAULT_TOOL_WORKERS = max(1, int(getattr(settings.agent, "tool_executor_workers", 4)))
# 防御型限制：防止单次调用过大输入导致内存放大
DEFAULT_TOOL_MAX_ARGS_LEN = 2000

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SENSITIVE_FILENAMES = {
    "config.yaml",
    ".env",
    ".env.local",
    ".env.development",
    ".env.production",
}
_SENSITIVE_DIRNAMES = {".git", ".hg", ".svn"}


def _is_sensitive_path(path: Path) -> bool:
    try:
        parts_lower = {p.lower() for p in path.parts}
    except Exception:
        parts_lower = set()
    if parts_lower.intersection(_SENSITIVE_DIRNAMES):
        return True
    try:
        name = path.name.lower()
    except Exception:
        return False
    if name in _SENSITIVE_FILENAMES:
        return True
    if name.startswith(".env."):
        return True
    return False


_SAFE_TITLE_RE = re.compile(r"[^0-9a-zA-Z\u4e00-\u9fff _.-]+")


def _sanitize_note_title(value: str, *, max_len: int = 60) -> str:
    title = (value or "").strip()
    title = _SAFE_TITLE_RE.sub("_", title)
    title = re.sub(r"_+", "_", title).strip(" ._")
    if not title:
        title = "note"
    return title[:max_len]


def _safe_eval_math_expression(expression: str) -> object:
    """
    安全计算数学表达式（替代 eval），避免大整数/幂运算导致的 DoS 风险。
    仅允许：数字常量、括号、+ - * / // 以及逗号生成 tuple。
    """
    if "**" in expression:
        raise ValueError("表达式包含不允许的运算符: **")

    node = ast.parse(expression, mode="eval")

    max_nodes = 100
    visited = 0
    max_abs_int = 10**50

    def ensure_safe_number(value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("不支持 bool")
        if isinstance(value, int):
            if abs(value) > max_abs_int:
                raise OverflowError("整数过大")
            return value
        if isinstance(value, float):
            if not math.isfinite(value):
                raise OverflowError("浮点数溢出")
            return value
        return value

    def walk(n: ast.AST) -> object:
        nonlocal visited
        visited += 1
        if visited > max_nodes:
            raise ValueError("表达式过于复杂")

        if isinstance(n, ast.Expression):
            return walk(n.body)

        if isinstance(n, ast.Constant):
            if isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
                return ensure_safe_number(n.value)
            raise ValueError("仅支持数字常量")

        if isinstance(n, ast.Tuple):
            return tuple(walk(elt) for elt in n.elts)

        if isinstance(n, ast.UnaryOp):
            operand = walk(n.operand)
            if not isinstance(operand, (int, float)):
                raise ValueError("一元运算仅支持数字")
            if isinstance(n.op, ast.UAdd):
                return ensure_safe_number(+operand)
            if isinstance(n.op, ast.USub):
                return ensure_safe_number(-operand)
            raise ValueError("不支持的一元运算")

        if isinstance(n, ast.BinOp):
            left = walk(n.left)
            right = walk(n.right)
            if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
                raise ValueError("二元运算仅支持数字")

            if isinstance(n.op, ast.Add):
                return ensure_safe_number(left + right)
            if isinstance(n.op, ast.Sub):
                return ensure_safe_number(left - right)
            if isinstance(n.op, ast.Mult):
                return ensure_safe_number(left * right)
            if isinstance(n.op, ast.Div):
                return ensure_safe_number(left / right)
            if isinstance(n.op, ast.FloorDiv):
                return ensure_safe_number(left // right)
            raise ValueError("不支持的运算符")

        raise ValueError("表达式包含不允许的语法")

    return walk(node)


@dataclass
class ToolStats:
    calls: int = 0
    successes: int = 0
    failures: int = 0
    total_time: float = 0.0
    last_error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        avg = self.total_time / self.calls if self.calls else 0.0
        return {
            "calls": self.calls,
            "successes": self.successes,
            "failures": self.failures,
            "avg_time": round(avg, 4),
            "last_error": self.last_error,
        }


# ==================== 工具装饰器 ====================
def tool_with_retry(max_retries: int = 2, retry_delay: float = 0.5):
    """
    工具重试装饰器 - v2.30.14 新增

    Args:
        max_retries: 最大重试次数
        retry_delay: 重试延迟（秒）
    """
    def decorator(func: Callable) -> Callable:
        tool_name = getattr(func, "name", None) or getattr(func, "__name__", None) or func.__class__.__name__

        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < max_retries:
                        logger.warning(
                            "工具 %s 执行失败，%.2f秒后重试 (%d/%d): %s",
                            tool_name,
                            retry_delay,
                            attempt + 1,
                            max_retries,
                            e,
                        )
                        time.sleep(retry_delay)
                    else:
                        logger.error("工具 %s 执行失败，已达最大重试次数: %s", tool_name, e)

            # 所有重试都失败，返回友好错误消息
            return f"抱歉主人，操作失败了喵~ 错误: {str(last_error)}"
        return wrapper
    return decorator


def _is_kwargs_too_large(kwargs: Dict[str, Any], max_chars: int, *, max_depth: int = 2) -> bool:
    """
    防御型参数大小估算：
    - 避免对超大参数直接 `repr()` 造成巨大临时字符串与内存放大
    - 只做“足够保守”的近似判断，超限则拒绝执行
    """
    if max_chars <= 0:
        return False

    total = 0
    seen: set[int] = set()
    stack: list[tuple[Any, int]] = [(kwargs, 0)]
    while stack:
        obj, depth = stack.pop()
        oid = id(obj)
        if oid in seen:
            continue
        seen.add(oid)

        if obj is None:
            continue

        if isinstance(obj, str):
            total += len(obj)
        elif isinstance(obj, bytes):
            total += len(obj)
        elif isinstance(obj, (int, float, bool)):
            total += 8
        elif isinstance(obj, dict):
            total += len(obj) * 2
            if total > max_chars:
                return True
            if depth < max_depth:
                for k, v in obj.items():
                    stack.append((k, depth + 1))
                    stack.append((v, depth + 1))
        elif isinstance(obj, (list, tuple, set)):
            total += len(obj)
            if total > max_chars:
                return True
            if depth < max_depth:
                for item in obj:
                    stack.append((item, depth + 1))
        else:
            # 其他类型避免展开与字符串化，只记一个小常量
            total += 16

        if total > max_chars:
            return True

    return False


def validate_params(**validators):
    """
    参数验证装饰器 - v2.30.14 新增

    Args:
        **validators: 参数验证器字典，格式为 {param_name: validator_func}
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 验证参数
            for param_name, validator in validators.items():
                if param_name in kwargs:
                    value = kwargs[param_name]
                    try:
                        if not validator(value):
                            error_msg = f"参数 {param_name} 验证失败: {value}"
                            logger.error(error_msg)
                            return f"抱歉主人，参数不正确喵~ {error_msg}"
                    except Exception as e:
                        logger.error("参数验证出错: %s", e)
                        return f"抱歉主人，参数验证出错了喵~ {str(e)}"

            return func(*args, **kwargs)
        return wrapper
    return decorator


# ==================== 时间相关工具 ====================
@tool
def get_current_time() -> str:
    """
    获取当前时间

    Returns:
        str: 当前时间的字符串表示
    """
    now = datetime.now()
    return now.strftime("%Y年%m月%d日 %H:%M:%S")


@tool
def get_current_date() -> str:
    """
    获取当前日期

    Returns:
        str: 当前日期的字符串表示
    """
    today = datetime.now()
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    weekday = weekdays[today.weekday()]
    return f"{today.strftime('%Y年%m月%d日')} {weekday}"


# ==================== 计算器工具 ====================
@tool
@tool_with_retry(max_retries=1, retry_delay=0.1)
@validate_params(expression=lambda x: isinstance(x, str) and len(x) > 0 and len(x) < 200)
def calculator(expression: str) -> str:
    """
    计算数学表达式 - v2.30.14 增强版

    Args:
        expression: 数学表达式，如 "2 + 3 * 4"

    Returns:
        str: 计算结果

    v2.30.14 优化:
    - 添加参数验证（长度限制）
    - 增强安全性检查
    - 改进错误消息
    """
    try:
        # v2.30.14: 增强安全性检查
        # 只允许基本的数学运算
        if not all(c in ALLOWED_EXPR_CHARS for c in expression):
            return "抱歉主人，表达式包含不允许的字符喵~ 只能使用数字和 +-*/() 符号"

        # 防止过长的表达式
        if len(expression) > 200:
            return "抱歉主人，表达式太长了喵~ 请简化一下"

        # 安全的数学表达式求值（替代 eval，避免 DoS 风险）
        result = _safe_eval_math_expression(expression)
        logger.info("计算成功: %s = %s", expression, result)
        return f"计算结果：{result} 喵~"
    except ZeroDivisionError:
        logger.warning("除零错误: %s", expression)
        return "抱歉主人，不能除以零喵~"
    except (OverflowError, ValueError) as e:
        logger.warning("表达式不安全或超限: %s (%s)", expression, e)
        return f"抱歉主人，表达式不安全或超出限制喵~ 错误: {str(e)}"
    except SyntaxError:
        logger.warning("语法错误: %s", expression)
        return "抱歉主人，表达式格式不正确喵~"
    except Exception as e:
        logger.error("计算错误: %s", e)
        return f"抱歉主人，计算出错了喵~ 错误: {str(e)}"


# ==================== 天气工具（模拟） ====================
@tool
def get_weather(city: str) -> str:
    """
    获取指定城市的天气信息（模拟数据）

    Args:
        city: 城市名称

    Returns:
        str: 天气信息
    """
    # 这是一个模拟实现，实际使用时应该调用真实的天气 API
    weather_data = {
        "北京": "晴天，温度 15-25°C，空气质量良好",
        "上海": "多云，温度 18-26°C，有轻微雾霾",
        "广州": "阴天，温度 22-30°C，湿度较大",
        "深圳": "小雨，温度 20-28°C，建议携带雨具",
    }

    weather = weather_data.get(
        city,
        f"{city}的天气：晴朗，温度适宜，适合外出活动",
    )

    logger.info("查询天气: %s -> %s", city, weather)
    return weather


# ==================== 提醒工具 ====================
@tool
def set_reminder(content: str, time: str) -> str:
    """
    设置提醒

    Args:
        content: 提醒内容
        time: 提醒时间

    Returns:
        str: 设置结果
    """
    # 这是一个模拟实现，实际使用时应该集成真实的提醒系统
    logger.info("设置提醒: %s at %s", content, time)
    return f"好的主人，我会在 {time} 提醒您：{content} 喵~"


# ==================== 搜索工具（模拟） ====================
@tool
def web_search(query: str) -> str:
    """
    网络搜索（模拟）

    Args:
        query: 搜索查询

    Returns:
        str: 搜索结果摘要
    """
    # 这是一个模拟实现，实际使用时应该调用真实的搜索 API
    logger.info("网络搜索: %s", query)
    return f"关于'{query}'的搜索结果：这是一个模拟的搜索结果。实际使用时会调用真实的搜索引擎。"


# ==================== 笔记工具 ====================
@tool
def save_note(title: str, content: str) -> str:
    """
    保存笔记

    Args:
        title: 笔记标题
        content: 笔记内容

    Returns:
        str: 保存结果
    """
    try:
        content_size = len(content.encode("utf-8"))
        if content_size > MAX_WRITE_BYTES:
            return f"抱歉主人，笔记内容太大了（{content_size / 1024 / 1024:.2f}MB，超过10MB限制）喵~"

        # 创建笔记目录
        notes_dir = Path(settings.data_dir) / "notes"
        notes_dir.mkdir(parents=True, exist_ok=True)

        # 生成文件名（使用时间戳避免重复）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_title = _sanitize_note_title(title)
        filename = f"{timestamp}_{safe_title}.txt"
        filepath = notes_dir / filename

        # 保存笔记
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"标题: {title}\n")
            f.write(f"时间: {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}\n")
            f.write(f"{'-' * 50}\n")
            f.write(content)

        logger.info("保存笔记: %s -> %s", title, filepath)
        return f"主人，笔记《{title}》已经保存好了喵~ 保存在 {filepath}"
    except Exception as e:
        logger.error("保存笔记失败: %s", e)
        return f"抱歉主人，保存笔记时出错了: {str(e)} 喵~"


# 公共路径验证助手，统一安全与可读性
def _validate_path(
    path_str: str,
    *,
    must_exist: bool = False,
    must_be_file: bool = False,
    must_be_dir: bool = False,
    base_dir: Optional[Path] = None,
) -> Tuple[Optional[Path], Optional[str]]:
    if not path_str or not isinstance(path_str, str):
        return None, "文件路径无效"

    root = PROJECT_ROOT.resolve()
    base_raw = Path(".") if base_dir is None else base_dir
    if base_raw.is_absolute():
        base = base_raw.resolve()
    else:
        base = (root / base_raw).resolve()
    try:
        base.relative_to(root)
    except ValueError:
        return None, "抱歉主人，只能访问项目目录内的文件喵~"

    raw_path = Path(path_str)
    path = raw_path.resolve() if raw_path.is_absolute() else (base / raw_path).resolve()
    try:
        path.relative_to(base)
    except ValueError:
        return None, "抱歉主人，只能访问项目目录内的文件喵~"

    if _is_sensitive_path(path):
        return None, "抱歉主人，出于安全考虑，无法访问该文件喵~"

    if must_exist and not path.exists():
        return None, f"主人，文件 {path_str} 不存在喵~"
    if must_be_file and path.exists() and not path.is_file():
        return None, f"主人，{path_str} 不是一个文件喵~"
    if must_be_dir and path.exists() and not path.is_dir():
        return None, f"主人，{path_str} 不是一个目录喵~"
    return path, None


# ==================== 文件操作工具 (v2.30.14 增强版) ====================
@tool
@tool_with_retry(max_retries=2, retry_delay=0.5)
@validate_params(filepath=lambda x: isinstance(x, str) and len(x) > 0)
def read_file(filepath: str, base_dir: str = ".") -> str:
    """
    读取文件内容 - v2.30.14 增强版

    Args:
        filepath: 文件路径

    Returns:
        str: 文件内容或错误信息

    v2.30.14 优化:
    - 添加重试机制
    - 增强路径验证
    - 支持多种编码
    - 改进错误处理
    """
    try:
        path, err = _validate_path(filepath, must_exist=True, must_be_file=True, base_dir=Path(base_dir))
        if err:
            logger.warning(err)
            return err

        file_size = path.stat().st_size
        if file_size > MAX_READ_BYTES:
            return f"主人，文件太大了（{file_size / 1024 / 1024:.2f}MB，超过1MB限制），我读不了喵~"

        # v2.30.14: 尝试多种编码
        encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
        content = None
        used_encoding = None

        for encoding in encodings:
            try:
                with open(path, "r", encoding=encoding) as f:
                    content = f.read()
                used_encoding = encoding
                break
            except UnicodeDecodeError:
                continue

        if content is None:
            return "抱歉主人，文件编码不支持，无法读取喵~"

        logger.info(
            "读取文件成功: %s (编码: %s, 大小: %d bytes)",
            filepath,
            used_encoding,
            file_size,
        )
        return f"文件内容（编码: {used_encoding}）：\n{content}"

    except ValidationError as e:
        logger.error("参数验证失败: %s", e)
        return f"抱歉主人，{e.message} 喵~"
    except PermissionError:
        logger.error("权限不足: %s", filepath)
        return f"抱歉主人，没有权限读取文件 {filepath} 喵~"
    except Exception as e:
        logger.error("读取文件失败: %s", e)
        return f"抱歉主人，读取文件时出错了: {str(e)} 喵~"


@tool
@tool_with_retry(max_retries=2, retry_delay=0.5)
@validate_params(
    filepath=lambda x: isinstance(x, str) and len(x) > 0,
    content=lambda x: isinstance(x, str)
)
def write_file(filepath: str, content: str, base_dir: str = ".") -> str:
    """
    写入文件 - v2.30.14 增强版

    Args:
        filepath: 文件路径
        content: 文件内容

    Returns:
        str: 操作结果

    v2.30.14 优化:
    - 添加重试机制
    - 增强路径验证
    - 添加内容大小限制
    - 改进错误处理
    """
    try:
        path, err = _validate_path(filepath, must_exist=False, must_be_file=True, base_dir=Path(base_dir))
        if err:
            logger.warning(err)
            return err

        content_size = len(content.encode('utf-8'))
        if content_size > MAX_WRITE_BYTES:
            return f"抱歉主人，内容太大了（{content_size / 1024 / 1024:.2f}MB，超过10MB限制）喵~"

        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info("写入文件成功: %s (大小: %d bytes)", filepath, content_size)
        return f"主人，文件已经写入到 {filepath} 了喵~ (大小: {content_size} bytes)"

    except ValidationError as e:
        logger.error("参数验证失败: %s", e)
        return f"抱歉主人，{e.message} 喵~"
    except PermissionError:
        logger.error("权限不足: %s", filepath)
        return f"抱歉主人，没有权限写入文件 {filepath} 喵~"
    except Exception as e:
        logger.error("写入文件失败: %s", e)
        return f"抱歉主人，写入文件时出错了: {str(e)} 喵~"


@tool
def list_files(directory: str = ".", base_dir: str = ".") -> str:
    """
    列出目录中的文件

    Args:
        directory: 目录路径

    Returns:
        str: 文件列表
    """
    try:
        path, err = _validate_path(directory, must_exist=True, must_be_dir=True, base_dir=Path(base_dir))
        if err:
            logger.warning(err)
            return err

        files = []
        dirs = []

        for idx, item in enumerate(path.iterdir()):
            if idx >= LIST_FILES_LIMIT:
                break
            if _is_sensitive_path(item):
                continue
            if item.is_file():
                try:
                    size = item.stat().st_size
                except OSError:
                    size = 0
                files.append(f"📄 {item.name} ({size} bytes)")
            elif item.is_dir():
                dirs.append(f"📁 {item.name}/")

        result = f"目录 {directory} 的内容：\n\n"
        if dirs:
            result += "目录：\n" + "\n".join(dirs) + "\n\n"
        if files:
            result += "文件：\n" + "\n".join(files)

        if not dirs and not files:
            result += "（空目录）"

        logger.info("列出目录: %s", directory)
        return result
    except Exception as e:
        logger.error("列出目录失败: %s", e)
        return f"抱歉主人，列出目录时出错了: {str(e)} 喵~"


class ToolRegistry:
    """工具注册表"""

    def __init__(self):
        """初始化工具注册表"""
        self._tools_enabled = bool(getattr(settings.agent, "enable_tools", True))
        self._tools: Dict[str, Callable] = {}
        self._stats: Dict[str, ToolStats] = {}
        self._lock = Lock()
        # MCP 工具（可选）单独保留列表，便于诊断/兼容脚本
        self._mcp_tools: List[Callable] = []
        self._optional_tools_loaded = False
        self._optional_tools_lock = Lock()
        self._executor: Optional[ThreadPoolExecutor] = None
        self._executor_lock = Lock()
        if self._tools_enabled:
            self._register_default_tools()
        else:
            logger.info("工具系统已在配置中禁用，将不注册任何工具")
        logger.info("工具注册表初始化完成")

    @staticmethod
    def _get_tool_name(tool_fn: Callable) -> str:
        """安全获取工具名称，兼容 LangChain StructuredTool 等对象"""
        return getattr(tool_fn, "name", None) or getattr(tool_fn, "__name__", None) or tool_fn.__class__.__name__

    def _get_executor(self) -> ThreadPoolExecutor:
        executor = self._executor
        if executor is not None:
            return executor

        with self._executor_lock:
            if self._executor is None:
                self._executor = ThreadPoolExecutor(
                    max_workers=DEFAULT_TOOL_WORKERS,
                    thread_name_prefix="mintchat-tool",
                )
            return self._executor

    def _run_with_timeout(self, func: Callable[[], Any], timeout: float) -> Any:
        """在线程池中执行并支持超时控制的帮助函数。"""
        # contextvars 默认不跨线程传播；这里显式 copy_context() 以便工具实现读取超时等上下文
        ctx = contextvars.copy_context()
        future = self._get_executor().submit(ctx.run, func)
        try:
            return future.result(timeout=timeout)
        except FuturesTimeoutError:
            future.cancel()
            raise

    def _register_tools(self, tools: List[Tuple[str, Callable]]) -> None:
        for name, fn in tools:
            self.register_tool(name, fn)

    def _register_default_tools(self) -> None:
        """注册默认工具（轻量、无外部依赖）。"""
        defaults: List[Tuple[str, Callable]] = [
            ("get_current_time", get_current_time),
            ("get_current_date", get_current_date),
            ("calculator", calculator),
            ("get_weather", get_weather),
            ("web_search", web_search),
            ("set_reminder", set_reminder),
            ("save_note", save_note),
            ("read_file", read_file),
            ("write_file", write_file),
            ("list_files", list_files),
        ]
        self._register_tools(defaults)

    def _ensure_optional_tools_loaded(self) -> None:
        """
        延迟加载可选工具（builtin_tools/MCP）。

        设计目标：
        - 避免 import 时就加载 aiohttp/bs4 或启动 MCP server 造成启动变慢
        - 仅在真正需要 tools 列表/执行工具时加载一次
        """
        if not self._tools_enabled:
            return
        if self._optional_tools_loaded:
            return

        with self._optional_tools_lock:
            if self._optional_tools_loaded:
                return

            # 1) 注册内置高级工具（Bing/高德等），避免重复
            if bool(getattr(settings.agent, "enable_builtin_tools", True)):
                try:
                    from src.agent.builtin_tools import get_builtin_tools

                    builtin = get_builtin_tools()
                    if builtin:
                        for tool_fn in builtin:
                            tool_name = self._get_tool_name(tool_fn)
                            with self._lock:
                                exists = tool_name in self._tools
                            if exists:
                                logger.debug("跳过重复工具: %s", tool_name)
                                continue
                            self.register_tool(tool_name, tool_fn)
                        logger.info("已注册内置高级工具 %d 个", len(builtin))
                except Exception as e:
                    logger.warning("内置高级工具注册失败: %s", e)

            # 2) 注册 MCP 工具（Model Context Protocol，可选）
            if bool(getattr(settings.agent, "enable_mcp_tools", True)):
                cfg = getattr(settings, "mcp", None)
                servers = getattr(cfg, "servers", None) if cfg else None
                if not cfg or not getattr(cfg, "enabled", False) or not servers:
                    self._mcp_tools = []
                else:
                    try:
                        from src.agent.mcp_manager import mcp_manager

                        mcp_tools = mcp_manager.get_tools()
                        self._mcp_tools = list(mcp_tools)
                        if mcp_tools:
                            for tool_fn in mcp_tools:
                                tool_name = self._get_tool_name(tool_fn)
                                with self._lock:
                                    exists = tool_name in self._tools
                                if exists:
                                    logger.debug("跳过重复工具: %s", tool_name)
                                    continue
                                self.register_tool(tool_name, tool_fn)
                            logger.info("已注册 MCP 工具 %d 个", len(mcp_tools))
                    except Exception as e:
                        self._mcp_tools = []
                        logger.warning("MCP 工具注册失败: %s", e)

            self._optional_tools_loaded = True

    def register_tool(self, name: str, tool_func: Callable) -> None:
        """
        注册工具

        Args:
            name: 工具名称
            tool_func: 工具函数
        """
        with self._lock:
            self._tools[name] = tool_func
            if name not in self._stats:
                self._stats[name] = ToolStats()
        logger.debug("注册工具: %s", name)

    def unregister_tool(self, name: str) -> None:
        """
        注销工具

        Args:
            name: 工具名称
        """
        with self._lock:
            if name in self._tools:
                del self._tools[name]
                logger.debug("注销工具: %s", name)

    def get_tool(self, name: str) -> Optional[Callable]:
        """
        获取工具

        Args:
            name: 工具名称

        Returns:
            Optional[Callable]: 工具函数，如果不存在则返回 None
        """
        if not self._tools_enabled:
            return None
        self._ensure_optional_tools_loaded()
        with self._lock:
            return self._tools.get(name)

    def get_all_tools(self) -> List[Callable]:
        """
        获取所有工具（包括 MCP 工具）

        Returns:
            List[Callable]: 工具函数列表
        """
        if not self._tools_enabled:
            return []
        self._ensure_optional_tools_loaded()
        with self._lock:
            return list(self._tools.values())

    def get_tool_names(self) -> List[str]:
        """
        获取所有工具名称

        Returns:
            List[str]: 工具名称列表
        """
        if not self._tools_enabled:
            return []
        self._ensure_optional_tools_loaded()
        with self._lock:
            return sorted(self._tools.keys())

    def get_tools_description(self) -> List[Dict[str, str]]:
        """
        获取所有工具的描述

        Returns:
            List[Dict[str, str]]: 工具描述列表
        """
        if not self._tools_enabled:
            return []
        self._ensure_optional_tools_loaded()
        with self._lock:
            items = list(self._tools.items())
        return [
            {
                "name": name,
                "description": getattr(tool_func, "description", None) or tool_func.__doc__ or "无描述",
            }
            for name, tool_func in items
        ]

    def execute_tool(self, name: str, timeout: float = DEFAULT_TOOL_TIMEOUT, **kwargs: Any) -> str:
        """
        v3.3.4: 执行工具 - 增强版（实际超时控制）

        Args:
            name: 工具名称
            timeout: 超时时间（秒），默认30秒
            **kwargs: 工具参数

        Returns:
            str: 执行结果

        v3.3.4 优化:
        - 实现真正的超时控制（使用 concurrent.futures）
        - 增强错误处理（改进空错误信息处理）
        - 改进日志记录
        - 添加执行时间统计
        """
        if not self._tools_enabled:
            return "工具系统已禁用"
        self._ensure_optional_tools_loaded()
        with self._lock:
            tool_func = self._tools.get(name)
            stats = self._stats.setdefault(name, ToolStats()) if tool_func is not None else None

        if tool_func is None:
            error_msg = f"工具 '{name}' 不存在"
            logger.error(error_msg)
            return error_msg

        # 输入防御：限制参数整体大小，避免劣质输入导致内存放大
        if _is_kwargs_too_large(kwargs, DEFAULT_TOOL_MAX_ARGS_LEN):
            msg = f"工具 '{name}' 参数过长，已拒绝执行"
            logger.warning(msg)
            with self._lock:
                stats.calls += 1
                stats.failures += 1
                stats.last_error = msg
            return "抱歉主人，工具参数过长，执行已被安全拒绝喵~"

        args_repr = "<suppressed>"
        if logger.isEnabledFor(logging.DEBUG):
            try:
                import reprlib

                args_repr = reprlib.repr(kwargs)
            except Exception:
                args_repr = "<unavailable>"

        start_time = time.time()

        try:
            logger.debug("开始执行工具 '%s'，参数: %s", name, args_repr)

            def _execute():
                # LangChain 工具需要使用 invoke 方法
                if hasattr(tool_func, 'invoke'):
                    return tool_func.invoke(kwargs) if kwargs else tool_func.invoke({})
                else:
                    return tool_func(**kwargs)

            token = tool_timeout_s_var.set(float(timeout))
            try:
                result = self._run_with_timeout(_execute, timeout)
            except (FuturesTimeoutError, asyncio.TimeoutError):
                timeout_msg = f"工具 '{name}' 执行超时（{timeout}秒）"
                with self._lock:
                    stats.calls += 1
                    stats.failures += 1
                    stats.last_error = timeout_msg
                execution_time = time.time() - start_time
                logger.error("工具 '%s' 执行超时（%.2f秒）", name, timeout)
                return f"抱歉主人，工具 '{name}' 执行超时了（超过 {timeout} 秒）喵~"
            finally:
                tool_timeout_s_var.reset(token)

            execution_time = time.time() - start_time
            logger.info("工具 '%s' 执行成功，耗时: %.2f秒", name, execution_time)
            with self._lock:
                stats.calls += 1
                stats.successes += 1
                stats.total_time += execution_time

            # v3.3.4: 检查执行时间（虽然已经超时控制，但记录警告）
            if execution_time > timeout * 0.9:  # 接近超时时间时警告
                logger.warning(
                    "工具 '%s' 执行接近超时（%.2f秒，超时阈值: %.2f秒）",
                    name,
                    execution_time,
                    timeout,
                )

            return str(result)

        except ValidationError as e:
            # v3.3.4: 改进错误信息处理
            error_msg = e.message if hasattr(e, 'message') and e.message else str(e) or repr(e) or "参数验证失败"
            full_error_msg = f"工具 '{name}' 参数验证失败: {error_msg}"
            logger.error(full_error_msg)
            with self._lock:
                stats.calls += 1
                stats.failures += 1
                stats.last_error = full_error_msg
            return f"抱歉主人，{full_error_msg} 喵~"
        except ResourceError as e:
            # v3.3.4: 改进错误信息处理
            error_msg = e.message if hasattr(e, 'message') and e.message else str(e) or repr(e) or "资源错误"
            full_error_msg = f"工具 '{name}' 资源错误: {error_msg}"
            logger.error(full_error_msg)
            with self._lock:
                stats.calls += 1
                stats.failures += 1
                stats.last_error = full_error_msg
            return f"抱歉主人，{full_error_msg} 喵~"
        except Exception as e:
            execution_time = time.time() - start_time
            # v3.3.4: 改进错误信息处理，避免空错误信息
            error_msg = str(e) or repr(e) or f"{type(e).__name__}: 工具执行失败"
            full_error_msg = f"工具 '{name}' 执行失败: {error_msg}"
            logger.error("%s，耗时: %.2f秒", full_error_msg, execution_time)

            # v3.3.4: 记录详细错误信息
            if logger.isEnabledFor(logging.DEBUG):
                import traceback

                logger.debug("错误堆栈:\n%s", traceback.format_exc())

            with self._lock:
                stats.calls += 1
                stats.failures += 1
                stats.last_error = full_error_msg
            return f"抱歉主人，工具执行失败了喵~ 错误: {error_msg}"

    def close(self) -> None:
        """关闭内部线程池"""
        with self._executor_lock:
            executor = self._executor
            self._executor = None
        if executor is not None:
            try:
                try:
                    executor.shutdown(wait=False, cancel_futures=True)
                except TypeError:
                    executor.shutdown(wait=False)
            except Exception:
                pass
        # 关闭 builtin_tools 的后台 loop/aiohttp session（若已加载）
        try:
            import sys

            if "src.agent.builtin_tools" in sys.modules:
                from src.agent.builtin_tools import shutdown_builtin_tools_runtime

                shutdown_builtin_tools_runtime()
        except Exception:
            pass
        # 关闭 MCP 会话（若已启用）
        try:
            import sys

            if "src.agent.mcp_manager" in sys.modules:
                from src.agent.mcp_manager import mcp_manager

                mcp_manager.close()
        except Exception:
            pass

    def get_tool_stats(self) -> Dict[str, Dict[str, Any]]:
        """返回工具执行统计信息（便于监控与调优）"""
        with self._lock:
            items = list(self._stats.items())
        return {name: stats.as_dict() for name, stats in items}


# 创建全局工具注册表实例
tool_registry = ToolRegistry()
