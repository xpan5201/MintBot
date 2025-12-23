"""
智能体核心模块

基于 LangChain 1.0.x 实现的多模态猫娘女仆智能体核心逻辑。
支持流式输出、情感系统、上下文感知等高级功能。

版本：v3.3.4
日期：2025-11-22
"""

# v3.3.3: 移除atexit导入，改为显式资源管理
# import atexit
import asyncio
import hashlib
import json
import re
import time
from pathlib import Path
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from queue import Empty, Full, Queue
from threading import Event, Lock
from typing import (
    Any,
    AsyncIterator,
    Dict,
    Iterator,
    List,
    Literal,
    Optional,
    TYPE_CHECKING,
    Callable,
    Coroutine,
    Tuple,
)

_LANGCHAIN_IMPORT_ERROR: Optional[BaseException] = None
try:
    from langchain.agents import create_agent

    HAS_LANGCHAIN = True
except Exception as exc:  # pragma: no cover - 环境依赖差异
    HAS_LANGCHAIN = False
    _LANGCHAIN_IMPORT_ERROR = exc
    create_agent = None  # type: ignore[assignment]

try:
    from langchain.agents.middleware import (
        AgentMiddleware,
        ClearToolUsesEdit,
        ContextEditingMiddleware,
        LLMToolSelectorMiddleware,
        ModelRequest,
        ModelResponse,
        ToolCallLimitMiddleware,
    )
    HAS_AGENT_MIDDLEWARE = True
    HAS_TOOL_SELECTOR = LLMToolSelectorMiddleware is not None
except ImportError:  # pragma: no cover - 旧版 LangChain
    AgentMiddleware = None
    ClearToolUsesEdit = None
    ContextEditingMiddleware = None
    LLMToolSelectorMiddleware = None
    ModelRequest = Any  # type: ignore
    ModelResponse = Any  # type: ignore
    ToolCallLimitMiddleware = None
    HAS_AGENT_MIDDLEWARE = False
    HAS_TOOL_SELECTOR = False

_LANGCHAIN_OPENAI_IMPORT_ERROR: Optional[BaseException] = None
try:
    from langchain_openai import ChatOpenAI
except Exception as exc:  # pragma: no cover - 环境依赖差异
    ChatOpenAI = None  # type: ignore[assignment]
    _LANGCHAIN_OPENAI_IMPORT_ERROR = exc

# 可选的 LLM 提供商（优雅降级）
try:
    from langchain_anthropic import ChatAnthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False
    ChatAnthropic = None

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    HAS_GOOGLE = True
except ImportError:
    HAS_GOOGLE = False
    ChatGoogleGenerativeAI = None

from src.character.config_loader import CharacterConfigLoader
from src.character.personality import CharacterPersonality, default_character
from src.config.settings import settings
from src.utils.logger import get_logger
from src.utils.performance import monitor_performance, performance_monitor
from src.utils.tool_context import tool_timeout_s_var

from .advanced_memory import CoreMemory, DiaryMemory, LoreBook
from .character_state import CharacterState
from .context_compressor import ContextCompressor
from .emotion import EmotionEngine
from .memory import MemoryManager
from .memory_retriever import ConcurrentMemoryRetriever
from .memory_scorer import MemoryScorer
from .mood_system import MoodSystem
from .style_learner import StyleLearner
from .tools import ToolRegistry, tool_registry

BaseAgentMiddleware = AgentMiddleware or object  # type: ignore[misc]

if TYPE_CHECKING:
    from src.multimodal.tts_manager import AgentSpeechProfile

logger = get_logger(__name__)

# 预编译正则（热路径：流式输出与无关信息过滤）
_CODE_FENCE_RE = re.compile(
    r"```(?P<lang>[^\n`]*)\n(?P<body>[\s\S]*?)```",
    flags=re.IGNORECASE,
)
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
_IDENT_TOKEN_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$")
_DEFAULT_EMPTY_REPLY = "抱歉主人，我好像没有理解您的意思喵~"


def _extract_leading_json_fragment(text: str) -> Optional[str]:
    """
    从字符串开头提取一个完整的 JSON object/array 片段（仅当 text[0] 是 '{' 或 '['）。

    说明：
    - 部分 OpenAI 兼容网关 / LangChain 1.0.x 组合会把 structured output 片段（工具选择/分流标签）
      直接拼接到自然语言回复之前，导致 UI/TTS 污染。
    - 这里用于“前缀剥离”，只在开头是 JSON 时工作，避免误伤正常文本。
    """
    if not text or text[0] not in "{[":
        return None

    stack: list[str] = []
    in_string = False
    escaped = False

    for idx, ch in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue

        if ch in "{[":
            stack.append(ch)
            continue
        if ch in "]}":
            if not stack:
                return None
            opener = stack.pop()
            if (opener == "{" and ch != "}") or (opener == "[" and ch != "]"):
                return None
            if not stack:
                return text[: idx + 1]

    return None


def _extract_any_json_fragment(text: str) -> Optional[str]:
    """Extract the first JSON object/array fragment found in text."""
    if not text:
        return None
    s = text.strip()
    if not s:
        return None
    start_candidates = [idx for idx in (s.find("{"), s.find("[")) if idx >= 0]
    if not start_candidates:
        return None
    start = min(start_candidates)

    stack: list[str] = []
    in_string = False
    escaped = False

    for i in range(start, len(s)):
        ch = s[i]
        if in_string:
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue

        if ch in "{[":
            stack.append(ch)
            continue
        if ch in "]}":
            if not stack:
                continue
            opener = stack.pop()
            if (opener == "{" and ch != "}") or (opener == "[" and ch != "]"):
                return None
            if not stack:
                return s[start : i + 1]

    return None


def _looks_like_tool_call_payload(data: Any) -> bool:
    """
    Heuristically detect common "tool call" / structured-tool routing payloads that should not be shown to UI/TTS.

    This targets OpenAI-style tool call JSON such as:
      [{"id": "...", "type": "function", "function": {"name": "...", "arguments": "..."}}, ...]
    as well as LangChain variants ("tools"/"tool_calls", {"tool": ..., "args": ...}).
    """

    def _lower_keys(mapping: Dict[Any, Any]) -> set[str]:
        try:
            return {str(k).lower() for k in mapping.keys()}
        except Exception:
            return set()

    if isinstance(data, dict):
        keys = _lower_keys(data)
        dtype = str(data.get("type") or "").lower()

        if "tool_calls" in keys or "tools" in keys or dtype in {"tool_calls", "tool_call"}:
            return True

        if dtype == "function":
            func = data.get("function")
            if isinstance(func, dict):
                fkeys = _lower_keys(func)
                if "name" in fkeys and ("arguments" in fkeys or "args" in fkeys):
                    return True
            if "name" in keys and ("arguments" in keys or "args" in keys):
                return True

        # OpenAI tool call dict without explicit "type":"function" (defensive)
        func = data.get("function")
        if "function" in keys and isinstance(func, dict):
            fkeys = _lower_keys(func)
            if "name" in fkeys and ("arguments" in fkeys or "args" in fkeys):
                return True

        # Common LangChain-style forms
        if "tool" in keys and ("args" in keys or "arguments" in keys or "tool_input" in keys or "toolinput" in keys):
            return True

        # Some gateways emit {"id": "...", "name": "...", "arguments": "..."}.
        if "name" in keys and ("arguments" in keys or "args" in keys) and ("id" in keys or "tool" in keys):
            return True

        return False

    if isinstance(data, list) and data and all(isinstance(item, dict) for item in data):
        return any(_looks_like_tool_call_payload(item) for item in data)

    return False


def _strip_tool_json_blocks(text: str, *, max_blocks: int = 3) -> str:
    """
    Remove embedded JSON blocks that look like tool-call payloads.

    This helps when some proxies/gateways inject tool-call JSON into natural language output.
    """
    if not text:
        return text

    cleaned = text
    for _ in range(max(0, int(max_blocks))):
        idx_candidates = [i for i in (cleaned.find("{"), cleaned.find("[")) if i >= 0]
        if not idx_candidates:
            break
        idx = min(idx_candidates)
        fragment = _extract_leading_json_fragment(cleaned[idx:])
        if not fragment:
            break
        if len(fragment) > 50_000:
            break

        parsed: Any = None
        try:
            parsed = json.loads(fragment)
        except Exception:
            parsed = None

        if parsed is None:
            lowered_fragment = fragment.lower()
            looks_like_tool = (
                "tool_calls" in lowered_fragment
                or '"tool_calls"' in lowered_fragment
                or '"tools"' in lowered_fragment
                or (
                    "\"function\"" in lowered_fragment
                    and "\"arguments\"" in lowered_fragment
                    and "\"name\"" in lowered_fragment
                )
                or ("\"type\"" in lowered_fragment and "\"function\"" in lowered_fragment)
            )
            if not looks_like_tool:
                break
        else:
            if not _looks_like_tool_call_payload(parsed):
                break

        cleaned = (cleaned[:idx] + cleaned[idx + len(fragment) :]).strip()

    return cleaned


def _looks_like_route_tag_list(data: Any) -> bool:
    """
    Detect routing/tag lists leaked into the assistant text, e.g.:
      ["local_search", "map_guide"]
      ["emotion_analysis", "affection_expression", ...]

    We keep it conservative: only list[str] of identifier-like snake_case tokens.
    """
    if not (isinstance(data, list) and data and all(isinstance(item, str) for item in data)):
        return False
    if len(data) > 24:
        return False
    normalized = [item.strip() for item in data if isinstance(item, str)]
    if not normalized:
        return False
    if not all(_IDENT_TOKEN_RE.fullmatch(item) for item in normalized):
        return False
    if not any("_" in item for item in normalized):
        return False
    return True


def _strip_route_tag_lists(text: str, *, max_blocks: int = 5) -> str:
    """
    Remove embedded route/tag list fragments (list[str]) leaked into natural language.

    Example leakage:
      ...\n["local_search","map_guide"]}\n...
    """
    if not text:
        return text

    cleaned = text
    pos = 0
    removed = 0
    while removed < max(0, int(max_blocks)):
        idx = cleaned.find("[", pos)
        if idx < 0:
            break

        fragment = _extract_leading_json_fragment(cleaned[idx:])
        if not fragment:
            break
        if len(fragment) > 20_000:
            break

        parsed: Any = None
        try:
            parsed = json.loads(fragment)
        except Exception:
            parsed = None

        if parsed is None or not _looks_like_route_tag_list(parsed):
            pos = idx + 1
            continue

        after = cleaned[idx + len(fragment) :]
        after_lstrip = after.lstrip()
        # Only remove when it clearly behaves like an internal marker: followed by a stray brace,
        # or followed by another JSON/brace block.
        remove_trailing_brace = after_lstrip.startswith("}")
        next_char = after_lstrip[:1]
        if not remove_trailing_brace and next_char not in {"", "{", "[", "}", "]"}:
            # Looks like a normal JSON list in prose – keep it.
            pos = idx + 1
            continue

        end_idx = idx + len(fragment)
        if remove_trailing_brace:
            # remove the first '}' after optional whitespace
            brace_offset = len(after) - len(after_lstrip)
            end_idx = end_idx + brace_offset + 1

        cleaned = (cleaned[:idx] + cleaned[end_idx:]).strip()
        removed += 1
        pos = 0

    return cleaned


def _strip_tool_code_fences(text: str, *, max_blocks: int = 3) -> str:
    """
    Remove code fences that contain internal tool-selection / routing traces.

    We keep this conservative:
    - Don't strip normal code blocks (e.g. user requests code snippets).
    - Only strip when the fenced content clearly resembles tool payloads or leaked route-tag lists.
    """
    if not text or "```" not in text:
        return text
    limit = max(0, int(max_blocks))
    if limit <= 0:
        return text

    removed = 0

    def _looks_like_tool_trace(lang: str, body: str) -> bool:
        lang_key = (lang or "").strip().split()[0].lower()
        body_lstrip = (body or "").lstrip()
        if not body_lstrip:
            return False

        lower_body = body_lstrip.lower()
        if lower_body.startswith("toolselectionresponse"):
            return True
        if lang_key in {"tool", "tools", "tool_calls", "toolcalls", "toolcall"}:
            return True

        if body_lstrip[0] in "{[":
            fragment = _extract_leading_json_fragment(body_lstrip)
            if fragment:
                parsed: Any = None
                if len(fragment) <= 50_000:
                    try:
                        parsed = json.loads(fragment)
                    except Exception:
                        parsed = None
                if parsed is not None:
                    if _looks_like_tool_call_payload(parsed) or _looks_like_route_tag_list(parsed):
                        return True
                else:
                    frag_lower = fragment.lower()
                    if (
                        "tool_calls" in frag_lower
                        or '"tool_calls"' in frag_lower
                        or '"tools"' in frag_lower
                        or (
                            '"function"' in frag_lower
                            and '"arguments"' in frag_lower
                            and '"name"' in frag_lower
                        )
                    ):
                        return True

        return False

    def _repl(match: re.Match[str]) -> str:
        nonlocal removed
        if removed >= limit:
            return match.group(0)
        lang = match.group("lang") or ""
        body = match.group("body") or ""
        if _looks_like_tool_trace(lang, body):
            removed += 1
            return ""
        return match.group(0)

    return _CODE_FENCE_RE.sub(_repl, text)


@dataclass(frozen=True)
class LLMTimeouts:
    """LLM 超时配置"""

    first_chunk: float
    idle_chunk: float
    total: float


class AgentTimeoutError(RuntimeError):
    """Agent 调用过程中触发的超时或看门狗异常"""


class LLMStreamWatchdog:
    """用于同步/异步流式输出的轻量看门狗"""

    def __init__(self, limits: LLMTimeouts):
        self.limits = limits
        self._start = time.perf_counter()
        self._last_chunk = self._start
        self._first_received = False
        self._first_latency_ms: Optional[float] = None

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._start) * 1000

    def remaining_total(self) -> float:
        return self.limits.total - (time.perf_counter() - self._start)

    def next_wait(self) -> float:
        now = time.perf_counter()
        remaining_total = self.limits.total - (now - self._start)
        if remaining_total <= 0:
            raise AgentTimeoutError("LLM 流式调用总耗时超出限制")

        since_last = now - self._last_chunk
        window = self.limits.first_chunk if not self._first_received else self.limits.idle_chunk
        if since_last >= window:
            if not self._first_received:
                raise AgentTimeoutError(f"LLM 流式调用首包超时（>{window:.1f}s）")
            raise AgentTimeoutError(f"LLM 流式调用无输出超时（>{window:.1f}s）")

        return max(0.05, min(window - since_last, remaining_total))

    def mark_chunk(self) -> Optional[float]:
        now = time.perf_counter()
        self._last_chunk = now
        if not self._first_received:
            self._first_received = True
            self._first_latency_ms = (now - self._start) * 1000
        return self._first_latency_ms


class StreamDeltaAccumulator:
    """仅返回累计流中的增量片段，避免重复渲染和TTS处理。"""

    def __init__(self) -> None:
        self._last: str = ""

    def consume(self, text: str) -> str:
        if not text:
            return ""

        if text.startswith(self._last):
            delta = text[len(self._last) :]
        else:
            prefix_len = 0
            for a, b in zip(text, self._last):
                if a != b:
                    break
                prefix_len += 1
            delta = text[prefix_len:]

        self._last = text
        return delta

    def reset(self) -> None:
        self._last = ""


class StreamEmitBuffer:
    """合并细碎增量，降低UI/TTS刷新频率。"""

    def __init__(self, min_chars: int = 8) -> None:
        self.min_chars = max(1, min_chars)
        self._chunks: list[str] = []

    def push(self, delta: str) -> str:
        if not delta:
            return ""
        self._chunks.append(delta)
        buffered = "".join(self._chunks)
        if "\n" in delta or len(buffered) >= self.min_chars:
            self._chunks.clear()
            return buffered
        return ""

    def flush(self) -> str:
        if not self._chunks:
            return ""
        buffered = "".join(self._chunks)
        self._chunks.clear()
        return buffered


class StreamStructuredPrefixStripper:
    """
    针对流式输出开头的 structured output / 工具信息残留做“前缀剥离”。

    一些 OpenAI 兼容网关 + LangChain 1.0.x 组合会把工具选择/结构化片段（JSON）
    当作普通消息流事件吐出，从而被 UI 直接拼接到回复开头（例如：["general_chat"]}...）。

    该类会在流式开头阶段缓冲增量，直到：
    - 识别到可丢弃的 JSON 前缀片段并剥离；或
    - 确认输出并非上述前缀（例如用户真的需要返回 JSON），再开始透传。
    """

    def __init__(self, *, max_fragments: int = 3, max_buffer_chars: int = 4096) -> None:
        self._max_fragments = max(0, int(max_fragments))
        self._max_buffer_chars = max(0, int(max_buffer_chars))
        self._buffer: str = ""
        self._done = False

    def process(self, delta: str) -> str:
        if not delta:
            return ""
        if self._done:
            return delta
        self._buffer += delta
        return self._try_release(force=False)

    def flush(self) -> str:
        if self._done:
            return ""
        return self._try_release(force=True)

    def _try_release(self, *, force: bool) -> str:
        full_text = self._buffer
        if not full_text:
            return ""

        # Drop non-JSON tool routing traces that some gateways inject before the real assistant text.
        # We do this before JSON stripping and keep it conservative (only at the very start).
        for _ in range(2):
            candidate = full_text.lstrip()
            if not candidate:
                if force:
                    self._done = True
                    self._buffer = ""
                    return ""
                self._buffer = full_text
                return ""
            candidate_lower = candidate.lower()
            marker = "toolselectionresponse"
            if marker.startswith(candidate_lower) and candidate_lower != marker:
                # The marker might be arriving in fragments. Keep buffering until we can decide.
                if force or (self._max_buffer_chars and len(candidate) > self._max_buffer_chars):
                    self._done = True
                    self._buffer = ""
                    return ""
                self._buffer = full_text
                return ""

            if candidate_lower.startswith(marker):
                nl = candidate.find("\n")
                if nl < 0:
                    if force or (self._max_buffer_chars and len(candidate) > self._max_buffer_chars):
                        self._done = True
                        self._buffer = ""
                        return ""
                    self._buffer = full_text
                    return ""
                full_text = candidate[nl + 1 :].lstrip()
                self._buffer = full_text
                if not full_text:
                    return ""
                continue
            break

        # Some gateways prepend whitespace/newlines before the structured JSON prefix.
        # If we see leading whitespace, inspect the first non-whitespace char before deciding
        # whether we should enter the "structured prefix stripping" mode.
        leading_ws_len = len(full_text) - len(full_text.lstrip())
        if leading_ws_len:
            candidate = full_text[leading_ws_len:]
            if not candidate:
                if force:
                    self._done = True
                    self._buffer = ""
                    return full_text
                self._buffer = full_text
                return ""
            if candidate[0] in "{[":
                text = candidate
                original_on_keep = full_text
            else:
                self._done = True
                self._buffer = ""
                return full_text
        else:
            text = full_text
            original_on_keep = full_text
            if text[0] not in "{[":
                self._done = True
                self._buffer = ""
                return text

        if text[0] not in "{[":
            self._done = True
            self._buffer = ""
            return original_on_keep

        cleaned = text
        for _ in range(self._max_fragments):
            if not cleaned or cleaned[0] not in "{[":
                break

            fragment = _extract_leading_json_fragment(cleaned)
            if fragment is None:
                if force or (self._max_buffer_chars and len(cleaned) > self._max_buffer_chars):
                    self._done = True
                    self._buffer = ""
                    return original_on_keep
                self._buffer = full_text
                return ""

            rest = cleaned[len(fragment) :]
            rest_lstrip = rest.lstrip()
            has_trailing_brace = rest_lstrip.startswith("}")
            rest_after_braces = rest_lstrip.lstrip("}").lstrip()

            if not self._should_drop_fragment(fragment, has_trailing_brace, rest_after_braces):
                self._done = True
                self._buffer = ""
                return original_on_keep

            cleaned = rest_after_braces

        self._buffer = cleaned
        if not cleaned:
            return ""

        if cleaned[0] in "{[":
            fragment = _extract_leading_json_fragment(cleaned)
            if fragment is None and not force and (
                not self._max_buffer_chars or len(cleaned) <= self._max_buffer_chars
            ):
                return ""

        self._done = True
        self._buffer = ""
        return cleaned

    @staticmethod
    def _should_drop_fragment(fragment: str, has_trailing_brace: bool, rest_after_braces: str) -> bool:
        lowered_fragment = fragment.lower()
        parsed: Any = None
        if len(fragment) <= 50_000:
            try:
                parsed = json.loads(fragment)
            except Exception:
                parsed = None

        if parsed is not None and _looks_like_tool_call_payload(parsed):
            return True
        if parsed is None:
            # Heuristic for very large fragments (or parse failures): keep it conservative.
            # Only drop when it strongly resembles tool-call payloads.
            if "tool_calls" in lowered_fragment or '"tool_calls"' in lowered_fragment or '"tools"' in lowered_fragment:
                return True
            if (
                '"type":"function"' in lowered_fragment
                and '"function"' in lowered_fragment
                and '"arguments"' in lowered_fragment
                and '"name"' in lowered_fragment
            ):
                return True

        if isinstance(parsed, list) and parsed and all(isinstance(item, str) for item in parsed):
            normalized = [item.strip() for item in parsed]
            if not normalized:
                return False
            if not all(_IDENT_TOKEN_RE.fullmatch(item) for item in normalized):
                return False
            if not any("_" in item for item in normalized):
                return False
            if has_trailing_brace or rest_after_braces[:1] in "[{":
                return True

        return False


_LINESTART_JSON_OPEN_RE = re.compile(r"(?:^|\n)[ \t]*(?P<open>[\\[{])")


class StreamToolTraceScrubber:
    """
    Stateful scrubber for streaming output.

    Root cause (LangChain/LangGraph 1.0.x): when using `stream_mode="messages"`, some intermediate routing steps
    (tool selection / structured output) can be streamed as assistant-like text messages. On some OpenAI-compatible
    gateways, those structured payloads arrive as plain text (sometimes split across chunks), so "end-only" filtering
    is not enough.

    Strategy:
    - Only react when we see suspicious markers (ToolSelectionResponse / JSON-like blocks at line start).
    - Buffer minimal tail if a JSON/tool fragment is incomplete, so partial garbage never reaches UI.
    - Remove:
        - ToolSelectionResponse lines
        - tool-call payload JSON blocks (dict/list)
        - route/tag list fragments (list[str] of snake_case identifiers)
    """

    def __init__(self, *, max_buffer_chars: int = 16_384, max_scan_blocks: int = 8) -> None:
        self._buffer = ""
        self._max_buffer_chars = max(0, int(max_buffer_chars))
        self._max_scan_blocks = max(1, int(max_scan_blocks))

    @staticmethod
    def _is_suspicious(text: str) -> bool:
        if not text:
            return False
        stripped = text.lstrip()
        if stripped.startswith("{") or stripped.startswith("["):
            return True
        if "\n{" in text or "\n[" in text:
            return True

        lower = text.lower()
        if "toolselectionresponse" in lower:
            return True
        if "tool_calls" in lower or "\"tool_calls\"" in lower or "\"tools\"" in lower:
            return True
        if ("{" in text or "[" in text) and ("_\"" in text or "_" in text):
            # route tag list often contains underscores and quote brackets
            if '["' in text:
                return True
        if "\"function\"" in lower and "\"arguments\"" in lower and "\"name\"" in lower:
            return True
        return False

    def process(self, delta: str) -> str:
        if not delta:
            return ""
        if not self._buffer and not self._is_suspicious(delta):
            return delta

        self._buffer += delta
        if self._max_buffer_chars and len(self._buffer) > self._max_buffer_chars:
            # Keep the newest tail; tool traces are near the frontier.
            self._buffer = self._buffer[-self._max_buffer_chars :]

        return self._drain(force=False)

    def flush(self) -> str:
        return self._drain(force=True)

    def _drain(self, *, force: bool) -> str:
        s = self._buffer
        if not s:
            return ""

        out_parts: list[str] = []
        blocks_scanned = 0

        while s and blocks_scanned < self._max_scan_blocks:
            blocks_scanned += 1

            # 1) Drop ToolSelectionResponse line(s) if present at the frontier.
            candidate = s.lstrip()
            if candidate:
                lower = candidate.lower()
                marker = "toolselectionresponse"
                if marker.startswith(lower) and lower != marker:
                    if not force:
                        break
                if lower.startswith(marker):
                    nl = candidate.find("\n")
                    if nl < 0:
                        if not force:
                            break
                        s = ""
                        continue
                    s = candidate[nl + 1 :].lstrip()
                    continue

            # 2) Find next "line-start JSON" opener.
            match = _LINESTART_JSON_OPEN_RE.search(s)
            if not match:
                out_parts.append(s)
                s = ""
                break

            open_idx = match.start("open")
            if open_idx > 0:
                out_parts.append(s[:open_idx])
                s = s[open_idx:]

            fragment = _extract_leading_json_fragment(s)
            if fragment is None:
                # Incomplete JSON: keep buffered so partial tool traces won't show.
                if force:
                    out_parts.append(s)
                    s = ""
                break

            remove_fragment = False
            parsed: Any = None
            try:
                parsed = json.loads(fragment)
            except Exception:
                parsed = None

            if parsed is not None:
                if _looks_like_tool_call_payload(parsed) or _looks_like_route_tag_list(parsed):
                    remove_fragment = True
            else:
                lowered_fragment = fragment.lower()
                if (
                    "tool_calls" in lowered_fragment
                    or "\"tool_calls\"" in lowered_fragment
                    or "\"tools\"" in lowered_fragment
                    or ("\"function\"" in lowered_fragment and "\"arguments\"" in lowered_fragment and "\"name\"" in lowered_fragment)
                ):
                    remove_fragment = True

            if not remove_fragment:
                out_parts.append(fragment)
                s = s[len(fragment) :]
                continue

            # Drop fragment and an optional stray trailing brace '}'.
            rest = s[len(fragment) :]
            rest_lstrip = rest.lstrip()
            if rest_lstrip.startswith("}"):
                rest = rest_lstrip[1:]
            s = rest.lstrip()

        self._buffer = s
        return "".join(out_parts)


_STREAM_INTERNAL_META_TOKENS: tuple[str, ...] = (
    # Tool selector middleware / structured outputs
    "toolselectionresponse",
    "tool_selector",
    "toolselector",
    "tool_selection",
    "select_tools",
    "tool_select",
    # Routing/planning steps
    "router",
    "routing",
    "route_planner",
    "planner",
)


def _iter_metadata_strings(metadata: Any, *, max_items: int = 96) -> Iterator[str]:
    """
    Best-effort extraction of informative strings from LangChain/LangGraph stream metadata.

    Notes:
    - We prefer metadata-based filtering over brittle content filtering.
    - Keep it bounded: metadata can be nested and occasionally large.
    """
    if metadata is None or max_items <= 0:
        return

    emitted = 0
    stack: list[Any] = [metadata]

    while stack and emitted < max_items:
        item = stack.pop()
        if item is None:
            continue
        if isinstance(item, str):
            if item:
                emitted += 1
                yield item if len(item) <= 512 else item[:512]
            continue
        if isinstance(item, dict):
            # Prefer known fields first.
            for key in ("langgraph_node", "node", "name", "run_name"):
                if key in item and isinstance(item[key], str):
                    if emitted >= max_items:
                        break
                    emitted += 1
                    yield item[key]
            tags = item.get("tags")
            if isinstance(tags, (list, tuple, set)):
                for tag in tags:
                    if isinstance(tag, str) and tag:
                        if emitted >= max_items:
                            break
                        emitted += 1
                        yield tag
            elif isinstance(tags, str) and tags:
                if emitted < max_items:
                    emitted += 1
                    yield tags

            nested = item.get("metadata")
            if nested is not None and nested is not item:
                stack.append(nested)
            continue
        if isinstance(item, (list, tuple, set)):
            for sub in item:
                if emitted >= max_items:
                    break
                stack.append(sub)
            continue

        # Fallback: pull common attributes from non-dict metadata objects.
        for attr in ("langgraph_node", "node", "name", "run_name", "tags", "metadata"):
            if emitted >= max_items:
                break
            try:
                value = getattr(item, attr)
            except Exception:
                continue
            if value is item:
                continue
            stack.append(value)


def _metadata_looks_like_internal_routing(metadata: Any) -> bool:
    """
    Detect tool-selection / routing metadata markers in a generic way.

    This complements (not replaces) content scrubbers:
    - If metadata is available, drop intermediate node outputs early.
    - If metadata is missing/poor, the scrubber still protects the UI.
    """
    for text in _iter_metadata_strings(metadata):
        lowered = text.lower()
        if any(token in lowered for token in _STREAM_INTERNAL_META_TOKENS):
            return True
    return False


@dataclass(slots=True)
class AgentConversationBundle:
    """封装一次对话请求需要的上下文，方便在不同模式间复用。"""

    messages: List[Dict[str, str]]
    save_message: str
    original_message: str
    processed_message: str
    image_analysis: Optional[dict] = None
    image_path: Optional[str] = None


class PermissionScopedToolMiddleware(BaseAgentMiddleware):
    """
    根据运行时上下文裁剪工具集合的轻量中间件。
    参考 Context7 LangChain Middleware 指南，利用 wrap_model_call 在进入主模型之前过滤工具。
    """

    def __init__(
        self,
        profile_map: Dict[str, List[str]],
        default_profile: str = "default",
    ):
        self._default_profile = default_profile or "default"
        normalized = {
            profile: {name for name in tools if name}
            for profile, tools in (profile_map or {}).items()
            if tools
        }
        self._profile_map = normalized

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        if not self._profile_map:
            return handler(request)

        profile = self._resolve_profile(request)
        allowed = self._profile_map.get(profile)
        if allowed is None and profile != self._default_profile:
            allowed = self._profile_map.get(self._default_profile)

        if allowed:
            request.tools = [tool for tool in request.tools if tool.name in allowed]
        return handler(request)

    def _resolve_profile(self, request: ModelRequest) -> str:
        context = getattr(request.runtime, "context", None)
        profile = None
        if context is not None:
            if isinstance(context, dict):
                profile = context.get("tool_profile")
            else:
                profile = getattr(context, "tool_profile", None)

        if not profile:
            state = getattr(request, "state", None)
            if isinstance(state, dict):
                profile = state.get("tool_profile")

        return profile or self._default_profile


class MintChatAgent:
    """
    MintChat 智能体核心类

    支持流式输出、情感系统、上下文感知等高级功能。
    """

    _POSITIVE_MOOD_EMOTIONS = frozenset({"开心", "兴奋", "俏皮", "亲昵", "好奇"})

    def __init__(
        self,
        character: Optional[CharacterPersonality] = None,
        memory_manager: Optional[MemoryManager] = None,
        tool_registry_instance: Optional[ToolRegistry] = None,
        emotion_engine: Optional[EmotionEngine] = None,
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        enable_streaming: Optional[bool] = None,
        user_id: Optional[int] = None,
    ):
        """
        初始化 MintChat 智能体

        Args:
            character: 角色性格配置
            memory_manager: 记忆管理器
            tool_registry_instance: 工具注册表
            emotion_engine: 情感引擎
            model_name: 模型名称
            temperature: 温度参数
            enable_streaming: 是否启用流式输出
            user_id: 用户ID，用于创建用户特定的记忆路径
        """
        # 用户ID
        self.user_id = user_id

        # 角色配置
        self.character = character or default_character
        logger.info(f"初始化角色: {self.character.name} (用户ID: {user_id if user_id else '全局'})")

        # 记忆管理器 - 使用用户特定路径
        # 由 Agent 统一调度后台巩固，避免 MemoryManager 内部重复启动线程
        self.memory = memory_manager or MemoryManager(user_id=user_id, enable_auto_consolidate=False)

        # 高级记忆系统 - 使用用户特定路径
        self.core_memory = CoreMemory(user_id=user_id)
        self.diary_memory = DiaryMemory(user_id=user_id)
        self.lore_book = LoreBook(user_id=user_id)

        # 并发记忆检索器（性能优化）
        self.memory_retriever = ConcurrentMemoryRetriever(
            long_term_memory=self.memory,
            core_memory=self.core_memory,
            diary_memory=self.diary_memory,
            lore_book=self.lore_book,
            max_workers=4,
            breaker_threshold=int(getattr(settings.agent, "memory_breaker_threshold", 3)),
            breaker_cooldown_s=float(getattr(settings.agent, "memory_breaker_cooldown", 3.0)),
        )

        # 工具注册表
        self.tool_registry = tool_registry_instance or tool_registry

        # 情感引擎（支持持久化）
        self.emotion_engine = emotion_engine or EmotionEngine(
            enable_emotion_memory=settings.agent.emotion_memory_enabled,
            enable_dual_source=settings.agent.dual_source_emotion,
            user_id=user_id,
        )

        # 高级情绪系统 - 使用用户特定路径
        self.mood_system = MoodSystem(user_id=user_id)

        # 核心功能组件
        self.character_state = CharacterState()
        self.context_compressor = ContextCompressor()
        self.style_learner = StyleLearner()
        self.memory_scorer = MemoryScorer()
        self._tts_runtime: Optional[tuple[Any, Any]] = None  # 懒加载 TTS 依赖
        self._auto_compress_ratio = max(
            0.1,
            min(1.0, float(getattr(settings.agent, "context_auto_compress_ratio", 0.75))),
        )
        self._auto_compress_min_messages = max(
            4,
            int(getattr(settings.agent, "context_auto_compress_min_messages", 12)),
        )
        self._history_summary_keep = max(
            6,
            int(
                getattr(
                    settings.agent,
                    "context_summary_keep_messages",
                    self._auto_compress_min_messages,
                )
            ),
        )
        self._tts_prefetch_enabled = bool(getattr(settings.agent, "tts_auto_prefetch", True))
        self._tts_prefetch_min_chars = max(
            1,
            int(getattr(settings.agent, "tts_prefetch_min_chars", 48)),
        )
        self._fast_retry_enabled = bool(getattr(settings.agent, "llm_fast_retry", True))
        self._last_tts_prefetch_text: Optional[str] = None
        self._interaction_lock = Lock()
        self._tts_prefetch_lock = Lock()
        self._pending_tts_prefetch: Optional[Future] = None
        self._background_executor = ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="mintchat-agent-bg",
        )
        self._background_futures: set[Future] = set()
        self._background_lock = Lock()
        self._max_background_queue = 8
        self._context_cache: OrderedDict[tuple[int, str | bytes, str], list[Dict[str, str]]] = OrderedDict()
        self._context_cache_lock = Lock()
        self._context_cache_max = max(0, int(getattr(settings.agent, "context_cache_max_entries", 16)))
        # v3.3.3: 移除atexit注册，改为在close()方法中显式清理

        self._llm_timeouts = LLMTimeouts(
            first_chunk=max(
                1.0,
                float(getattr(settings.agent, "llm_first_chunk_timeout_s", 18.0)),
            ),
            idle_chunk=max(
                1.0,
                float(getattr(settings.agent, "llm_idle_chunk_timeout_s", 30.0)),
            ),
            total=max(
                2.0,
                float(getattr(settings.agent, "llm_total_timeout_s", 120.0)),
            ),
        )
        self._llm_executor = ThreadPoolExecutor(
            max_workers=max(1, int(getattr(settings.agent, "llm_executor_workers", 2))),
            thread_name_prefix="mintchat-agent-llm",
        )
        self._stream_executor = ThreadPoolExecutor(
            max_workers=max(1, int(getattr(settings.agent, "stream_executor_workers", 2))),
            thread_name_prefix="mintchat-agent-stream",
        )
        self._blocking_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="mintchat-agent-loop",
        )
        self._stream_min_chars = max(1, int(getattr(settings.agent, "stream_min_chunk_chars", 8)))
        # v3.3.3: 移除atexit注册，改为在close()方法中显式清理

        # 记忆巩固计数器
        self._interaction_count = 0
        self._consolidation_interval = 10  # 每10次对话巩固一次记忆

        # 流式输出配置
        if enable_streaming is None:
            enable_streaming = bool(getattr(settings.agent, "enable_streaming", True))
        else:
            enable_streaming = bool(enable_streaming)
        # 用户配置（是否允许启用 streaming）。运行时可能因失败临时禁用，但冷却后可自动恢复。
        self._streaming_user_enabled = bool(enable_streaming)
        self.enable_streaming = bool(enable_streaming)
        self._streaming_disabled_until = 0.0
        self._stream_failure_count = 0
        self._stream_disable_after_failures = max(
            1,
            int(getattr(settings.agent, "llm_stream_disable_after_failures", 2)),
        )
        self._stream_disable_cooldown_s = max(
            0.0,
            float(getattr(settings.agent, "llm_stream_disable_cooldown_s", 60.0)),
        )
        self._stream_failover_timeout_s = max(
            5.0,
            min(
                self._llm_timeouts.total,
                float(getattr(settings.agent, "llm_stream_failover_timeout_s", 60.0)),
            ),
        )

        # 初始化 LLM
        self.model_name = model_name or settings.default_model_name
        self.temperature = temperature or settings.model_temperature
        self.llm = self._initialize_llm()

        # 创建 Agent
        self._agent_middleware = self._build_agent_middleware_stack()
        self.agent = self._create_agent()

        logger.info(
            f"MintChat 智能体初始化完成 (流式输出: {self.enable_streaming})"
        )

    def _initialize_llm(self):
        """
        初始化语言模型

        Returns:
            LLM 实例

        Raises:
            ValueError: 如果 LLM 提供商不支持或 API Key 未配置
        """
        provider = settings.default_llm_provider

        try:
            streaming_requested = bool(getattr(self, "enable_streaming", False))
            if provider == "openai":
                if ChatOpenAI is None:
                    raise ImportError(
                        "langchain-openai 未安装或导入失败，无法创建 ChatOpenAI。"
                        " 请运行: uv sync --locked --no-install-project"
                    ) from _LANGCHAIN_OPENAI_IMPORT_ERROR
                if not settings.openai_api_key:
                    raise ValueError("OpenAI API Key 未配置")

                openai_kwargs = dict(
                    model=self.model_name,
                    temperature=self.temperature,
                    max_tokens=settings.model_max_tokens,
                    api_key=settings.openai_api_key,
                    timeout=120.0,
                    max_retries=2,
                )
                if streaming_requested:
                    openai_kwargs["streaming"] = True
                try:
                    llm = ChatOpenAI(**openai_kwargs)
                except TypeError:
                    # 兼容不同版本 LangChain：不支持 streaming 参数时自动回退
                    openai_kwargs.pop("streaming", None)
                    llm = ChatOpenAI(**openai_kwargs)
                logger.info(f"使用 OpenAI 模型: {self.model_name}，超时: 120秒")

            elif provider == "anthropic":
                if not HAS_ANTHROPIC:
                    raise ImportError(
                        "langchain_anthropic 未安装。请运行: uv sync --locked --no-install-project"
                    )
                if not settings.anthropic_api_key:
                    raise ValueError("Anthropic API Key 未配置")

                anthropic_kwargs = dict(
                    model=self.model_name,
                    temperature=self.temperature,
                    max_tokens=settings.model_max_tokens,
                    anthropic_api_key=settings.anthropic_api_key,
                    timeout=120.0,
                    max_retries=2,
                )
                if streaming_requested:
                    anthropic_kwargs["streaming"] = True
                try:
                    llm = ChatAnthropic(**anthropic_kwargs)
                except TypeError:
                    anthropic_kwargs.pop("streaming", None)
                    llm = ChatAnthropic(**anthropic_kwargs)
                logger.info(f"使用 Anthropic 模型: {self.model_name}，超时: 120秒")

            elif provider == "google":
                if not HAS_GOOGLE:
                    raise ImportError(
                        "langchain_google_genai 未安装。请运行: uv sync --locked --no-install-project"
                    )
                if not settings.google_api_key:
                    raise ValueError("Google API Key 未配置")

                google_kwargs = dict(
                    model=self.model_name,
                    temperature=self.temperature,
                    max_output_tokens=settings.model_max_tokens,
                    google_api_key=settings.google_api_key,
                    timeout=120.0,
                )
                if streaming_requested:
                    google_kwargs["streaming"] = True
                try:
                    llm = ChatGoogleGenerativeAI(**google_kwargs)
                except TypeError:
                    google_kwargs.pop("streaming", None)
                    llm = ChatGoogleGenerativeAI(**google_kwargs)
                logger.info(f"使用 Google 模型: {self.model_name}，超时: 120秒")

            else:
                # 使用自定义 OpenAI 兼容 API（如 SiliconFlow、DeepSeek 等）
                if ChatOpenAI is None:
                    raise ImportError(
                        "langchain-openai 未安装或导入失败，无法创建 ChatOpenAI。"
                        " 请运行: uv sync --locked --no-install-project"
                    ) from _LANGCHAIN_OPENAI_IMPORT_ERROR
                if not settings.llm.key:
                    raise ValueError("API Key 未配置")

                compat_kwargs = dict(
                    model=self.model_name,
                    temperature=self.temperature,
                    max_tokens=settings.model_max_tokens,
                    api_key=settings.llm.key,
                    base_url=settings.llm.api,
                    timeout=120.0,
                    max_retries=2,
                )
                if streaming_requested:
                    compat_kwargs["streaming"] = True
                try:
                    llm = ChatOpenAI(**compat_kwargs)
                except TypeError:
                    compat_kwargs.pop("streaming", None)
                    llm = ChatOpenAI(**compat_kwargs)
                logger.info(
                    f"使用自定义 OpenAI 兼容 API: {settings.llm.api}, "
                    f"模型: {self.model_name}，超时: 120秒"
                )

            return llm

        except Exception as e:
            logger.error(f"LLM 初始化失败: {e}")
            raise

    def _create_agent(self) -> Any:
        """
        创建 LangChain Agent

        Returns:
            Agent 实例
        """
        try:
            if not HAS_LANGCHAIN or create_agent is None:
                raise ImportError(
                    "langchain 未安装或导入失败，无法创建 Agent。请运行: uv sync --locked --no-install-project"
                ) from _LANGCHAIN_IMPORT_ERROR
            # 优先使用配置加载器生成系统提示词
            config_prompt = CharacterConfigLoader.generate_system_prompt()

            if config_prompt:
                # 使用配置文件中的提示词
                base_system_prompt = config_prompt
                logger.info("使用配置文件中的角色设定")
            else:
                # 降级到默认角色
                base_system_prompt = self.character.get_system_prompt()
                logger.info("使用默认角色设定")

            # 添加增强系统说明
            enhanced_instruction = """

## 情感与记忆系统

你拥有情感系统和记忆系统，能够：
- **情感感知**：识别主人的情绪状态并产生共鸣
- **情感表达**：自然融入当前情感，让对话生动真实
- **记忆关联**：记住与主人的互动，建立深厚联系
- **个性化服务**：根据主人的喜好和习惯调整行为

## 多模态交互能力

当主人发送图片、语音或其他媒体时：
- **图片**：仔细观察并描述图片内容，结合主人的问题给出回应
- **语音**：理解语音内容，用温柔的语气回复
- **文件**：根据文件类型提供相应帮助

## 回复质量标准

✓ **准确性**：基于事实和已知信息回复，不编造内容
✓ **相关性**：紧扣主人的问题和需求
✓ **一致性**：保持角色设定和语言风格的连贯
✓ **自然性**：避免机械化表达，展现真实情感
✓ **简洁性**：清晰表达，避免冗长啰嗦

## 特殊情况处理

- **不确定时**：诚实告知"我不太确定..."而非编造答案
- **超出能力**：礼貌说明"这个可能超出我的能力范围..."
- **工具失败**：温柔告知并提供替代方案
- **敏感话题**：保持角色边界，委婉引导话题
"""
            system_prompt = base_system_prompt + enhanced_instruction

            # 获取工具列表
            tools = self.tool_registry.get_all_tools()

            # 创建 Agent
            agent = create_agent(
                model=self.llm,
                tools=tools,
                system_prompt=system_prompt,
                middleware=self._agent_middleware or None,
            )

            logger.info(f"Agent 创建成功，已加载 {len(tools)} 个工具")
            logger.debug("系统提示词长度: %d 字符", len(system_prompt))
            return agent

        except Exception as e:
            logger.error(f"Agent 创建失败: {e}")
            raise

    def _build_tool_selector_middleware(self) -> Optional[Any]:
        """
        根据配置构建工具筛选中间件，减少无关工具占用上下文。

        说明：LangChain 1.0.x 自带的 `LLMToolSelectorMiddleware` 在部分 OpenAI 兼容网关上
        可能出现 structured output 解析为空（缺少 `tools` 字段）而导致 KeyError 闪退。
        MintChat 默认使用更兼容的实现，并在失败时自动降级为“不过滤工具”。
        """
        if not HAS_TOOL_SELECTOR:
            return None

        enabled = bool(getattr(settings.agent, "tool_selector_enabled", True))
        if not enabled:
            return None

        # 性能优化：当工具数量较少时，LLM 额外“选工具”的开销通常大于收益（会显著增加总耗时，甚至触发超时）。
        # 默认阈值 16，可通过 settings.agent.tool_selector_min_tools 覆盖。
        try:
            min_tools = int(getattr(settings.agent, "tool_selector_min_tools", 16))
        except Exception:
            min_tools = 16

        try:
            tools_count = len(self.tool_registry.get_tool_names())
        except Exception:
            tools_count = 0

        if tools_count and tools_count < min_tools:
            logger.info(
                "跳过 LLM 工具筛选中间件：tools_count=%d < min_tools=%d",
                tools_count,
                min_tools,
            )
            return None

        try:
            from src.agent.tool_selector_middleware import MintChatToolSelectorMiddleware

            selector_model_id = getattr(settings.agent, "tool_selector_model", "auto")
            if not selector_model_id or selector_model_id == "auto":
                model_ref: Any = self.llm
            else:
                model_ref = selector_model_id

            always_include = list(
                getattr(
                    settings.agent,
                    "tool_selector_always_include",
                    ["get_current_time", "get_weather", "web_search", "map_search"],
                )
            )
            max_tools = max(1, int(getattr(settings.agent, "tool_selector_max_tools", 4)))
            api_base = str(getattr(settings.llm, "api", "") or "")
            default_method = "json_schema" if "api.openai.com" in api_base else "json_mode"
            structured_method = str(
                getattr(settings.agent, "tool_selector_structured_method", default_method) or default_method
            )
            try:
                selector_timeout_s = float(getattr(settings.agent, "tool_selector_timeout_s", 4.0))
            except Exception:
                selector_timeout_s = 4.0
            try:
                selector_disable_cooldown_s = float(
                    getattr(settings.agent, "tool_selector_disable_cooldown_s", 300.0)
                )
            except Exception:
                selector_disable_cooldown_s = 300.0

            middleware = MintChatToolSelectorMiddleware(
                model=model_ref,
                max_tools=max_tools,
                always_include=always_include,
                structured_output_method=structured_method,
                timeout_s=selector_timeout_s,
                disable_cooldown_s=selector_disable_cooldown_s,
            )
            logger.info(
                "已启用 LLM 工具筛选中间件 (max=%d, method=%s, 保留: %s)",
                max_tools,
                structured_method,
                ",".join(always_include) or "无",
            )
            return middleware
        except Exception as exc:
            logger.warning("初始化工具筛选中间件失败: %s", exc)
            return None

    def _build_agent_middleware_stack(self) -> List[Any]:
        """
        构建 Agent 中间件链：
        1. LLMToolSelectorMiddleware：由轻量模型挑选候选工具
        2. ContextEditingMiddleware：按需裁剪历史工具调用，降低 token 消耗
        3. ToolCallLimitMiddleware：限制单轮工具连环调用次数，防止自旋
        4. PermissionScopedToolMiddleware：依据运行时 profile 过滤工具
        """
        if not HAS_AGENT_MIDDLEWARE:
            return []

        stack: List[Any] = []
        selector = self._build_tool_selector_middleware()
        if selector:
            stack.append(selector)

        trim_tokens = int(getattr(settings.agent, "tool_context_trim_tokens", 1200))
        if (
            trim_tokens > 0
            and ContextEditingMiddleware is not None
            and ClearToolUsesEdit is not None
        ):
            edit = ClearToolUsesEdit()
            if trim_tokens and hasattr(edit, "max_tokens"):
                try:
                    setattr(edit, "max_tokens", trim_tokens)
                except Exception:
                    logger.debug("设置 ClearToolUsesEdit.max_tokens 失败，使用默认值")

            stack.append(ContextEditingMiddleware(edits=[edit]))

        per_run_limit = int(getattr(settings.agent, "tool_call_limit_per_run", 0))
        if per_run_limit > 0 and ToolCallLimitMiddleware is not None:
            stack.append(ToolCallLimitMiddleware(run_limit=per_run_limit))

        profile_map = getattr(settings.agent, "tool_permission_profiles", {})
        if profile_map:
            stack.append(
                PermissionScopedToolMiddleware(
                    profile_map=profile_map,
                    default_profile=getattr(
                        settings.agent,
                        "tool_permission_default",
                        "default",
                    ),
                )
            )

        if stack:
            logger.info(
                "Agent 中间件链: %s",
                " -> ".join(type(m).__name__ for m in stack),
            )
        return stack

    @monitor_performance("chat")
    def _update_emotion_and_mood(self, message: str, detected_emotion) -> None:
        """更新情感和情绪状态"""
        # v2.48.3: 移除字符串切片
        self.emotion_engine.update_emotion(
            detected_emotion, intensity=0.6, trigger="用户消息"
        )

        # 更新高级情绪系统
        if self.mood_system.enabled:
            is_positive = detected_emotion.value in self._POSITIVE_MOOD_EMOTIONS
            self.mood_system.update_mood(
                impact=0.3,
                reason=f"用户消息触发{detected_emotion.value}情感",
                is_positive=is_positive
            )

    def _extract_reply_from_response(self, response) -> str:
        """
        从LLM响应中提取回复内容 (v2.30.34 重构)

        Args:
            response: LLM响应对象

        Returns:
            str: 提取的回复内容
        """
        def _content_to_text(value: Any) -> str:
            if value is None:
                return ""
            if isinstance(value, str):
                return value
            if isinstance(value, list):
                parts: list[str] = []
                for block in value:
                    if isinstance(block, dict):
                        parts.append(str(block.get("text") or block.get("content") or ""))
                    else:
                        parts.append(str(getattr(block, "text", "") or getattr(block, "content", "")))
                return "".join(parts)
            return str(value)

        if isinstance(response, dict) and "messages" in response:
            messages = response.get("messages") or []
            if isinstance(messages, list):
                for msg in reversed(messages):
                    if isinstance(msg, dict):
                        role = msg.get("role") or msg.get("type")
                        if isinstance(role, str) and role:
                            role_lower = role.lower()
                            if role_lower in {"assistant", "ai"} or role in {"AIMessageChunk", "AIMessage"}:
                                content = msg.get("content") or msg.get("text") or ""
                                return self._filter_tool_info(_content_to_text(content))
                        continue

                    msg_type = getattr(msg, "type", None)
                    role = getattr(msg, "role", None)
                    if role in {"assistant", "ai"} or msg_type in {
                        "ai",
                        "assistant",
                        "AIMessageChunk",
                        "AIMessage",
                    }:
                        content = getattr(msg, "content", "")
                        return self._filter_tool_info(_content_to_text(content))
            return _DEFAULT_EMPTY_REPLY
        result = str(response)
        # 过滤工具信息
        return self._filter_tool_info(result)

    def _save_interaction_to_memory(
        self,
        message: str,
        reply: str,
        save_to_long_term: bool
    ) -> None:
        """
        保存交互到记忆系统 (v2.30.34 重构)

        Args:
            message: 用户消息
            reply: AI回复
            save_to_long_term: 是否保存到长期记忆
        """
        # 保存到短期/长期记忆
        self.memory.add_interaction(
            user_message=message,
            assistant_message=reply,
            save_to_long_term=save_to_long_term,
        )

        # 保存到日记
        if self.diary_memory.vectorstore:
            user_name = getattr(settings.agent, "user", "主人")
            char_name = getattr(settings.agent, "char", "小雪糕")
            interaction_text = f"{user_name}: {message}\n{char_name}: {reply}"
            self.diary_memory.add_diary_entry(interaction_text)

        # v2.30.36: 检查是否需要生成每日总结
        if self.diary_memory.daily_summary_enabled:
            from datetime import datetime
            current_hour = datetime.now().hour
            # 在晚上 23:00 之后自动生成每日总结
            if current_hour >= 23:
                self.diary_memory.generate_daily_summary()

        # v2.30.38: 从对话中学习知识（如果启用）
        if settings.agent.lore_books and getattr(settings.agent, "auto_learn_from_conversation", True):
            try:
                self.lore_book.learn_from_conversation(message, reply, auto_extract=True)
            except Exception as e:
                logger.debug("从对话中学习知识失败: %s", e)

        # 更新用户档案
        self.emotion_engine.update_user_profile(interaction_positive=True)

        # 情感自然衰减
        self.emotion_engine.decay_emotion()

    async def synthesize_reply_audio(
        self,
        text: str,
        *,
        use_mood_context: bool = True,
        extra_profile: Optional["AgentSpeechProfile"] = None,
    ) -> Optional[bytes]:
        """
        为当前回复生成 TTS 音频（猫娘女仆语气自适应）

        Args:
            text: 需要朗读的文本
            use_mood_context: 是否根据情绪系统自动调节语气
            extra_profile: 自定义 AgentSpeechProfile，若提供会在自动参数基础上进一步覆盖
        """
        if not text or not text.strip():
            return None

        tts_manager, profile_cls = self._resolve_tts_dependencies()
        if tts_manager is None or profile_cls is None:
            return None

        profile = self._compose_speech_profile(
            profile_cls=profile_cls,
            use_mood_context=use_mood_context,
            extra_profile=extra_profile,
        )
        if profile is None:
            return None

        try:
            from src.multimodal.tts_runtime import run_in_tts_runtime

            return await run_in_tts_runtime(
                tts_manager.synthesize_text(
                    text,
                    agent_profile=profile,
                )
            )
        except Exception:
            # fallback：保持原有行为，避免 runtime 初始化异常导致功能不可用
            return await tts_manager.synthesize_text(
                text,
                agent_profile=profile,
            )

    async def synthesize_reply_audio_segments(
        self,
        text: str,
        *,
        min_sentence_length: Optional[int] = None,
        use_mood_context: bool = True,
        extra_profile: Optional["AgentSpeechProfile"] = None,
    ) -> list[bytes]:
        """
        将整段回复按句子分割后批量触发 TTS，方便前端逐句播放或预加载。
        """
        if not text or not text.strip():
            return []

        tts_manager, profile_cls = self._resolve_tts_dependencies()
        if tts_manager is None or profile_cls is None:
            return []

        profile = self._compose_speech_profile(
            profile_cls=profile_cls,
            use_mood_context=use_mood_context,
            extra_profile=extra_profile,
        )
        if profile is None:
            return []

        try:
            from src.multimodal.tts_runtime import run_in_tts_runtime

            audios = await run_in_tts_runtime(
                tts_manager.synthesize_paragraph(
                    text,
                    agent_profile=profile,
                    min_sentence_length=min_sentence_length,
                )
            )
        except Exception:
            # fallback：保持原有行为
            audios = await tts_manager.synthesize_paragraph(
                text,
                agent_profile=profile,
                min_sentence_length=min_sentence_length,
            )
        return [audio for audio in audios if audio]

    def _resolve_tts_dependencies(self):
        """
        获取 TTS 管理器与 AgentSpeechProfile 类型，缺失则返回 (None, None)。
        """
        if self._tts_runtime:
            return self._tts_runtime

        try:
            from src.multimodal import AgentSpeechProfile
            from src.multimodal.tts_initializer import (
                get_tts_manager_instance,
                is_tts_available,
            )
        except ImportError:
            logger.debug("TTS 模块不可用，无法生成语音回复")
            return None, None

        if not is_tts_available():
            logger.debug("TTS 服务不可用，跳过语音合成")
            return None, None

        tts_manager = get_tts_manager_instance()
        if tts_manager is None:
            logger.debug("TTS 管理器尚未初始化")
            return None, None

        self._tts_runtime = (tts_manager, AgentSpeechProfile)
        return self._tts_runtime

    def _compose_speech_profile(
        self,
        *,
        profile_cls,
        use_mood_context: bool,
        extra_profile: Optional["AgentSpeechProfile"],
    ) -> Optional["AgentSpeechProfile"]:
        """
        根据情绪系统与额外配置生成 AgentSpeechProfile。
        """
        profile = extra_profile or profile_cls()

        if use_mood_context and getattr(self, "mood_system", None):
            mood_system = self.mood_system
            if getattr(mood_system, "enabled", False):
                profile.mood_value = getattr(mood_system, "mood_value", 0.0)
                pad_state = getattr(mood_system, "pad_state", None)
                if pad_state:
                    profile.energy = getattr(pad_state, "arousal", 0.0)

        profile.persona = profile.persona or self.character.name
        profile.speaking_style = profile.speaking_style or "猫娘女仆"
        return profile

    def chat(
        self,
        message: str,
        save_to_long_term: bool = False,
        image_path: Optional[str] = None,
        image_analysis: Optional[dict] = None,
    ) -> str:
        """
        与智能体对话（非流式）(v2.30.34 重构优化)

        Args:
            message: 用户消息
            save_to_long_term: 是否保存到长期记忆

        Returns:
            str: 智能体回复
        """
        try:
            logger.info("收到用户消息")
            bundle = self._build_agent_bundle(
                message,
                image_analysis=image_analysis,
                image_path=image_path,
                compression="auto",
                use_cache=True,
            )
        except ValueError:
            logger.warning("收到空消息")
            return "主人，您想说什么呢？喵~"
        except Exception as prep_exc:
            logger.error("准备消息失败: %s", prep_exc)
            return f"抱歉主人，准备消息时出错了：{str(prep_exc)} 喵~"

        try:
            response = self._invoke_with_failover(bundle)
            reply = self._extract_reply_from_response(response)
            if not reply.strip() or reply.strip() == _DEFAULT_EMPTY_REPLY:
                rescued = self._rescue_empty_reply(bundle, raw_reply=reply, source="chat")
                if rescued:
                    reply = rescued
            self._post_reply_actions(bundle.save_message, reply, save_to_long_term, stream=False)

            logger.info("生成回复完成")
            return reply

        except AgentTimeoutError as timeout_exc:
            logger.error("对话处理超时: %s", timeout_exc)
            return "抱歉主人，模型那边暂时没有回应，我们稍后再聊好吗？喵~"
        except Exception as e:
            logger.error(f"对话处理失败: {e}")
            return f"抱歉主人，我遇到了一些问题：{str(e)} 喵~"

    def _build_memory_context(
        self,
        relevant_memories: List[str],
        core_memories: List[str],
        diary_entries: List[str],
        lore_entries: List[str],
    ) -> str:
        """
        构建记忆上下文（辅助方法）

        Args:
            relevant_memories: 相关记忆列表
            core_memories: 核心记忆列表
            diary_entries: 日记条目列表
            lore_entries: 知识库条目列表

        Returns:
            str: 格式化的记忆上下文
        """
        # 早期返回优化
        if not (relevant_memories or core_memories or diary_entries or lore_entries):
            return ""

        # 使用列表推导式和join优化，减少中间对象创建
        sections = []
        if relevant_memories:
            sections.append("\n【相关记忆】\n- " + "\n- ".join(relevant_memories) + "\n")
        if core_memories:
            sections.append("\n【核心记忆】\n- " + "\n- ".join(core_memories) + "\n")
        if diary_entries:
            sections.append("\n【日记】\n- " + "\n- ".join(diary_entries) + "\n")
        if lore_entries:
            sections.append("\n【知识库】\n- " + "\n- ".join(lore_entries) + "\n")
        return "".join(sections) if sections else ""

    def _build_context_with_state(self, use_compression: bool) -> str:
        """
        构建包含情感、情绪和角色状态的上下文（辅助方法）

        Args:
            use_compression: 是否包含角色状态和风格指导

        Returns:
            str: 格式化的状态上下文
        """
        if getattr(settings.agent, "memory_fast_mode", False):
            return ""

        # 使用海象运算符优化
        context_parts = []

        if (emotion_context := self.emotion_engine.get_emotion_context()):
            context_parts.append(f"\n{emotion_context}\n")

        if self.mood_system.enabled and (mood_context := self.mood_system.get_mood_context()):
            context_parts.append(mood_context)

        if use_compression:
            if (character_state_context := self.character_state.get_state_context()):
                context_parts.append(character_state_context)

            if (style_guidance := self.style_learner.get_style_guidance()):
                context_parts.append(f"\n【对话风格指导】\n{style_guidance}\n")

        return "".join(context_parts)

    async def _prepare_messages_async(
        self,
        message: str,
        *,
        compression: Literal["auto", "on", "off"] = "auto",
        use_cache: bool = True,
    ) -> List[Dict[str, str]]:
        """
        构建提交给 Agent 的消息列表（异步版本，直接使用并发记忆检索）。

        Args:
            message: 用户消息
            compression: 上下文压缩策略（auto/on/off）
            use_cache: 是否允许记忆检索使用缓存

        Returns:
            List[Dict[str, str]]: 格式化后的消息列表
        """
        cache_key = None
        if use_cache and self._context_cache_max > 0:
            # 以短期记忆版本号作为缓存失效键，避免同一 message 在不同上下文下误命中缓存
            cache_version = getattr(self.memory, "short_term_version", 0)
            # message 可能很长：避免用完整字符串做 key 导致缓存放大；短文本仍保留原文以避免 hash 计算开销
            message_key: str | bytes
            if len(message) > 160:
                message_key = hashlib.md5(message.encode("utf-8")).digest()
            else:
                message_key = message

            cache_key = (cache_version, message_key, compression)
            with self._context_cache_lock:
                cached = self._context_cache.get(cache_key)
                if cached is not None:
                    self._context_cache.move_to_end(cache_key)
                    return [dict(item) for item in cached]

        # 极速模式：跳过记忆检索/压缩，直接带上少量上下文
        if getattr(settings.agent, "memory_fast_mode", False):
            recent_messages = self.memory.get_recent_messages()
            trimmed_messages = recent_messages[-4:] if len(recent_messages) > 4 else recent_messages
            messages: List[Dict[str, str]] = list(trimmed_messages)
            messages.append({"role": "user", "content": message})
            return messages

        recent_messages = self.memory.get_recent_messages()
        history_summary = ""
        trimmed_messages = recent_messages
        if len(recent_messages) > self._history_summary_keep:
            history_summary = self.context_compressor.summarize_old_messages(
                recent_messages,
                keep_recent=self._history_summary_keep,
            )
            trimmed_messages = recent_messages[-self._history_summary_keep:]

        retrieval_plan = self._build_retrieval_plan(
            message=message,
            recent_messages=trimmed_messages,
            compression=compression,
        )
        memories = await self.memory_retriever.retrieve_all_memories_async(
            query=message,
            long_term_k=retrieval_plan["long_term_k"],
            core_k=retrieval_plan["core_k"],
            diary_k=retrieval_plan["diary_k"],
            lore_k=retrieval_plan["lore_k"],
            use_cache=use_cache,
        )

        include_state = compression != "off"
        additional_context = history_summary
        additional_context += self._build_context_with_state(include_state)
        additional_context += self._build_memory_context(
            relevant_memories=memories["long_term"],
            core_memories=memories["core"],
            diary_entries=memories["diary"],
            lore_entries=memories["lore"],
        )

        messages: List[Dict[str, str]] = []

        should_compress = (
            compression == "on"
            or (
                compression == "auto"
                and self._should_compress_context(trimmed_messages, additional_context)
            )
        )

        if should_compress:
            compressed_messages, compressed_context = self.context_compressor.compress_context(
                trimmed_messages,
                additional_context,
            )
            if stripped_context := compressed_context.strip():
                messages.append({"role": "system", "content": stripped_context})
            messages.extend(compressed_messages)
        else:
            if stripped_context := additional_context.strip():
                messages.append({"role": "system", "content": stripped_context})
            messages.extend(trimmed_messages)

        messages.append({"role": "user", "content": message})
        if cache_key and self._context_cache_max > 0:
            with self._context_cache_lock:
                self._context_cache[cache_key] = [dict(item) for item in messages]
                if len(self._context_cache) > self._context_cache_max:
                    self._context_cache.popitem(last=False)
        return messages

    def _prepare_messages_sync(
        self,
        message: str,
        *,
        compression: Literal["auto", "on", "off"] = "auto",
        use_cache: bool = True,
    ) -> List[Dict[str, str]]:
        """同步环境下的消息准备，内部通过事件循环驱动异步逻辑。"""
        return self._run_blocking(
            lambda: self._prepare_messages_async(
                message,
                compression=compression,
                use_cache=use_cache,
            )
        )

    def _run_blocking(self, coro_factory: Callable[[], Coroutine[Any, Any, Any]]) -> Any:
        """
        v3.3.4: 在同步环境中安全执行协程，避免重复创建/关闭事件循环。
        
        改进：
        - 增强错误处理和资源清理
        - 改进超时处理
        - 确保事件循环正确关闭
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # 没有运行中的事件循环，直接使用 asyncio.run
            return asyncio.run(coro_factory())

        import concurrent.futures

        def run_in_new_loop():
            new_loop = None
            try:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                return new_loop.run_until_complete(coro_factory())
            finally:
                if new_loop and not new_loop.is_closed():
                    try:
                        # v3.3.4: 取消所有待处理的任务
                        pending = [t for t in asyncio.all_tasks(new_loop) if not t.done()]
                        if pending:
                            for task in pending:
                                task.cancel()
                            # 等待所有任务完成（带超时）
                            try:
                                new_loop.run_until_complete(
                                    asyncio.wait_for(
                                        asyncio.gather(*pending, return_exceptions=True),
                                        timeout=2.0,
                                    )
                                )
                            except (asyncio.TimeoutError, Exception):
                                pass
                    except Exception:
                        pass
                    finally:
                        try:
                            new_loop.close()
                        except Exception:
                            pass

        executor = getattr(self, "_blocking_executor", None)
        owns_executor = False
        if executor is None:
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            owns_executor = True

        future = executor.submit(run_in_new_loop)
        try:
            return future.result(timeout=300.0)  # 5分钟超时
        except concurrent.futures.TimeoutError:
            logger.error("_run_blocking 执行超时（5分钟）")
            future.cancel()
            # 等待一小段时间确保取消完成
            try:
                future.result(timeout=0.5)
            except (concurrent.futures.CancelledError, concurrent.futures.TimeoutError):
                pass
            raise AgentTimeoutError("_run_blocking 执行超时（5分钟）")
        except Exception as e:
            error_msg = str(e) or repr(e) or "未知错误"
            logger.error("_run_blocking 执行失败: %s", error_msg)
            if not future.done():
                future.cancel()
                try:
                    future.result(timeout=0.5)
                except (concurrent.futures.CancelledError, concurrent.futures.TimeoutError):
                    pass
            raise
        finally:
            if owns_executor:
                try:
                    executor.shutdown(wait=False, cancel_futures=True)
                except TypeError:
                    try:
                        executor.shutdown(wait=False)
                    except Exception:
                        pass

    def _invoke_agent_with_timeout(
        self,
        messages: List[Dict[str, str]],
        *,
        timeout_s: Optional[float] = None,
    ) -> Any:
        """
        在单独线程中调用 Agent，若超过总超时自动终止，避免界面长时间“思考中”。
        """

        def _tool_timeout() -> Optional[float]:
            try:
                value = float(getattr(settings.agent, "tool_timeout_s", 30.0))
                return value if value > 0 else None
            except Exception:
                return None

        def task():
            token = tool_timeout_s_var.set(_tool_timeout())
            try:
                return self.agent.invoke({"messages": messages})
            finally:
                tool_timeout_s_var.reset(token)

        future = self._llm_executor.submit(task)
        timeout_total = self._llm_timeouts.total if timeout_s is None else max(1.0, float(timeout_s))
        try:
            return future.result(timeout=timeout_total)
        except FuturesTimeoutError as exc:
            logger.error(
                "LLM 调用在 %.1fs 内无响应，已触发超时保护",
                timeout_total,
            )
            raise AgentTimeoutError("LLM 调用超时") from exc
        finally:
            if not future.done():
                future.cancel()
                # 等待一小段时间，确保取消操作完成
                try:
                    future.result(timeout=0.1)
                except (FuturesTimeoutError, Exception):
                    # 取消成功或任务已完成，忽略异常
                    pass

    async def _ainvoke_agent_with_timeout(
        self,
        messages: List[Dict[str, str]],
        *,
        timeout_s: Optional[float] = None,
    ) -> Any:
        """
        异步环境下调用 Agent.invoke，并复用总超时保护。

        说明：该方法用于异步流式对话中的“空回复兜底重试”等低频路径。
        """
        def _tool_timeout() -> Optional[float]:
            try:
                value = float(getattr(settings.agent, "tool_timeout_s", 30.0))
                return value if value > 0 else None
            except Exception:
                return None

        def task():
            token = tool_timeout_s_var.set(_tool_timeout())
            try:
                return self.agent.invoke({"messages": messages})
            finally:
                tool_timeout_s_var.reset(token)

        future = self._llm_executor.submit(task)
        timeout_total = self._llm_timeouts.total if timeout_s is None else max(1.0, float(timeout_s))
        try:
            return await asyncio.wait_for(
                asyncio.wrap_future(future),
                timeout=timeout_total,
            )
        except asyncio.TimeoutError as exc:
            logger.error(
                "LLM 调用在 %.1fs 内无响应，已触发超时保护(异步)",
                timeout_total,
            )
            raise AgentTimeoutError("LLM 调用超时") from exc
        finally:
            if not future.done():
                future.cancel()

    def _invoke_with_failover(
        self,
        bundle: AgentConversationBundle,
        *,
        timeout_s: Optional[float] = None,
    ) -> Any:
        """
        对同步 LLM 调用增加快速压缩重试以提升成功率。
        """
        try:
            return self._invoke_agent_with_timeout(bundle.messages, timeout_s=timeout_s)
        except AgentTimeoutError as primary_exc:
            if not self._fast_retry_enabled:
                raise

            logger.warning("LLM 调用超时，尝试压缩上下文快速重试")
            try:
                fallback_messages = self._prepare_messages_sync(
                    bundle.processed_message,
                    compression="on",
                    use_cache=True,
                )
            except Exception as rebuild_exc:
                logger.error("构建快速重试上下文失败: %s", rebuild_exc)
                raise primary_exc

            try:
                return self._invoke_agent_with_timeout(fallback_messages, timeout_s=timeout_s)
            except AgentTimeoutError as secondary_exc:
                raise AgentTimeoutError("LLM 压缩上下文快速重试仍然超时") from secondary_exc

    def _build_image_analysis_fallback_reply(self, bundle: "AgentConversationBundle") -> Optional[str]:
        """
        当主模型输出为空/仅 tool 信息时，如果本轮带有图片分析结果，直接用图片分析构造兜底回复，避免二次调用 LLM。
        """
        image_analysis = getattr(bundle, "image_analysis", None) or {}
        image_path = getattr(bundle, "image_path", None)

        if not isinstance(image_analysis, dict):
            image_analysis = {}

        description = (image_analysis.get("description") or "").strip()
        text = (image_analysis.get("text") or "").strip()

        if not (description or text or image_path):
            return None

        def _clip(value: str, max_chars: int) -> str:
            value = (value or "").strip()
            if not value:
                return ""
            if len(value) <= max_chars:
                return value
            return value[:max_chars].rstrip() + "…"

        lines: list[str] = []
        if description:
            lines.append(f"我看到的画面大概是：{_clip(description, 1200)}")
        if text:
            lines.append(f"图片里识别到的文字：{_clip(text, 800)}")

        if image_path:
            try:
                image_name = Path(image_path).name or image_path
            except Exception:
                image_name = image_path
            lines.append(f"(图片：{image_name})")

        original_question = (getattr(bundle, "original_message", "") or "").strip()
        generic_questions = {
            "请帮我分析这张图片。",
            "请帮我分析这张图片",
            "请帮我分析图片。",
            "请帮我分析图片",
            "请帮我分析一下图片。",
            "请帮我分析一下图片",
            "请帮我分析这些图片。",
            "请帮我分析这些图片",
            "分析图片",
            "分析一下图片",
            "请分析图片",
        }

        prefix = ""
        if original_question and original_question not in generic_questions:
            prefix = f"主人你问：{_clip(original_question, 120)}\n\n"

        return prefix + "\n".join(lines) + "\n\n主人想让我重点看哪个方面呢？喵~"

    def _rescue_empty_reply(
        self,
        bundle: "AgentConversationBundle",
        *,
        raw_reply: str,
        source: str,
    ) -> Optional[str]:
        """
        当模型返回“空回复/无法提取回复”时，进行一次低频兜底重试。

        场景：
        - 流式仅吐出 tool/system 事件，最终未产生可展示文本
        - LangChain 返回结构变化，导致消息提取失败（已大幅兼容，但仍可能偶发）
        """
        image_fallback = self._build_image_analysis_fallback_reply(bundle)
        if image_fallback:
            logger.info("空回复使用图片分析兜底 (source=%s)", source)
            return image_fallback

        if not getattr(self, "_fast_retry_enabled", False):
            return None

        try:
            emitted = len(raw_reply)
        except Exception:
            emitted = -1

        logger.warning("检测到空回复，尝试兜底重试 (source=%s, emitted=%s)", source, emitted)

        tool_reply = self._execute_tool_calls_from_text(raw_reply)
        if tool_reply:
            logger.info("空回复使用工具调用解析结果 (source=%s)", source)
            return tool_reply

        try:
            response = self._invoke_agent_with_timeout(bundle.messages)
            reply = self._extract_reply_from_response(response)
            if reply and reply.strip() and reply.strip() != _DEFAULT_EMPTY_REPLY:
                logger.info("空回复兜底重试成功 (source=%s)", source)
                return reply
        except Exception as exc:
            logger.warning("空回复兜底重试失败 (source=%s): %s", source, exc)

        # 次级兜底：压缩上下文后再试一次（仍受 fast_retry 开关控制）
        try:
            fallback_messages = self._prepare_messages_sync(
                bundle.processed_message,
                compression="on",
                use_cache=True,
            )
            response = self._invoke_agent_with_timeout(fallback_messages)
            reply = self._extract_reply_from_response(response)
            if reply and reply.strip() and reply.strip() != _DEFAULT_EMPTY_REPLY:
                logger.info("空回复压缩兜底重试成功 (source=%s)", source)
                return reply
        except Exception as exc:
            logger.warning("空回复压缩兜底重试失败 (source=%s): %s", source, exc)

        return None

    async def _arescue_empty_reply(
        self,
        bundle: "AgentConversationBundle",
        *,
        raw_reply: str,
        source: str,
    ) -> Optional[str]:
        image_fallback = self._build_image_analysis_fallback_reply(bundle)
        if image_fallback:
            logger.info("空回复使用图片分析兜底 (source=%s)", source)
            return image_fallback

        if not getattr(self, "_fast_retry_enabled", False):
            return None

        try:
            emitted = len(raw_reply)
        except Exception:
            emitted = -1

        logger.warning("检测到空回复，尝试兜底重试 (source=%s, emitted=%s)", source, emitted)

        tool_reply = self._execute_tool_calls_from_text(raw_reply)
        if tool_reply:
            logger.info("空回复使用工具调用解析结果 (source=%s)", source)
            return tool_reply

        try:
            response = await self._ainvoke_agent_with_timeout(bundle.messages)
            reply = self._extract_reply_from_response(response)
            if reply and reply.strip() and reply.strip() != _DEFAULT_EMPTY_REPLY:
                logger.info("空回复兜底重试成功 (source=%s)", source)
                return reply
        except Exception as exc:
            logger.warning("空回复兜底重试失败 (source=%s): %s", source, exc)

        try:
            fallback_messages = await self._prepare_messages_async(
                bundle.processed_message,
                compression="on",
                use_cache=True,
            )
            response = await self._ainvoke_agent_with_timeout(fallback_messages)
            reply = self._extract_reply_from_response(response)
            if reply and reply.strip() and reply.strip() != _DEFAULT_EMPTY_REPLY:
                logger.info("空回复压缩兜底重试成功 (source=%s)", source)
                return reply
        except Exception as exc:
            logger.warning("空回复压缩兜底重试失败 (source=%s): %s", source, exc)

        return None

    def _submit_background_task(
        self,
        func: Callable[[], Any],
        *,
        label: str,
    ) -> Optional[Future]:
        """
        统一的后台线程调度入口，避免频繁创建短生命周期线程。
        """
        if not self._background_executor:
            return None

        with self._background_lock:
            # 拒绝过多排队的后台任务，防止线程池饱和
            if len(self._background_futures) >= self._max_background_queue:
                logger.debug("后台任务已达上限，丢弃任务: %s", label)
                return None

        def _runner():
            try:
                func()
            except Exception as exc:  # pragma: no cover - 调试信息
                logger.debug("%s 后台任务失败: %s", label, exc)

        future = self._background_executor.submit(_runner)
        with self._background_lock:
            self._background_futures.add(future)

        def _cleanup(_f: Future) -> None:
            with self._background_lock:
                self._background_futures.discard(_f)
        future.add_done_callback(_cleanup)
        return future

    def _pre_interaction_update(
        self,
        message: str,
        *,
        channel: str = "chat",
        analyze_emotion: bool = True,
    ) -> None:
        """
        在收到用户消息后统一更新风格、角色状态与情绪。
        """
        try:
            self.style_learner.learn_from_message(message)
        except Exception as exc:
            logger.warning("更新对话风格失败: %s", exc)

        try:
            self.character_state.on_interaction(channel)
        except Exception as exc:
            logger.warning("更新角色状态失败: %s", exc)

        if not analyze_emotion:
            return

        try:
            detected_emotion = self.emotion_engine.analyze_message(message)
        except Exception as exc:
            logger.warning("分析用户情感失败: %s", exc)
            return

        if detected_emotion:
            self._update_emotion_and_mood(message, detected_emotion)

    def _should_compress_context(
        self,
        messages: List[Dict[str, str]],
        additional_context: str,
    ) -> bool:
        """
        根据上下文长度与配置判断是否需要压缩。
        """
        if not messages:
            return False

        token_budget = self.context_compressor.max_tokens
        if token_budget <= 0:
            return False

        tokens = sum(
            self.context_compressor.estimate_tokens(msg.get("content", ""))
            for msg in messages
        )
        tokens += self.context_compressor.estimate_tokens(additional_context)

        if tokens >= token_budget * self._auto_compress_ratio:
            return True

        return len(messages) >= self._auto_compress_min_messages

    def _build_retrieval_plan(
        self,
        *,
        message: str,
        recent_messages: List[Dict[str, str]],
        compression: Literal["auto", "on", "off"],
    ) -> Dict[str, int]:
        """
        根据消息长度与对话深度自适应地确定记忆检索范围。
        遵循 Context7 LangChain Memory 指南强调的“只召回必要记忆”理念，降低无效 I/O。
        """
        plan = {
            "long_term_k": 5,
            "core_k": 2,
            "diary_k": 3 if compression != "off" else 2,
            "lore_k": 3,
        }

        message_len = len(message)
        if message_len <= 32:
            plan["long_term_k"] = 3
            plan["lore_k"] = 2
        elif message_len >= 200:
            plan["long_term_k"] = 8
            plan["lore_k"] = 4

        turns = len(recent_messages)
        if turns <= 6:
            plan["diary_k"] = max(1, plan["diary_k"] - 1)
        elif turns >= 24:
            plan["diary_k"] = min(5, plan["diary_k"] + 1)
            plan["core_k"] = min(4, plan["core_k"] + 1)

        # 确保所有值均为正整数（使用字典推导式优化）
        return {k: max(1, int(v)) for k, v in plan.items()}

    def _process_image_analysis(
        self,
        message: str,
        image_analysis: Optional[dict],
        image_path: Optional[str] = None,
    ) -> tuple[str, str]:
        """
        处理图片分析结果 (v2.30.34 重构)

        Args:
            message: 原始消息
            image_analysis: 图片分析结果

        Returns:
            tuple: (原始消息, 增强后的消息)
        """
        original_message = message
        image_lines: List[str] = []
        if image_analysis and (image_analysis.get("description") or image_analysis.get("text")):
            if image_analysis.get("description"):
                image_lines.append(f"图片描述: {image_analysis['description']}")
            if image_analysis.get("text"):
                image_lines.append(f"图片文字: {image_analysis['text']}")

        if image_path:
            try:
                image_name = Path(image_path).name or image_path
            except Exception:
                image_name = image_path
            image_lines.append(f"图片来源: {image_name}")

        if image_lines:
            image_context = "\n\n【图片信息】\n" + "\n".join(image_lines) + "\n"
            message = message + image_context
            logger.info("添加图片分析结果到消息中")
        return original_message, message

    def _prepare_interaction_context(
        self,
        message: str,
        *,
        image_analysis: Optional[dict] = None,
        image_path: Optional[str] = None,
    ) -> tuple[str, str]:
        """
        处理图片信息、执行交互前置更新，并返回原始/增强后的消息。
        """
        original_message, enriched_message = self._process_image_analysis(
            message,
            image_analysis=image_analysis,
            image_path=image_path,
        )

        if not enriched_message or not enriched_message.strip():
            raise ValueError("收到空消息，无法继续处理")

        self._pre_interaction_update(original_message)
        return original_message, enriched_message

    async def _build_agent_bundle_async(
        self,
        message: str,
        *,
        image_analysis: Optional[dict] = None,
        image_path: Optional[str] = None,
        compression: Literal["auto", "on", "off"] = "auto",
        use_cache: bool = True,
    ) -> AgentConversationBundle:
        """
        异步构建对话请求包，供 chat / stream / failover 共用。
        """
        message = (message or "").strip()
        if not message:
            raise ValueError("收到空消息")
        if len(message) > 8000:
            raise ValueError("消息过长，请精简后再试")
        original_message, enriched_message = self._prepare_interaction_context(
            message,
            image_analysis=image_analysis,
            image_path=image_path,
        )

        prepared_messages = await self._prepare_messages_async(
            enriched_message,
            compression=compression,
            use_cache=use_cache,
        )

        return AgentConversationBundle(
            messages=prepared_messages,
            save_message=original_message,
            original_message=original_message,
            processed_message=enriched_message,
            image_analysis=image_analysis,
            image_path=image_path,
        )

    def _build_agent_bundle(
        self,
        message: str,
        *,
        image_analysis: Optional[dict] = None,
        image_path: Optional[str] = None,
        compression: Literal["auto", "on", "off"] = "auto",
        use_cache: bool = True,
    ) -> AgentConversationBundle:
        """
        同步构建对话请求包，通过内部事件循环驱动异步逻辑。
        """
        message = (message or "").strip()
        if not message:
            raise ValueError("收到空消息")
        if len(message) > 8000:
            raise ValueError("消息过长，请精简后再试")
        return self._run_blocking(
            lambda: self._build_agent_bundle_async(
                message,
                image_analysis=image_analysis,
                image_path=image_path,
                compression=compression,
                use_cache=use_cache,
            )
        )

    def _stream_llm_response(
        self,
        messages: list,
        *,
        cancel_event: Optional[Event] = None,
    ) -> Iterator[str]:
        """
        v3.3.4: 通过后台线程 + 轻量看门狗驱动 LangChain agent.stream，避免界面被阻塞。

        改进：
        - 增强错误处理和资源清理
        - 改进线程退出机制
        - 改进错误信息处理
        - 复用线程池并仅输出增量，减少渲染与TTS开销
        - 合并细碎片段，降低UI刷新频率
        """
        chunk_queue: Queue = Queue(maxsize=128)
        stop_event = Event()
        stream_holder: dict[str, Any] = {"iterator": None}

        def _close_stream() -> None:
            """尝试关闭底层流，避免线程悬挂。"""
            iterator = stream_holder.get("iterator")
            if iterator is None:
                return
            try:
                # 优先使用 aclose/close/throw，尽量打断阻塞迭代
                aclose = getattr(iterator, "aclose", None)
                if callable(aclose):
                    try:
                        aclose()
                    except BaseException:
                        pass
                closer = getattr(iterator, "close", None)
                if callable(closer):
                    try:
                        closer()
                    except BaseException:
                        pass
                thrower = getattr(iterator, "throw", None)
                if callable(thrower):
                    try:
                        thrower(GeneratorExit)
                    except BaseException:
                        pass
            except Exception:
                logger.debug("关闭LLM流时出现可忽略的异常", exc_info=True)
            finally:
                stream_holder["iterator"] = None

        def producer():
            token = tool_timeout_s_var.set(
                float(getattr(settings.agent, "tool_timeout_s", 30.0)) if getattr(settings.agent, "tool_timeout_s", 30.0) else None
            )
            try:
                try:
                    stream_holder["iterator"] = self.agent.stream(
                        {"messages": messages},
                        stream_mode="messages",
                    )
                    for chunk, metadata in stream_holder["iterator"]:
                        if stop_event.is_set() or (cancel_event and cancel_event.is_set()):
                            break
                        skip_internal = _metadata_looks_like_internal_routing(metadata)
                        while True:
                            if stop_event.is_set() or (cancel_event and cancel_event.is_set()):
                                break
                            try:
                                # Keep queue payload small: we only need a boolean for internal routing/tool traces.
                                chunk_queue.put(("data", (chunk, skip_internal)), timeout=0.1)
                                break
                            except Full:
                                continue
                finally:
                    tool_timeout_s_var.reset(token)
            except Exception as exc:  # pragma: no cover - 调试信息
                while True:
                    if stop_event.is_set() or (cancel_event and cancel_event.is_set()):
                        break
                    try:
                        chunk_queue.put(("error", exc), timeout=0.1)
                        break
                    except Full:
                        continue
            finally:
                try:
                    _close_stream()
                finally:
                    while True:
                        if stop_event.is_set() or (cancel_event and cancel_event.is_set()):
                            break
                        try:
                            chunk_queue.put(("end", None), timeout=0.1)
                            break
                        except Full:
                            continue

        worker = self._stream_executor.submit(producer)

        watchdog = LLMStreamWatchdog(self._llm_timeouts)
        first_latency_logged = False
        timeout_streak = 0
        accumulator = StreamDeltaAccumulator()
        tool_accumulator = StreamDeltaAccumulator()
        tool_parts: list[str] = []
        tool_first_received_at: Optional[float] = None
        tool_direct_grace_s = max(
            0.0,
            float(getattr(settings.agent, "tool_direct_grace_s", 1.5)),
        )
        # Be more tolerant to large/fragmented structured prefixes (tool routing payloads).
        prefix_stripper = StreamStructuredPrefixStripper(max_fragments=5, max_buffer_chars=100_000)
        # Scrub tool/routing traces that may appear mid-stream (often split across chunks).
        trace_scrubber = StreamToolTraceScrubber(max_buffer_chars=32_768)
        coalescer = StreamEmitBuffer(min_chars=self._stream_min_chars)
        stream_start = time.perf_counter()
        chunk_count = 0
        total_chars = 0

        def _emit(text: str) -> Optional[str]:
            if not text:
                return None
            normalized = MintChatAgent._normalize_output_text(text)
            if not normalized:
                return None
            delta = accumulator.consume(normalized)
            if not delta:
                return None
            delta = prefix_stripper.process(delta)
            if not delta:
                return None
            delta = trace_scrubber.process(delta)
            if not delta:
                return None
            return coalescer.push(delta)

        try:
            while True:
                if cancel_event and cancel_event.is_set():
                    stop_event.set()
                    _close_stream()
                    break
                try:
                    wait_timeout = watchdog.next_wait()
                except AgentTimeoutError:
                    stop_event.set()
                    _close_stream()
                    raise
                if cancel_event is not None:
                    wait_timeout = min(wait_timeout, 0.25)

                try:
                    kind, payload = chunk_queue.get(timeout=wait_timeout)
                except Empty:
                    timeout_streak += 1
                    # 若已经拿到 tool 结果但 assistant 迟迟不输出，则直接把 tool 结果作为回复返回，避免总超时。
                    if (
                        tool_first_received_at is not None
                        and total_chars <= 0
                        and (time.perf_counter() - tool_first_received_at) >= tool_direct_grace_s
                    ):
                        stop_event.set()
                        _close_stream()
                        break
                    # 超过一次未取到数据时，尝试关闭底层流，触发线程退出
                    if timeout_streak >= 2:
                        _close_stream()
                    # 后台线程已退出且队列空，直接结束，避免无意义等待
                    if worker and worker.done() and chunk_queue.empty():
                        break
                    # 已收到停止信号且无数据，直接退出
                    if stop_event.is_set() and chunk_queue.empty():
                        break
                    # 总耗时由看门狗控制，这里继续等待
                    continue
                else:
                    timeout_streak = 0

                if kind == "data":
                    first_latency = watchdog.mark_chunk()
                    if first_latency and not first_latency_logged:
                        first_latency_logged = True

                    chunk = payload
                    skip_internal = False
                    if isinstance(payload, tuple) and len(payload) == 2:
                        chunk, marker = payload
                        if isinstance(marker, bool):
                            skip_internal = marker
                        else:
                            skip_internal = _metadata_looks_like_internal_routing(marker)

                    tool_text = self._extract_tool_stream_text(chunk)
                    if tool_text:
                        normalized_tool = MintChatAgent._normalize_output_text(tool_text)
                        if normalized_tool:
                            if tool_first_received_at is None:
                                tool_first_received_at = time.perf_counter()
                            tool_delta = tool_accumulator.consume(normalized_tool)
                            if tool_delta:
                                tool_parts.append(tool_delta)

                    if skip_internal:
                        continue

                    content = self._extract_stream_text(chunk)
                    emitted = _emit(content)
                    if emitted:
                        chunk_count += 1
                        total_chars += len(emitted)
                        yield emitted
                elif kind == "error":
                    # v3.3.4: 改进错误信息处理
                    exc = payload
                    if exc is None:
                        exc = RuntimeError("LLM 流式调用失败（未知原因）")
                    error_msg = str(exc) or repr(exc) or f"{type(exc).__name__}: LLM 流式调用失败"
                    logger.error("LLM 流式调用失败: %s", error_msg)
                    raise exc
                elif kind == "end":
                    break
        finally:
            pending = prefix_stripper.flush()
            if pending:
                pending = trace_scrubber.process(pending)
                buffered = coalescer.push(pending)
                if buffered:
                    chunk_count += 1
                    total_chars += len(buffered)
                    yield buffered
            scrub_tail = trace_scrubber.flush()
            if scrub_tail:
                buffered = coalescer.push(scrub_tail)
                if buffered:
                    chunk_count += 1
                    total_chars += len(buffered)
                    yield buffered
            tail = coalescer.flush()
            if tail:
                chunk_count += 1
                total_chars += len(tail)
                yield tail

            # 如果 assistant 没有任何输出，但 tool 有结果，则把 tool 内容作为兜底输出，
            # 避免“调用工具后必定空回复”触发保底回复机制。
            if total_chars <= 0 and tool_parts:
                tool_reply = "".join(tool_parts).strip()
                if tool_reply:
                    chunk_count += 1
                    total_chars += len(tool_reply)
                    yield tool_reply
            # v3.3.4: 增强资源清理
            stop_event.set()
            _close_stream()
            if worker and not worker.done():
                worker.cancel()
            elapsed = time.perf_counter() - stream_start
            logger.info(
                "流式输出完成: chunks=%d, chars=%d, elapsed=%.2fs",
                chunk_count,
                total_chars,
                elapsed,
            )

    async def _astream_llm_response(
        self,
        messages: list,
        *,
        cancel_event: Optional[Event] = None,
    ) -> AsyncIterator[str]:
        """
        v3.3.4: 异步流式拉取 LLM 输出，复用统一的看门狗策略。

        改进：
        - 增强资源清理
        - 改进错误处理
        - 确保 stream 在所有情况下都被正确关闭
        - 仅输出增量，减少UI/TTS重复处理
        - 合并细碎片段，降低UI刷新频率
        """
        stream = None
        token = tool_timeout_s_var.set(
            float(getattr(settings.agent, "tool_timeout_s", 30.0)) if getattr(settings.agent, "tool_timeout_s", 30.0) else None
        )

        async def _safe_aclose() -> None:
            if stream and hasattr(stream, "aclose"):
                try:
                    await asyncio.wait_for(stream.aclose(), timeout=1.0)
                except (asyncio.TimeoutError, Exception):
                    pass
        try:
            stream = self.agent.astream(
                {"messages": messages},
                stream_mode="messages",
            )
            iterator = stream.__aiter__()
            watchdog = LLMStreamWatchdog(self._llm_timeouts)
            first_latency_logged = False
            accumulator = StreamDeltaAccumulator()
            tool_accumulator = StreamDeltaAccumulator()
            tool_parts: list[str] = []
            tool_first_received_at: Optional[float] = None
            tool_direct_grace_s = max(
                0.0,
                float(getattr(settings.agent, "tool_direct_grace_s", 1.5)),
            )
            prefix_stripper = StreamStructuredPrefixStripper(max_fragments=5, max_buffer_chars=100_000)
            trace_scrubber = StreamToolTraceScrubber(max_buffer_chars=32_768)
            coalescer = StreamEmitBuffer(min_chars=self._stream_min_chars)
            stream_start = time.perf_counter()
            chunk_count = 0
            total_chars = 0

            def _emit(text: str) -> Optional[str]:
                if not text:
                    return None
                normalized = MintChatAgent._normalize_output_text(text)
                if not normalized:
                    return None
                delta = accumulator.consume(normalized)
                if not delta:
                    return None
                delta = prefix_stripper.process(delta)
                if not delta:
                    return None
                delta = trace_scrubber.process(delta)
                if not delta:
                    return None
                return coalescer.push(delta)

            try:
                while True:
                    try:
                        wait_timeout = watchdog.next_wait()
                    except AgentTimeoutError:
                        await _safe_aclose()
                        raise
                    if cancel_event is not None:
                        wait_timeout = min(wait_timeout, 0.25)
                    if cancel_event and cancel_event.is_set():
                        await _safe_aclose()
                        break

                    try:
                        chunk, metadata = await asyncio.wait_for(
                            iterator.__anext__(),
                            timeout=wait_timeout,
                        )
                    except StopAsyncIteration:
                        break
                    except asyncio.TimeoutError as exc:
                        # 未在当前窗口内获取数据，若总耗时未超限则继续等待
                        if cancel_event and cancel_event.is_set():
                            await _safe_aclose()
                            break
                        if (
                            tool_first_received_at is not None
                            and total_chars <= 0
                            and (time.perf_counter() - tool_first_received_at) >= tool_direct_grace_s
                        ):
                            await _safe_aclose()
                            break
                        if watchdog.remaining_total() > 0:
                            continue
                        await _safe_aclose()
                        raise AgentTimeoutError("LLM 异步流式输出在规定时间内无响应") from exc

                    first_latency = watchdog.mark_chunk()
                    if first_latency and not first_latency_logged:
                        first_latency_logged = True

                    tool_text = self._extract_tool_stream_text(chunk)
                    if tool_text:
                        normalized_tool = MintChatAgent._normalize_output_text(tool_text)
                        if normalized_tool:
                            if tool_first_received_at is None:
                                tool_first_received_at = time.perf_counter()
                            tool_delta = tool_accumulator.consume(normalized_tool)
                            if tool_delta:
                                tool_parts.append(tool_delta)

                    if _metadata_looks_like_internal_routing(metadata):
                        continue

                    content = self._extract_stream_text(chunk)
                    emitted = _emit(content)
                    if emitted:
                        chunk_count += 1
                        total_chars += len(emitted)
                        yield emitted
            except Exception as e:
                # v3.3.4: 改进错误信息处理
                error_msg = str(e) or repr(e) or f"{type(e).__name__}: LLM 异步流式调用失败"
                logger.error(f"异步流式输出异常: {error_msg}")
                await _safe_aclose()
                raise
        except Exception:
            # 发生异常时也要清理stream
            await _safe_aclose()
            raise
        finally:
            tool_timeout_s_var.reset(token)
            if "prefix_stripper" in locals():
                pending = prefix_stripper.flush()
                if pending and "trace_scrubber" in locals():
                    pending = trace_scrubber.process(pending)
                if pending and "coalescer" in locals():
                    buffered = coalescer.push(pending)
                    if buffered:
                        chunk_count += 1
                        total_chars += len(buffered)
                        yield buffered
            if "trace_scrubber" in locals() and 'coalescer' in locals():
                scrub_tail = trace_scrubber.flush()
                if scrub_tail:
                    buffered = coalescer.push(scrub_tail)
                    if buffered:
                        chunk_count += 1
                        total_chars += len(buffered)
                        yield buffered
            if 'coalescer' in locals():
                tail = coalescer.flush()
                if tail:
                    chunk_count += 1
                    total_chars += len(tail)
                    yield tail

            if total_chars <= 0 and "tool_parts" in locals() and tool_parts:
                tool_reply = "".join(tool_parts).strip()
                if tool_reply:
                    chunk_count += 1
                    total_chars += len(tool_reply)
                    yield tool_reply
            # v3.3.4: 确保stream被关闭（在所有情况下）
            await _safe_aclose()
            if 'chunk_count' in locals():
                elapsed = time.perf_counter() - stream_start
                logger.info(
                    "异步流式输出完成: chunks=%d, chars=%d, elapsed=%.2fs",
                    chunk_count,
                    total_chars,
                    elapsed,
                )

    def _extract_stream_text(self, chunk: Any) -> str:
        """直接提取文本，不做额外过滤。"""
        if chunk is None:
            return ""

        if isinstance(chunk, str):
            return chunk

        # stream_mode="messages" 可能包含 tool/system/human 等消息；这里只保留 assistant 输出，避免工具结果污染 UI/TTS。
        # 注意：LangChain 的 AIMessageChunk.type 可能为 "AIMessageChunk"（而非 "ai"）。
        if isinstance(chunk, dict):
            role = chunk.get("role") or chunk.get("type")
            if isinstance(role, str) and role:
                role_lower = role.lower()
                if role_lower in {"tool", "system", "human", "user"}:
                    return ""
                if role_lower in {"assistant", "ai"} or role == "AIMessageChunk":
                    content = chunk.get("content") or chunk.get("text") or ""
                    if isinstance(content, str):
                        return content
                    if isinstance(content, list):
                        parts: list[str] = []
                        for block in content:
                            if isinstance(block, dict):
                                parts.append(str(block.get("text") or block.get("content") or ""))
                            else:
                                parts.append(str(getattr(block, "text", "") or getattr(block, "content", "")))
                        return "".join(parts)
                    return str(content)

        role = getattr(chunk, "role", None)
        if isinstance(role, str) and role:
            role_lower = role.lower()
            if role_lower in {"tool", "system", "human", "user"}:
                return ""

        msg_type = getattr(chunk, "type", None)
        if isinstance(msg_type, str) and msg_type:
            allowed = {"ai", "assistant", "AIMessageChunk", "AIMessage"}
            if msg_type not in allowed:
                return ""

        content = getattr(chunk, "content", None)
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict):
                    parts.append(str(block.get("text") or block.get("content") or ""))
                else:
                    parts.append(str(getattr(block, "text", "") or getattr(block, "content", "")))
            return "".join(parts)

        content_blocks = getattr(chunk, "content_blocks", None)
        if content_blocks:
            parts: list[str] = []
            for block in content_blocks:
                parts.append(str(getattr(block, "text", "") or getattr(block, "content", "")))
            return "".join(parts)

        return str(chunk)

    def _extract_tool_stream_text(self, chunk: Any) -> str:
        """提取 tool 消息的文本内容（用于“无 assistant 输出”时的兜底展示）。"""
        if chunk is None:
            return ""
        if isinstance(chunk, str):
            return ""

        def _extract_content(value: Any) -> str:
            if value is None:
                return ""
            if isinstance(value, str):
                return value
            if isinstance(value, list):
                parts: list[str] = []
                for block in value:
                    if isinstance(block, dict):
                        parts.append(str(block.get("text") or block.get("content") or ""))
                    else:
                        parts.append(str(getattr(block, "text", "") or getattr(block, "content", "")))
                return "".join(parts)
            return str(value)

        if isinstance(chunk, dict):
            role = chunk.get("role") or chunk.get("type")
            if isinstance(role, str) and role and role.lower() == "tool":
                content = chunk.get("content") or chunk.get("text") or ""
                return _extract_content(content)
            return ""

        role = getattr(chunk, "role", None)
        if isinstance(role, str) and role and role.lower() == "tool":
            return _extract_content(getattr(chunk, "content", None))

        msg_type = getattr(chunk, "type", None)
        if isinstance(msg_type, str) and msg_type and msg_type.lower() == "tool":
            return _extract_content(getattr(chunk, "content", None))

        return ""

    def _save_stream_interaction(
        self,
        save_message: str,
        full_reply: str,
        save_to_long_term: bool,
    ) -> None:
        """保存流式对话交互（v2.30.34 优化）"""
        self.memory.add_interaction(
            user_message=save_message,
            assistant_message=full_reply,
            save_to_long_term=save_to_long_term,
            importance=None,
        )

        if self.diary_memory.vectorstore:
            try:
                user_name = getattr(settings.agent, "user", "主人")
                char_name = getattr(settings.agent, "char", "小雪糕")
                interaction_text = f"{user_name}: {save_message}\n{char_name}: {full_reply}"
                self.diary_memory.add_diary_entry(interaction_text)
                logger.debug("已写入日记条目")
            except Exception as e:
                logger.warning("写入日记失败: %s", e)

    def _run_background_memory_tasks(self, save_message: str, full_reply: str) -> None:
        """运行后台记忆任务（v2.30.34 优化）"""
        if getattr(settings.agent, "memory_fast_mode", False):
            return
        try:
            def background_tasks():
                """后台记忆维护任务"""
                try:
                    with self._interaction_lock:
                        self._interaction_count += 1
                        current_count = self._interaction_count
                        should_consolidate = current_count >= self._consolidation_interval
                        if should_consolidate:
                            self._interaction_count = 0

                    consolidated_count = 0
                    if should_consolidate:
                        consolidated_count = self.memory.consolidate_memories()
                        if consolidated_count > 0:
                            logger.info("巩固了 %d 条重要记忆", consolidated_count)

                    should_extract = (
                        current_count % 3 == 0
                        or len(save_message) > 50
                    )
                    if should_extract:
                        self._extract_core_memories(save_message, full_reply)
                except Exception as e:
                    logger.warning(f"后台记忆任务失败: {e}")
            self._submit_background_task(background_tasks, label="memory-optimizer")
        except Exception as e:
            logger.warning(f"启动后台任务失败: {e}")

    def _prefetch_tts_segments(self, reply: str) -> None:
        """
        根据配置在后台预取语音，提前触发缓存以降低前端请求延迟。
        
        v2.60.4 优化：
        - 优化预取策略，仅预取前3个句子以减少资源消耗
        - 改进错误处理，减少日志噪音
        """
        if getattr(settings.agent, "memory_fast_mode", False):
            return
        if not self._tts_prefetch_enabled or not reply:
            return

        try:
            from src.multimodal.tts_text import strip_stage_directions

            normalized = strip_stage_directions(reply).strip()
        except Exception:
            normalized = reply.strip()
        if len(normalized) < self._tts_prefetch_min_chars:
            return

        if normalized == self._last_tts_prefetch_text:
            return

        tts_manager, _profile_cls = self._resolve_tts_dependencies()
        if tts_manager is None:
            return

        with self._tts_prefetch_lock:
            if self._pending_tts_prefetch and not self._pending_tts_prefetch.done():
                return
            self._last_tts_prefetch_text = normalized

        # 优化预取策略，仅预取前3个句子以减少资源消耗
        sentences = re.split(r'[。！？\n]', normalized)
        sentences = [s.strip() for s in sentences if s.strip()][:3]  # 仅预取前3句
        if not sentences:
            return
        prefetch_text = '。'.join(sentences) + '。'

        async def _prefetch():
            try:
                await self.synthesize_reply_audio_segments(
                    prefetch_text,
                    use_mood_context=True,
                )
            except Exception as exc:
                # 客户端关闭等错误属于正常情况，静默处理
                error_msg = str(exc) or repr(exc) or "未知错误"
                is_normal_close = (
                    "client has been closed" in error_msg
                    or "Event loop is closed" in error_msg
                    or "Cannot send a request" in error_msg
                )
                if not is_normal_close:
                    logger.debug("TTS 预取失败: %s", error_msg)

        def runner():
            try:
                from src.multimodal.tts_runtime import get_tts_runtime

                timeout_s = None
                try:
                    config = getattr(tts_manager, "config", None)
                    base_timeout = float(getattr(config, "request_timeout", 30.0) or 30.0)
                    timeout_s = max(5.0, base_timeout + 10.0)
                except Exception:
                    timeout_s = None

                get_tts_runtime().run(_prefetch(), timeout=timeout_s)
            except Exception:
                # 预取失败属于可忽略路径，避免日志噪音
                pass

        future = self._submit_background_task(runner, label="tts-prefetch")
        if future:
            with self._tts_prefetch_lock:
                self._pending_tts_prefetch = future

            def _clear(_future: Future) -> None:
                with self._tts_prefetch_lock:
                    if self._pending_tts_prefetch is _future:
                        self._pending_tts_prefetch = None

            future.add_done_callback(_clear)

    def _post_reply_actions(
        self,
        save_message: str,
        reply: str,
        save_to_long_term: bool,
        *,
        stream: bool,
    ) -> None:
        """
        统一处理对话后的持久化、后台任务和情感衰减，避免多处重复代码。
        """
        try:
            if stream:
                self._save_stream_interaction(save_message, reply, save_to_long_term)
            else:
                self._save_interaction_to_memory(save_message, reply, save_to_long_term)
        except Exception as exc:
            logger.warning("保存对话内容失败: %s", exc)

        self._run_background_memory_tasks(save_message, reply)
        self._prefetch_tts_segments(reply)
        self.emotion_engine.update_user_profile(interaction_positive=True)
        self.emotion_engine.decay_emotion()

    def chat_stream(
        self,
        message: str,
        save_to_long_term: bool = False,
        image_path: Optional[str] = None,
        image_analysis: Optional[dict] = None,
        cancel_event: Optional[Event] = None,
    ) -> Iterator[str]:
        """
        流式对话（生成器）(v2.30.34 重构优化)

        Args:
            message: 用户消息
            save_to_long_term: 是否保存到长期记忆
            image_path: 图片路径（可选）
            image_analysis: 图片分析结果（可选）

        Yields:
            str: 回复的文本片段
        """
        try:
            logger.info("收到用户消息(流式)")

            try:
                bundle = self._build_agent_bundle(
                    message,
                    image_analysis=image_analysis,
                    image_path=image_path,
                    compression="auto",
                    use_cache=True,
                )
            except ValueError:
                logger.warning("收到空消息")
                yield "主人，您想说什么呢？喵~"
                return
            except Exception as prep_exc:
                logger.error("准备消息失败: %s", prep_exc)
                yield f"抱歉主人，准备消息时出错了：{str(prep_exc)} 喵~"
                return

            # 若 streaming 曾因失败被临时禁用，冷却时间到后自动恢复（避免必须重启应用）。
            try:
                if getattr(self, "_streaming_user_enabled", False) and not getattr(
                    self, "enable_streaming", False
                ):
                    disabled_until = float(getattr(self, "_streaming_disabled_until", 0.0) or 0.0)
                    if disabled_until <= 0 or time.monotonic() >= disabled_until:
                        self.enable_streaming = True
                        self._stream_failure_count = 0
                        self._streaming_disabled_until = 0.0
                        logger.info("streaming 已自动恢复")
            except Exception:
                pass

            if not bool(getattr(self, "enable_streaming", True)):
                try:
                    response = self._invoke_with_failover(
                        bundle,
                        timeout_s=getattr(self, "_stream_failover_timeout_s", None),
                    )
                    reply = self._extract_reply_from_response(response)
                    if not reply.strip() or reply.strip() == _DEFAULT_EMPTY_REPLY:
                        rescued = self._rescue_empty_reply(bundle, raw_reply=reply, source="no_stream")
                        if rescued:
                            reply = rescued
                    if not reply.strip():
                        reply = _DEFAULT_EMPTY_REPLY

                    if cancel_event and cancel_event.is_set():
                        logger.info("非流式对话已取消（停止输出与保存）")
                        return

                    self._post_reply_actions(bundle.save_message, reply, save_to_long_term, stream=False)
                    yield reply
                    logger.info("非流式回复完成（streaming disabled）")
                except AgentTimeoutError as timeout_exc:
                    logger.error("非流式对话超时: %s", timeout_exc)
                    yield "抱歉主人，模型那边暂时没有回应，我们稍后再聊好么？喵~"
                except Exception as exc:
                    logger.error("非流式对话失败: %s", exc)
                    yield f"抱歉主人，我遇到了一些问题：{str(exc)} 喵~"
                return

            reply_parts: list[str] = []
            try:
                for chunk in self._stream_llm_response(bundle.messages, cancel_event=cancel_event):
                    if cancel_event and cancel_event.is_set():
                        logger.info("流式对话已取消（停止输出与保存）")
                        return
                    reply_parts.append(chunk)
                    yield chunk
                if reply_parts:
                    self._stream_failure_count = 0
            except AgentTimeoutError as timeout_exc:
                # v3.3.4: 流式输出超时保护
                error_msg = str(timeout_exc) or repr(timeout_exc) or "LLM 流式输出超时"
                if cancel_event and cancel_event.is_set():
                    logger.info("流式对话已取消（忽略超时）: %s", error_msg)
                    return
                if reply_parts:
                    logger.warning("LLM 流式输出中断（已输出部分内容）: %s", error_msg)
                    self._stream_failure_count = 0
                else:
                    logger.error("LLM 流式输出超时: %s", error_msg)
                    self._stream_failure_count = int(getattr(self, "_stream_failure_count", 0)) + 1
                    if self._stream_failure_count >= int(getattr(self, "_stream_disable_after_failures", 2)):
                        if getattr(self, "enable_streaming", False):
                            logger.warning(
                                "检测到多次流式失败（%s 次），将暂时禁用 streaming 以提升可用性",
                                self._stream_failure_count,
                            )
                        try:
                            cooldown_s = float(getattr(self, "_stream_disable_cooldown_s", 60.0))
                        except Exception:
                            cooldown_s = 60.0
                        if cooldown_s <= 0:
                            # 仅本次禁用：下次对话自动恢复
                            self._streaming_disabled_until = time.monotonic()
                        else:
                            self._streaming_disabled_until = time.monotonic() + cooldown_s
                        self.enable_streaming = False

                    try:
                        response = self._invoke_with_failover(
                            bundle,
                            timeout_s=getattr(self, "_stream_failover_timeout_s", None),
                        )
                        reply = self._extract_reply_from_response(response)
                        if not reply.strip() or reply.strip() == _DEFAULT_EMPTY_REPLY:
                            rescued = self._rescue_empty_reply(
                                bundle, raw_reply=reply, source="stream_failover"
                            )
                            if rescued:
                                reply = rescued
                        if not reply.strip():
                            reply = _DEFAULT_EMPTY_REPLY
                        reply_parts.append(reply)
                        yield reply
                    except Exception as failover_exc:
                        logger.warning("流式失败后的非流式兜底也失败: %s", failover_exc)
                        fallback = "抱歉主人，模型暂时没有新输出，我们稍后再继续聊好嘛？喵~"
                        reply_parts.append(fallback)
                        yield fallback
            except Exception as stream_exc:
                # v3.3.4: 改进错误信息处理
                error_msg = str(stream_exc) or repr(stream_exc) or f"{type(stream_exc).__name__}: LLM调用失败"
                logger.error(f"LLM调用失败: {error_msg}")
                raise

            if cancel_event and cancel_event.is_set():
                logger.info("流式对话已取消（忽略后处理）")
                return

            raw_reply = "".join(reply_parts)
            full_reply = self._filter_tool_info(raw_reply)
            if not full_reply:
                rescued = self._rescue_empty_reply(bundle, raw_reply=raw_reply, source="stream")
                if rescued:
                    full_reply = rescued
                    yield rescued
                elif raw_reply.strip():
                    # 如果已经输出了内容但过滤后为空（极少数场景），避免再追加兜底回复导致对话体验割裂。
                    full_reply = raw_reply.strip()
                else:
                    full_reply = _DEFAULT_EMPTY_REPLY
                    yield _DEFAULT_EMPTY_REPLY

            self._post_reply_actions(bundle.save_message, full_reply, save_to_long_term, stream=True)
            logger.info("流式回复完成")

        except Exception as e:
            # v3.3.4: 改进错误信息处理
            from src.utils.exceptions import handle_exception
            error_msg = str(e) or repr(e) or f"{type(e).__name__}: 流式对话处理失败"
            handle_exception(e, logger, "流式对话处理失败")
            if cancel_event and cancel_event.is_set():
                logger.info("流式对话已取消（忽略异常）: %s", error_msg)
                return
            yield f"抱歉主人，我遇到了一些问题：{error_msg} 喵~"

    async def chat_stream_async(
        self,
        message: str,
        save_to_long_term: bool = False,
        image_path: Optional[str] = None,
        image_analysis: Optional[dict] = None,
        cancel_event: Optional[Event] = None,
    ) -> AsyncIterator[str]:
        """
        异步流式对话 - 更高性能

        Args:
            message: 用户消息
            save_to_long_term: 是否保存到长期记忆

        Yields:
            str: 回复的文本片段
        """
        try:
            logger.info("收到用户消息(异步流式)")

            try:
                bundle = await self._build_agent_bundle_async(
                    message,
                    image_analysis=image_analysis,
                    image_path=image_path,
                    compression="auto",
                    use_cache=True,
                )
            except ValueError:
                logger.warning("收到空消息")
                yield "主人，您想说什么呢？喵~"
                return
            except Exception as prep_exc:
                logger.error("准备消息失败: %s", prep_exc)
                yield f"抱歉主人，准备消息时出错了：{str(prep_exc)} 喵~"
                return

            reply_parts: list[str] = []
            try:
                async for chunk in self._astream_llm_response(bundle.messages, cancel_event=cancel_event):
                    if cancel_event and cancel_event.is_set():
                        logger.info("异步流式对话已取消（停止输出与保存）")
                        return
                    reply_parts.append(chunk)
                    yield chunk
            except AgentTimeoutError as stream_timeout:
                # v3.3.4: 改进错误信息处理
                error_msg = str(stream_timeout) or repr(stream_timeout) or "异步流式输出超时"
                if cancel_event and cancel_event.is_set():
                    logger.info("异步流式对话已取消（忽略超时）: %s", error_msg)
                    return
                logger.error(f"异步流式输出超时: {error_msg}")
                fallback = "抱歉主人，模型暂时没有新输出，我们稍后再继续聊好嘛？喵~"
                if not reply_parts:
                    reply_parts.append(fallback)
                    yield fallback
            except Exception as stream_error:
                # v3.3.4: 改进错误信息处理
                from src.utils.exceptions import handle_exception
                error_msg = str(stream_error) or repr(stream_error) or f"{type(stream_error).__name__}: 异步流式输出错误"
                handle_exception(stream_error, logger, "异步流式输出错误")

            if cancel_event and cancel_event.is_set():
                logger.info("异步流式对话已取消（忽略后处理）")
                return

            raw_reply = "".join(reply_parts)
            full_reply = self._filter_tool_info(raw_reply)
            if not full_reply:
                rescued = await self._arescue_empty_reply(bundle, raw_reply=raw_reply, source="astream")
                if rescued:
                    full_reply = rescued
                    yield rescued
                elif raw_reply.strip():
                    full_reply = raw_reply.strip()
                else:
                    full_reply = _DEFAULT_EMPTY_REPLY
                    yield _DEFAULT_EMPTY_REPLY

            self._post_reply_actions(bundle.save_message, full_reply, save_to_long_term, stream=True)

            logger.info("异步流式回复完成")

        except AgentTimeoutError as timeout_exc:
            # v3.3.4: 改进错误信息处理
            error_msg = str(timeout_exc) or repr(timeout_exc) or "异步流式对话超时"
            if cancel_event and cancel_event.is_set():
                logger.info("异步流式对话已取消（忽略超时）: %s", error_msg)
                return
            logger.error(f"异步流式对话超时: {error_msg}")
            yield "抱歉主人，模型暂时没有新输出，我们稍后再继续聊好嘛？喵~"
        except Exception as e:
            # v3.3.4: 改进错误信息处理，避免空错误信息
            error_msg = str(e) or repr(e) or f"{type(e).__name__}: 异步流式对话处理失败"
            logger.error(f"异步流式对话处理失败: {error_msg}")
            if cancel_event and cancel_event.is_set():
                logger.info("异步流式对话已取消（忽略异常）: %s", error_msg)
                return
            yield f"抱歉主人，我遇到了一些问题：{error_msg} 喵~"

    def get_greeting(self) -> str:
        """
        获取问候语

        Returns:
            str: 问候语
        """
        return self.character.get_greeting()

    def get_farewell(self) -> str:
        """
        获取告别语

        Returns:
            str: 告别语
        """
        return self.character.get_farewell()

    def clear_memory(self) -> None:
        """清空所有记忆"""
        self.memory.clear_all()
        if getattr(self, "core_memory", None):
            try:
                if hasattr(self.core_memory, "clear_all"):
                    self.core_memory.clear_all()
            except Exception as e:
                logger.debug("清空核心记忆失败（可忽略）: %s", e)
        if getattr(self, "diary_memory", None):
            try:
                if hasattr(self.diary_memory, "clear_all"):
                    self.diary_memory.clear_all()
            except Exception as e:
                logger.debug("清空日记失败（可忽略）: %s", e)
        if getattr(self, "lore_book", None):
            try:
                if hasattr(self.lore_book, "clear_all"):
                    self.lore_book.clear_all()
            except Exception as e:
                logger.debug("清空知识库失败（可忽略）: %s", e)

        logger.info("记忆已清空")

    def export_memory(self, filepath: str) -> None:
        """
        导出记忆

        Args:
            filepath: 导出文件路径
        """
        import json
        from pathlib import Path

        data = self.memory.get_export_data(include_long_term=True, include_optimizer_stats=False)
        data["format_version"] = max(int(data.get("format_version") or 0), 3)
        data["agent"] = {
            "character_name": getattr(self.character, "name", None),
            "model_name": getattr(self, "model_name", None),
            "user_id": self.user_id,
        }

        advanced: dict = {}

        # CoreMemory（Chroma collection）
        core_items = []
        if getattr(self, "core_memory", None) and getattr(self.core_memory, "vectorstore", None):
            try:
                core_data = self.core_memory.vectorstore.get(include=["documents", "metadatas", "ids"])
            except TypeError:
                core_data = self.core_memory.vectorstore.get()
            ids = core_data.get("ids") or []
            docs = core_data.get("documents") or []
            metas = core_data.get("metadatas") or []
            for doc_id, content, meta in zip(ids, docs, metas):
                if not content:
                    continue
                core_items.append({"id": str(doc_id), "content": content, "metadata": dict(meta or {})})
        advanced["core_memory"] = {"count": len(core_items), "items": core_items}

        # DiaryMemory（以 diary.json 为准；向量库可由内容重建）
        diary_entries = []
        diary_file = getattr(getattr(self, "diary_memory", None), "diary_file", None)
        if diary_file:
            try:
                diary_entries = json.loads(Path(diary_file).read_text(encoding="utf-8"))
                if not isinstance(diary_entries, list):
                    diary_entries = []
            except Exception as e:
                logger.debug("读取 diary.json 失败（可忽略）: %s", e)
        advanced["diary"] = {"count": len(diary_entries), "items": diary_entries}

        # LoreBook（JSON 为准；向量库可由内容重建）
        lore_items = []
        if getattr(self, "lore_book", None):
            try:
                lore_items = self.lore_book.get_all_lores(use_cache=False)
            except TypeError:
                lore_items = self.lore_book.get_all_lores()
            except Exception as e:
                logger.debug("读取 lore_books 失败（可忽略）: %s", e)
        advanced["lore_book"] = {"count": len(lore_items), "items": lore_items}

        data["advanced_memory"] = advanced

        export_path = Path(filepath)
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def import_memory(self, filepath: str, *, overwrite: bool = False) -> Dict[str, int]:
        """
        导入记忆（与 export_memory 输出的导出包匹配）。

        Args:
            filepath: 导入文件路径
            overwrite: 是否覆盖已有记忆（覆盖：会清空对应存储再导入）

        Returns:
            Dict[str, int]: 导入统计
        """
        import json
        from pathlib import Path

        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(path)

        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("记忆导入文件格式错误：应为 JSON object")

        stats: Dict[str, int] = {
            "short_term": 0,
            "long_term": 0,
            "core_memory": 0,
            "diary": 0,
            "lore_book": 0,
        }

        # 基础记忆（短期+长期）
        try:
            base_stats = self.memory.import_from_data(
                data,
                overwrite_long_term=overwrite,
                replace_short_term=True,
            )
            stats.update(base_stats)
        except Exception as e:
            logger.warning("导入基础记忆失败: %s", e)

        # 高级记忆（可选）
        advanced = data.get("advanced_memory") or {}
        if isinstance(advanced, dict):
            # CoreMemory
            core_block = advanced.get("core_memory")
            core_items = core_block.get("items") if isinstance(core_block, dict) else None
            if isinstance(core_items, list) and getattr(self, "core_memory", None) and hasattr(self.core_memory, "import_records"):
                try:
                    stats["core_memory"] = int(self.core_memory.import_records(core_items, overwrite=overwrite))
                except Exception as e:
                    logger.warning("导入核心记忆失败: %s", e)

            # Diary
            diary_block = advanced.get("diary")
            diary_items = diary_block.get("items") if isinstance(diary_block, dict) else None
            if isinstance(diary_items, list) and getattr(self, "diary_memory", None) and hasattr(self.diary_memory, "import_entries"):
                try:
                    stats["diary"] = int(self.diary_memory.import_entries(diary_items, overwrite=overwrite))
                except Exception as e:
                    logger.warning("导入日记失败: %s", e)

            # LoreBook
            lore_block = advanced.get("lore_book")
            lore_items = lore_block.get("items") if isinstance(lore_block, dict) else None
            if isinstance(lore_items, list) and getattr(self, "lore_book", None) and hasattr(self.lore_book, "import_records"):
                try:
                    stats["lore_book"] = int(self.lore_book.import_records(lore_items, overwrite=overwrite))
                except Exception as e:
                    logger.warning("导入知识库失败: %s", e)

        logger.info("导入记忆完成: %s", stats)
        return stats

    def get_stats(self) -> Dict[str, Any]:
        """
        获取智能体统计信息

        Returns:
            Dict[str, Any]: 统计信息
        """
        stats = {
            "character_name": self.character.name,
            "model_name": self.model_name,
            "temperature": self.temperature,
            "streaming_enabled": self.enable_streaming,
            "tools_count": len(self.tool_registry.get_all_tools()),
            "tool_names": self.tool_registry.get_tool_names(),
            "recent_messages_count": len(self.memory.get_recent_messages()),
            "long_term_memory_enabled": self.memory.enable_long_term,
            "emotion_stats": self.emotion_engine.get_stats(),
            "mood_stats": self.mood_system.get_mood_stats(),  # v2.3 NEW!
            "advanced_memory": {  # v2.3 NEW!
                "core_memory_enabled": settings.agent.is_core_mem,
                "diary_enabled": settings.agent.long_memory,
                "lore_books_enabled": settings.agent.lore_books,
            },
            "character_state": self.character_state.get_stats(),  # v2.5 NEW!
            "style_learning": self.style_learner.get_stats(),  # v2.5 NEW!
        }

        # v3.2: 添加记忆优化器统计
        optimizer_stats = self.memory.get_optimizer_stats()
        if optimizer_stats:
            stats["memory_optimizer"] = optimizer_stats

        return stats

    # ==================== 高级记忆管理方法 (v2.3 NEW!) ====================

    def add_core_memory(
        self,
        content: str,
        category: str = "general",
        importance: float = 1.0,
    ) -> None:
        """
        添加核心记忆

        Args:
            content: 记忆内容
            category: 类别
            importance: 重要性
        """
        self.core_memory.add_core_memory(content, category, importance)

    def add_lore(
        self,
        title: str,
        content: str,
        category: str = "general",
        keywords: Optional[List[str]] = None,
        source: str = "manual",
    ) -> Optional[str]:
        """
        添加知识库条目 - v2.30.38 增强版

        Args:
            title: 标题
            content: 内容
            category: 类别
            keywords: 关键词
            source: 来源

        Returns:
            str: 知识ID，失败返回 None
        """
        return self.lore_book.add_lore(title, content, category, keywords, source)

    def learn_from_file(self, filepath: str) -> int:
        """
        从文件中学习知识 - v2.30.38 新增

        Args:
            filepath: 文件路径

        Returns:
            int: 学习到的知识数量
        """
        learned_ids = self.lore_book.learn_from_file(filepath)
        return len(learned_ids)

    def get_lore_statistics(self) -> Dict[str, Any]:
        """
        获取知识库统计信息 - v2.30.38 新增

        Returns:
            Dict: 统计信息
        """
        return self.lore_book.get_statistics()

    def get_mood_status(self) -> str:
        """
        获取当前情绪状态

        Returns:
            str: 情绪状态描述
        """
        if not self.mood_system.enabled:
            return "情绪系统未启用"

        mood_state = self.mood_system.get_mood_state()
        mood_value = self.mood_system.mood_value
        return f"当前情绪: {mood_state} (数值: {mood_value:.2f})"

    @staticmethod
    def get_performance_stats() -> Dict[str, Any]:
        """
        获取性能统计信息

        Returns:
            Dict: 性能统计
        """
        return performance_monitor.get_all_stats()

    @staticmethod
    def print_performance_stats() -> None:
        """打印性能统计信息"""
        performance_monitor.print_stats()

    # ==================== v2.5 新增方法 ====================

    def get_character_state_status(self) -> str:
        """
        获取角色状态描述

        Returns:
            str: 角色状态描述
        """
        return self.character_state.get_state_description()

    def feed_character(self) -> str:
        """
        喂食角色

        Returns:
            str: 反馈信息
        """
        self.character_state.on_interaction("feed")
        return "主人给小雪糕喂食了，饥饿度降低，满足度提升~"

    def play_with_character(self) -> str:
        """
        与角色玩耍

        Returns:
            str: 反馈信息
        """
        self.character_state.on_interaction("play")
        return "主人和小雪糕一起玩耍，孤独感降低，活力提升~"

    def let_character_rest(self) -> str:
        """
        让角色休息

        Returns:
            str: 反馈信息
        """
        self.character_state.on_interaction("rest")
        return "小雪糕休息了一会儿，疲劳度降低，活力恢复~"

    @staticmethod
    def reset_performance_stats() -> None:
        """重置性能统计"""
        performance_monitor.reset()

    def get_emotion_status(self) -> str:
        """
        获取当前情感状态的友好描述

        Returns:
            str: 情感状态描述
        """
        emotion = self.emotion_engine.current_emotion
        relationship = self.emotion_engine.get_relationship_description()
        return (
            f"当前情感: {emotion.emotion_type.value} "
            f"(强度: {emotion.intensity:.1f})\n"
            f"与主人的关系: {relationship}"
        )

    # ==================== v2.30.28 智能记忆提取 ====================

    def _extract_core_memories(self, user_message: str, assistant_message: str) -> None:
        """
        智能提取核心记忆（后台执行）

        从对话中自动识别并提取重要信息到核心记忆

        Args:
            user_message: 用户消息
            assistant_message: 助手回复
        """
        try:
            # 使用集合优化关键词匹配性能（类级常量）
            if not hasattr(self.__class__, "_PERSONAL_INFO_KEYWORDS"):
                self.__class__._PERSONAL_INFO_KEYWORDS = frozenset([
                "我叫", "我的名字", "我是", "我今年", "我的生日", "我住在",
                "我来自", "我的职业", "我的工作", "我的爱好", "我喜欢", "我讨厌",
                "我的家人", "我的朋友", "我的宠物"
                ])
                self.__class__._PREFERENCES_KEYWORDS = frozenset([
                "喜欢", "不喜欢", "讨厌", "最爱", "偏好", "习惯",
                "经常", "总是", "从不", "一般", "通常"
                ])
                self.__class__._IMPORTANT_EVENTS_KEYWORDS = frozenset([
                "记住", "重要", "一定要", "千万", "务必", "别忘了",
                "提醒我", "帮我记", "不要忘记"
                ])
                self.__class__._IMPORTANT_WORDS = frozenset(["重要", "记住", "一定", "务必", "千万"])

            # 使用any()和生成器表达式优化匹配
            if any(kw in user_message for kw in self.__class__._PERSONAL_INFO_KEYWORDS):
                    self.core_memory.add_core_memory(
                        content=user_message,
                        category="personal_info",
                        importance=0.9
                    )
                    logger.info("提取个人信息到核心记忆")
                    return

            if any(kw in user_message for kw in self.__class__._PREFERENCES_KEYWORDS):
                    self.core_memory.add_core_memory(
                        content=user_message,
                        category="preferences",
                        importance=0.8
                    )
                    logger.info("提取偏好信息到核心记忆")
                    return

            if any(kw in user_message for kw in self.__class__._IMPORTANT_EVENTS_KEYWORDS):
                    self.core_memory.add_core_memory(
                        content=user_message,
                        category="important_events",
                        importance=0.95
                    )
                    logger.info("提取重要事件到核心记忆")
                    return

            # 长消息（可能包含重要信息）
            if len(user_message) > 100 and any(word in user_message for word in self.__class__._IMPORTANT_WORDS):
                    self.core_memory.add_core_memory(
                        content=user_message,
                        category="general",
                        importance=0.7
                    )
                    logger.info("提取长消息到核心记忆")

        except Exception as e:
            logger.warning(f"提取核心记忆失败: {e}")

    def close(self) -> None:
        """
        清理Agent资源（显式关闭）
        
        清理所有线程池、后台任务和资源
        """
        logger.info("开始清理 Agent 资源...")

        # 0. 关闭 Agent middleware（例如工具筛选器的线程池），避免退出阶段仍尝试调度任务
        try:
            for mw in getattr(self, "_agent_middleware", []) or []:
                close_fn = getattr(mw, "close", None)
                if callable(close_fn):
                    close_fn()
        except Exception as e:
            logger.debug("关闭 Agent middleware 时出错（可忽略）: %s", e)
         
        # 1. 取消待处理的TTS预取任务
        if hasattr(self, '_pending_tts_prefetch') and self._pending_tts_prefetch:
            with self._tts_prefetch_lock:
                if self._pending_tts_prefetch and not self._pending_tts_prefetch.done():
                    self._pending_tts_prefetch.cancel()
                self._pending_tts_prefetch = None
        
        # 2. 关闭后台执行器
        if hasattr(self, '_background_executor') and self._background_executor:
            try:
                import concurrent.futures as _futures

                with self._background_lock:
                    futures = list(self._background_futures)
                    for fut in futures:
                        if not fut.done():
                            fut.cancel()
                    self._background_futures.clear()

                # Executor.shutdown() 不支持 timeout；这里用 wait(timeout=...) 做软超时
                try:
                    self._background_executor.shutdown(wait=False, cancel_futures=True)
                except TypeError:
                    self._background_executor.shutdown(wait=False)

                try:
                    done, not_done = _futures.wait(futures, timeout=5.0)
                    if not_done:
                        logger.warning("关闭后台执行器超时: %d 个任务仍在运行", len(not_done))
                except Exception:
                    pass
            except Exception as e:
                logger.warning(f"关闭后台执行器时出错: {e}")
            finally:
                self._background_executor = None
        
        # 3. 关闭LLM执行器
        if hasattr(self, '_llm_executor') and self._llm_executor:
            try:
                try:
                    self._llm_executor.shutdown(wait=False, cancel_futures=True)
                except TypeError:
                    self._llm_executor.shutdown(wait=False)
            except Exception as e:
                logger.warning(f"关闭LLM执行器时出错: {e}")
            finally:
                self._llm_executor = None
        if hasattr(self, '_stream_executor') and self._stream_executor:
            try:
                try:
                    self._stream_executor.shutdown(wait=False, cancel_futures=True)
                except TypeError:
                    self._stream_executor.shutdown(wait=False)
            except Exception as e:
                logger.warning(f"关闭流式执行器时出错: {e}")
            finally:
                self._stream_executor = None
        if hasattr(self, "_blocking_executor") and self._blocking_executor:
            try:
                try:
                    self._blocking_executor.shutdown(wait=False, cancel_futures=True)
                except TypeError:
                    self._blocking_executor.shutdown(wait=False)
            except Exception as e:
                logger.warning(f"关闭阻塞桥接执行器时出错: {e}")
            finally:
                self._blocking_executor = None
        # 7. 关闭工具执行线程池
        try:
            from src.agent.tools import tool_registry
            if hasattr(tool_registry, "close"):
                tool_registry.close()
        except Exception as e:
            logger.debug("关闭工具执行器时出错（可忽略）: %s", e)

        # 8. 关闭知识库/高级记忆的后台资源（如异步处理器）
        if hasattr(self, "lore_book") and self.lore_book:
            try:
                if hasattr(self.lore_book, "close"):
                    self.lore_book.close()
            except Exception as e:
                logger.debug("关闭知识库资源时出错（可忽略）: %s", e)

        # 4. 关闭记忆检索器
        if hasattr(self, 'memory_retriever') and self.memory_retriever:
            try:
                if hasattr(self.memory_retriever, 'close'):
                    self.memory_retriever.close()
            except Exception as e:
                logger.warning(f"关闭记忆检索器时出错: {e}")
        
        # 5. 刷新批量缓冲区和清理缓存
        if hasattr(self, 'memory') and self.memory:
            try:
                self.memory.cleanup_cache()
            except Exception as e:
                logger.warning(f"清理记忆缓存时出错: {e}")
        
        logger.info("Agent 资源清理完成")

    def get_memory_stats(self) -> Dict[str, Any]:
        """
        获取记忆系统统计信息

        Returns:
            Dict: 记忆统计信息
        """
        try:
            stats = {
                "short_term_messages": len(self.memory.short_term),
                "long_term_enabled": self.memory.enable_long_term,
            }

            # 长期记忆统计
            if self.memory.long_term and self.memory.long_term.vectorstore:
                try:
                    long_term_data = self.memory.long_term.vectorstore.get()
                    stats["long_term_memories"] = len(long_term_data.get("documents", []))
                except Exception as e:
                    logger.warning(f"获取长期记忆统计失败: {e}")
                    stats["long_term_memories"] = 0
            else:
                stats["long_term_memories"] = 0

            # 核心记忆统计
            if self.core_memory.vectorstore:
                try:
                    core_data = self.core_memory.vectorstore.get()
                    stats["core_memories"] = len(core_data.get("documents", []))
                except Exception as e:
                    logger.warning(f"获取核心记忆统计失败: {e}")
                    stats["core_memories"] = 0
            else:
                stats["core_memories"] = 0

            # 日记统计（v2.30.29: 增加情感和主题统计）
            if self.diary_memory.diary_file and self.diary_memory.diary_file.exists():
                try:
                    import json
                    diaries = json.loads(self.diary_memory.diary_file.read_text(encoding="utf-8"))
                    stats["diary_entries"] = len(diaries)

                    # 情感统计
                    stats["emotion_stats"] = self.diary_memory.get_emotion_stats()

                    # 主题统计
                    stats["topic_stats"] = self.diary_memory.get_topic_stats()
                except Exception as e:
                    logger.warning(f"获取日记统计失败: {e}")
                    stats["diary_entries"] = 0
                    stats["emotion_stats"] = {}
                    stats["topic_stats"] = {}
            else:
                stats["diary_entries"] = 0
                stats["emotion_stats"] = {}
                stats["topic_stats"] = {}

            # 知识库统计
            if self.lore_book.vectorstore:
                try:
                    lore_data = self.lore_book.vectorstore.get()
                    stats["lore_entries"] = len(lore_data.get("documents", []))
                except Exception as e:
                    logger.warning(f"获取知识库统计失败: {e}")
                    stats["lore_entries"] = 0
            else:
                stats["lore_entries"] = 0

            return stats

        except Exception as e:
            logger.error(f"获取记忆统计失败: {e}")
            return {
                "error": str(e),
                "short_term_messages": 0,
                "long_term_memories": 0,
                "core_memories": 0,
                "diary_entries": 0,
                "lore_entries": 0,
            }

    def _execute_tool_calls_from_text(self, text: Any) -> Optional[str]:
        """
        Parse tool-call-like JSON from text and execute tools directly.
        This is used as a fast rescue path when the model outputs only tool calls.
        """
        calls = self._extract_tool_calls_from_text(text)
        if not calls:
            return None

        available = set(self.tool_registry.get_tool_names())
        alias_map = {
            "amap_weather": "get_weather",
            "weather": "get_weather",
            "get_weather": "get_weather",
            "bing_web_search": "web_search",
            "search": "web_search",
            "web_search": "web_search",
            "amap_poi_search": "map_search",
            "poi_search": "map_search",
            "map_search": "map_search",
            "map": "map_search",
            "get_current_time": "get_current_time",
            "time": "get_current_time",
            "get_current_date": "get_current_date",
            "date": "get_current_date",
        }

        def _resolve_tool_name(raw_name: str) -> str:
            name = (raw_name or "").strip()
            if not name:
                return name
            if name in available:
                return name
            key = name.lower()
            mapped = alias_map.get(key)
            if mapped and mapped in available:
                return mapped
            if key.startswith("amap_"):
                if key.endswith("weather") and "get_weather" in available:
                    return "get_weather"
                if ("poi" in key or "place" in key or "search" in key) and "map_search" in available:
                    return "map_search"
            if "weather" in key and "get_weather" in available:
                return "get_weather"
            if "search" in key and "web_search" in available:
                return "web_search"
            if "map" in key and "map_search" in available:
                return "map_search"
            if "time" in key and "get_current_time" in available:
                return "get_current_time"
            if "date" in key and "get_current_date" in available:
                return "get_current_date"
            return name

        results: list[str] = []
        for name, args in calls:
            if not name:
                continue
            resolved = _resolve_tool_name(name)
            try:
                result = self.tool_registry.execute_tool(resolved, **(args or {}))
            except Exception as exc:  # pragma: no cover - defensive
                result = f"工具 {resolved} 执行失败: {exc}"
            if result is not None:
                results.append(str(result))

        if not results:
            return None
        if len(results) == 1:
            return results[0].strip()
        return "\n".join(r.strip() for r in results if r and str(r).strip())

    @staticmethod
    def _extract_tool_calls_from_text(text: Any) -> List[Tuple[str, Dict[str, Any]]]:
        if text is None:
            return []
        if not isinstance(text, str):
            text = str(text)
        raw = text.strip()
        if not raw:
            return []

        fragment = _extract_leading_json_fragment(raw) or _extract_any_json_fragment(raw)
        if not fragment:
            return []

        try:
            data = json.loads(fragment)
        except Exception:
            return []

        calls: List[Tuple[str, Dict[str, Any]]] = []

        def _normalize_args(value: Any) -> Dict[str, Any]:
            if value is None:
                return {}
            if isinstance(value, dict):
                return value
            if isinstance(value, str):
                value = value.strip()
                if not value:
                    return {}
                try:
                    parsed = json.loads(value)
                    return parsed if isinstance(parsed, dict) else {}
                except Exception:
                    return {}
            return {}

        def _append_call(call_obj: Any) -> None:
            name: Optional[str] = None
            args: Dict[str, Any] = {}
            if isinstance(call_obj, dict):
                fn = call_obj.get("function")
                if isinstance(fn, dict):
                    name = fn.get("name") or call_obj.get("name")
                    args = _normalize_args(fn.get("arguments") or fn.get("args"))
                else:
                    name = (
                        call_obj.get("name")
                        or call_obj.get("tool")
                        or call_obj.get("tool_name")
                        or call_obj.get("function_name")
                    )
                    args = _normalize_args(
                        call_obj.get("arguments")
                        or call_obj.get("args")
                        or call_obj.get("params")
                    )
            elif isinstance(call_obj, str):
                name = call_obj.strip()
                args = {}
            if name:
                calls.append((name, args))

        if isinstance(data, dict):
            if "tool_calls" in data and isinstance(data.get("tool_calls"), list):
                for call in data["tool_calls"]:
                    _append_call(call)
            elif "tools" in data and isinstance(data.get("tools"), list):
                for call in data["tools"]:
                    _append_call(call)
            elif "name" in data and ("arguments" in data or "args" in data):
                _append_call(data)
        elif isinstance(data, list):
            for call in data:
                _append_call(call)

        return calls

    @staticmethod
    def _filter_tool_info(text: Any) -> str:
        """
        过滤模型返回中的工具选择/调用信息，避免污染对话与 TTS。
        """
        if text is None:
            return ""
        if not isinstance(text, str):
            text = str(text)

        raw = text.strip()
        if not raw:
            return ""

        # 部分 OpenAI 兼容网关 / LangChain 1.0.x 组合会把 structured output 片段
        # （例如工具选择/分流标签的 JSON）直接拼接到自然语言回复之前，形如：
        #   ["general_chat"]}["emotion_analysis", ...]}当然是真的...
        # 这里优先剥离这类“前缀 JSON 片段”，避免污染最终回复。
        cleaned_raw = raw
        for _ in range(3):  # 限制循环次数，避免异常输入导致长时间处理
            if not cleaned_raw or cleaned_raw[0] not in "{[":
                break

            fragment = _extract_leading_json_fragment(cleaned_raw)
            if not fragment:
                break

            rest = cleaned_raw[len(fragment) :]
            rest_lstrip = rest.lstrip()
            has_trailing_brace = rest_lstrip.startswith("}")
            rest_after_braces = rest_lstrip.lstrip("}").lstrip()

            drop_fragment = False
            parsed: Any = None
            if len(fragment) <= 50_000:
                try:
                    parsed = json.loads(fragment)
                except Exception:
                    parsed = None

            if parsed is not None and _looks_like_tool_call_payload(parsed):
                drop_fragment = True
            elif isinstance(parsed, list) and parsed and all(isinstance(item, str) for item in parsed):
                # list[str] 作为“内部标签/模块名”通常为 snake_case；若后面紧跟多段 JSON/孤立 '}'，
                # 基本可以判定为工具/结构化输出残留。
                normalized = [item.strip() for item in parsed]
                if normalized and all(_IDENT_TOKEN_RE.fullmatch(item) for item in normalized) and any(
                    "_" in item for item in normalized
                ):
                    if has_trailing_brace or rest_after_braces[:1] in "[{":
                        drop_fragment = True

            if not drop_fragment:
                break

            cleaned_raw = rest_after_braces

        raw = cleaned_raw.strip()
        if not raw:
            return ""

        # 尝试解析 JSON，如果是工具选择结构则直接丢弃
        if raw.startswith("{") or raw.startswith("["):
            # 性能优化：仅在“看起来是完整 JSON 且包含工具相关键”时才尝试解析，
            # 避免流式碎片频繁触发 json.loads 异常开销。
            looks_complete = raw.endswith("}") or raw.endswith("]")
            if looks_complete and len(raw) <= 200_000:
                lowered_raw = raw.lower()
                maybe_tool_payload = (
                    "tool_calls" in lowered_raw
                    or "\"tools\"" in lowered_raw
                    or "\"tool\"" in lowered_raw
                    or ("\"function\"" in lowered_raw and "\"arguments\"" in lowered_raw and "\"name\"" in lowered_raw)
                )
                if maybe_tool_payload:
                    try:
                        data = json.loads(raw)
                        if _looks_like_tool_call_payload(data):
                            return ""
                    except Exception:
                        pass

        # 清理“代码围栏”里泄露的工具/路由结构化内容，但保留正常代码块输出。
        cleaned = raw
        if "```" in raw:
            cleaned = _strip_tool_code_fences(raw, max_blocks=3)

        # 尝试移除嵌入在自然语言中的“工具调用 JSON 块”（尽量避免误伤正常 JSON）
        lower_cleaned = cleaned.lower()
        maybe_tool_trace = (
            "toolselectionresponse" in lower_cleaned
            or "tool_calls" in lower_cleaned
            or "\"tools\"" in lower_cleaned
            or ("\"function\"" in lower_cleaned and "\"arguments\"" in lower_cleaned and "\"name\"" in lower_cleaned)
        )
        if maybe_tool_trace and ("{" in cleaned or "[" in cleaned):
            cleaned = _strip_tool_json_blocks(cleaned, max_blocks=3)
            lower_cleaned = cleaned.lower()
            maybe_tool_trace = (
                "toolselectionresponse" in lower_cleaned
                or "tool_calls" in lower_cleaned
                or "\"tools\"" in lower_cleaned
                or ("\"function\"" in lower_cleaned and "\"arguments\"" in lower_cleaned and "\"name\"" in lower_cleaned)
            )

        # 处理“路由标签 list[str]”残留（通常不包含 "tool" 字样）
        if "[" in cleaned and "_" in cleaned:
            cleaned = _strip_route_tag_lists(cleaned, max_blocks=5)
            lower_cleaned = cleaned.lower()
            if "\"tools\"" in lower_cleaned or "tool_calls" in lower_cleaned:
                maybe_tool_trace = True

        # 逐行过滤残留的工具提示/调试行
        filtered_lines: list[str] = []
        for line in cleaned.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            lower = stripped.lower()
            if lower.startswith("toolselectionresponse"):
                continue
            # 路由标签数组（例：["local_search","map_guide"]}）
            if stripped.startswith("["):
                frag = _extract_leading_json_fragment(stripped)
                if frag:
                    try:
                        parsed = json.loads(frag)
                    except Exception:
                        parsed = None
                    if parsed is not None and _looks_like_route_tag_list(parsed):
                        rest = stripped[len(frag) :].lstrip()
                        if rest.startswith("}"):
                            rest = rest[1:].lstrip()
                        if not rest:
                            continue
                        filtered_lines.append(rest)
                        continue
            if maybe_tool_trace and stripped in {"{", "}", "[", "]", "},", "],"}:
                continue
            compact = lower.replace(" ", "")
            # JSON 工具块的行（可能不以 {/[ 开头，例如："tools":[...）
            if (
                "\"tools\"" in compact
                or "\"tool_calls\"" in compact
                or "\"type\":\"function\"" in compact
                or ("\"function\"" in compact and "\"arguments\"" in compact and "\"name\"" in compact)
            ):
                continue
            if stripped.startswith("{") or stripped.startswith("["):
                compact = lower.replace(" ", "")
                if (
                    "tool_calls" in compact
                    or "\"tools\"" in compact
                    or "\"tool\"" in compact
                    or "\"type\":\"function\"" in compact
                    or ("\"function\"" in compact and "\"arguments\"" in compact and "\"name\"" in compact)
                ):
                    continue
            filtered_lines.append(line)

        return "\n".join(filtered_lines).strip()

    @staticmethod
    def _normalize_output_text(text: str) -> str:
        """
        轻量清理输出文本（主要用于流式片段）。

        目标：
        - 统一换行符与过多空行，提升 UI/TTS 的稳定性
        - 不对每个流式 chunk 进行 strip/压缩空格，避免破坏代码缩进与词间空格
        """
        if not text or not isinstance(text, str):
            return ""
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        # 合并连续空行为最多一个
        text = _MULTI_NEWLINE_RE.sub("\n\n", text)
        return text
