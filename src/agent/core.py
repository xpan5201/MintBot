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
import logging
import re
import time
from difflib import SequenceMatcher
from pathlib import Path
from collections import OrderedDict, deque
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

from src.character.config_loader import CharacterConfigLoader  # noqa: E402
from src.character.personality import CharacterPersonality, default_character  # noqa: E402
from src.config.settings import settings  # noqa: E402
from src.utils.logger import get_logger  # noqa: E402
from src.utils.async_loop_thread import AsyncLoopThread  # noqa: E402
from src.utils.performance import monitor_performance, performance_monitor  # noqa: E402
from src.utils.tool_context import (  # noqa: E402
    ToolTraceRecorder,
    tool_timeout_s_var,
    tool_trace_recorder_var,
)

from .advanced_memory import CoreMemory  # noqa: E402
from .character_state import CharacterState  # noqa: E402
from .context_compressor import ContextCompressor  # noqa: E402
from .emotion import EmotionEngine  # noqa: E402
from .memory import MemoryManager  # noqa: E402
from .memory_retriever import ConcurrentMemoryRetriever  # noqa: E402
from .memory_scorer import MemoryScorer  # noqa: E402
from .mood_system import MoodSystem  # noqa: E402
from .style_learner import StyleLearner  # noqa: E402
from .tools import ToolRegistry, tool_registry  # noqa: E402
from .tool_trace_middleware import ToolTraceMiddleware  # noqa: E402

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
_MEANINGFUL_CHAR_RE = re.compile(r"[0-9A-Za-z\u4e00-\u9fff]")
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
    Heuristically detect common "tool call" / structured-tool routing payloads that should not be
    shown to UI/TTS.

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
        if "tool" in keys and (
            "args" in keys or "arguments" in keys or "tool_input" in keys or "toolinput" in keys
        ):
            return True

        # Some gateways emit {"id": "...", "name": "...", "arguments": "..."}.
        if (
            "name" in keys
            and ("arguments" in keys or "args" in keys)
            and ("id" in keys or "tool" in keys)
        ):
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
                    '"function"' in lowered_fragment
                    and '"arguments"' in lowered_fragment
                    and '"name"' in lowered_fragment
                )
                or ('"type"' in lowered_fragment and '"function"' in lowered_fragment)
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
        if not remove_trailing_brace and next_char not in {"{", "[", "}", "]"}:
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

        # Drop non-JSON tool routing traces that some gateways inject before the real assistant
        # text.
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
                if force:
                    self._done = True
                    self._buffer = ""
                    # If we only received a very short prefix (e.g. "tool"/"tools"), it might be
                    # legit text.
                    # Drop only when we have enough chars to be confident it's the marker.
                    return "" if len(candidate_lower) >= 8 else full_text
                self._buffer = full_text
                return ""

            if candidate_lower.startswith(marker):
                nl = candidate.find("\n")
                if nl < 0:
                    if force or (
                        self._max_buffer_chars and len(candidate) > self._max_buffer_chars
                    ):
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
                    probe = cleaned.lstrip().lower()
                    compact = probe.replace(" ", "")
                    looks_like_tool_payload = (
                        "toolselectionresponse" in compact
                        or "tool_calls" in compact
                        or '"tool_calls"' in compact
                        or '"tools"' in compact
                        or '"type":"function"' in compact
                        or (
                            '"function"' in compact
                            and '"arguments"' in compact
                            and '"name"' in compact
                        )
                    )
                    if looks_like_tool_payload:
                        return ""
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
            if (
                fragment is None
                and not force
                and (not self._max_buffer_chars or len(cleaned) <= self._max_buffer_chars)
            ):
                return ""

        self._done = True
        self._buffer = ""
        return cleaned

    @staticmethod
    def _should_drop_fragment(
        fragment: str, has_trailing_brace: bool, rest_after_braces: str
    ) -> bool:
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
            if (
                "tool_calls" in lowered_fragment
                or '"tool_calls"' in lowered_fragment
                or '"tools"' in lowered_fragment
            ):
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
_LINESTART_TOOL_PREFIX_RE = re.compile(r"(?:^|\n)[ \t]*(?P<tool>(?i:tool_))")
_TOOL_RESULT_HEADER_RE = re.compile(r"(?i)^tool_result\s*:\s*")
_TOOL_RESULT_KV_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\s*:\s*")
_TOOL_RESULT_NUMBERED_RE = re.compile(r"^\d+\.\s*")


class StreamToolTraceScrubber:
    """
    Stateful scrubber for streaming output.

    Root cause (LangChain/LangGraph 1.0.x): when using `stream_mode="messages"`, some intermediate
    routing steps (tool selection / structured output) can be streamed as assistant-like text
    messages. On some OpenAI-compatible gateways, those structured payloads arrive as plain text
    (sometimes split across chunks), so "end-only" filtering is not enough.

    Strategy:
    - Only react when we see suspicious markers (ToolSelectionResponse / JSON-like blocks at line
      start).
    - Buffer minimal tail if a JSON/tool fragment is incomplete, so partial garbage never reaches
      UI.
    - Remove:
        - ToolSelectionResponse lines
        - tool-call payload JSON blocks (dict/list)
        - route/tag list fragments (list[str] of snake_case identifiers)
    """

    def __init__(self, *, max_buffer_chars: int = 16_384, max_scan_blocks: int = 8) -> None:
        self._buffer = ""
        self._max_buffer_chars = max(0, int(max_buffer_chars))
        self._max_scan_blocks = max(1, int(max_scan_blocks))
        self._in_tool_result = False

    @staticmethod
    def _is_suspicious(text: str) -> bool:
        if not text:
            return False
        stripped = text.lstrip()
        if stripped.startswith("{") or stripped.startswith("["):
            return True
        if "\n{" in text or "\n[" in text:
            return True

        stripped_lower = stripped.lower()
        marker = "toolselectionresponse"
        if (
            stripped_lower
            and stripped_lower != marker
            and len(stripped_lower) >= 8
            and marker.startswith(stripped_lower)
        ):
            return True

        lower = text.lower()
        if "tool_result" in lower or stripped.lower().startswith("tool_") or "\ntool_" in lower:
            return True
        if "toolselectionresponse" in lower:
            return True
        if "tool_calls" in lower or '"tool_calls"' in lower or '"tools"' in lower:
            return True
        if ("{" in text or "[" in text) and ('_"' in text or "_" in text):
            # route tag list often contains underscores and quote brackets
            if '["' in text:
                return True
        if '"function"' in lower and '"arguments"' in lower and '"name"' in lower:
            return True
        return False

    def _tool_result_line_is_continuation(self, line: str) -> bool:
        stripped = (line or "").strip()
        if not stripped:
            return True
        lower = stripped.lower()
        if lower == "results:":
            return True
        if stripped.startswith("[...工具输出已截断"):
            return True
        if _TOOL_RESULT_KV_RE.match(stripped):
            return True
        if _TOOL_RESULT_NUMBERED_RE.match(stripped):
            return True
        return False

    def _consume_tool_result_frontier(self, s: str, *, force: bool) -> tuple[str, bool]:
        """
        Consume TOOL_RESULT blocks and their continuation lines at the frontier.

        Returns:
        - (new_s, needs_more): if needs_more is True, keep buffering `new_s` and stop draining.
        """
        while True:
            if not s:
                return "", False

            # TOOL_RESULT blocks are line-oriented; drop leading whitespace while we're in this
            # mode.
            s_stripped = s.lstrip()
            if s_stripped != s:
                s = s_stripped
                if not s:
                    return "", False

            nl = s.find("\n")
            if nl < 0:
                probe = s.strip()
                if not probe:
                    return "", False
                if _TOOL_RESULT_HEADER_RE.match(probe) or (
                    self._in_tool_result and self._tool_result_line_is_continuation(probe)
                ):
                    if not force:
                        return s, True
                    return "", False
                # Looks like normal text: exit tool-result mode and keep it.
                self._in_tool_result = False
                return s, False

            line = s[: nl + 1]
            rest = s[nl + 1 :]
            line_stripped = line.strip()

            if not line_stripped:
                s = rest
                continue

            if _TOOL_RESULT_HEADER_RE.match(line_stripped):
                self._in_tool_result = True
                s = rest
                continue

            if self._in_tool_result and self._tool_result_line_is_continuation(line_stripped):
                s = rest
                continue

            # Not a tool-result continuation line: exit mode and keep the remaining text.
            self._in_tool_result = False
            return s, False

    def process(self, delta: str) -> str:
        if not delta:
            return ""
        if not self._buffer and not self._in_tool_result and not self._is_suspicious(delta):
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
                    # Force flush: drop incomplete marker fragments instead of leaking them to UI.
                    s = ""
                    continue
                if lower.startswith(marker):
                    nl = candidate.find("\n")
                    if nl < 0:
                        if not force:
                            break
                        s = ""
                        continue
                    s = candidate[nl + 1 :].lstrip()
                    continue

            # 2) Consume TOOL_RESULT blocks (tool outputs accidentally echoed by the model).
            if self._in_tool_result:
                s, needs_more = self._consume_tool_result_frontier(s, force=force)
                if needs_more:
                    break
                if not s:
                    break

            # 3) Find next marker: JSON blocks or TOOL_RESULT/TOOL_ prefixes at line start.
            json_match = _LINESTART_JSON_OPEN_RE.search(s)
            tool_match = _LINESTART_TOOL_PREFIX_RE.search(s)
            if not json_match and not tool_match:
                out_parts.append(s)
                s = ""
                break

            json_idx = json_match.start("open") if json_match else None
            tool_idx = tool_match.start("tool") if tool_match else None
            indices = [i for i in (json_idx, tool_idx) if isinstance(i, int)]
            if not indices:
                out_parts.append(s)
                s = ""
                break

            next_idx = min(indices)
            if next_idx > 0:
                out_parts.append(s[:next_idx])
                s = s[next_idx:]

            if tool_idx is not None and tool_idx == next_idx:
                lowered = s.lower()
                if lowered.startswith("tool_result"):
                    # Drop header line; the remaining continuation lines will be discarded in
                    # subsequent iterations.
                    nl = s.find("\n")
                    if nl < 0:
                        if not force:
                            break
                        s = ""
                        self._in_tool_result = False
                        continue
                    self._in_tool_result = True
                    s = s[nl + 1 :]
                    continue

                if lowered.startswith("tool_re"):
                    # Likely a split TOOL_RESULT prefix; keep buffering unless we're force flushing.
                    if not force:
                        break
                    s = ""
                    self._in_tool_result = False
                    continue

                out_parts.append(s)
                s = ""
                break

            # JSON marker path (existing behavior).
            if json_match is None:
                out_parts.append(s)
                s = ""
                break

            fragment = _extract_leading_json_fragment(s)
            if fragment is None:
                # Incomplete JSON: keep buffered so partial tool traces won't show.
                if force:
                    probe = s.lstrip().lower()
                    compact = probe.replace(" ", "")
                    looks_like_tool_payload = (
                        "toolselectionresponse" in compact
                        or "tool_calls" in compact
                        or '"tool_calls"' in compact
                        or '"tools"' in compact
                        or '"type":"function"' in compact
                        or (
                            '"function"' in compact
                            and '"arguments"' in compact
                            and '"name"' in compact
                        )
                    )
                    if not looks_like_tool_payload:
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
                if _looks_like_tool_call_payload(parsed):
                    remove_fragment = True
                elif _looks_like_route_tag_list(parsed):
                    # Be conservative: only remove tag lists when they behave like leaked internal
                    # markers (e.g., followed by a stray brace or another JSON block). Otherwise the
                    # user might legitimately be asking the model to output a JSON array.
                    after = s[len(fragment) :]
                    after_lstrip = after.lstrip()
                    if after_lstrip.startswith("}") or after_lstrip[:1] in {"{", "["}:
                        remove_fragment = True
            else:
                lowered_fragment = fragment.lower()
                if (
                    "tool_calls" in lowered_fragment
                    or '"tool_calls"' in lowered_fragment
                    or '"tools"' in lowered_fragment
                    or (
                        '"function"' in lowered_fragment
                        and '"arguments"' in lowered_fragment
                        and '"name"' in lowered_fragment
                    )
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


_STREAM_MODE_NAMES: frozenset[str] = frozenset({"messages", "updates", "values", "debug", "custom"})


def _unwrap_stream_item(item: Any) -> tuple[Any, Any]:
    """
    Normalize streamed items to a common (chunk, metadata) shape.

    Supported shapes:
    - (chunk, metadata)                     (LangChain agent.stream(stream_mode="messages"))
    - (mode, payload)                       (LangGraph stream(stream_mode=[...]))
    - (mode, (chunk, metadata))             (LangGraph multi-mode + messages payload carries
      metadata)
    - chunk                                 (fallback: no metadata)
    """
    stream_mode: Optional[str] = None
    chunk: Any = item
    metadata: Any = None

    if isinstance(item, tuple) and len(item) == 2:
        first, second = item
        if isinstance(first, str) and first in _STREAM_MODE_NAMES:
            stream_mode = first
            payload = second
            if isinstance(payload, tuple) and len(payload) == 2:
                chunk, metadata = payload
            else:
                chunk, metadata = payload, None
        else:
            chunk, metadata = first, second

    if stream_mode:
        if metadata is None:
            metadata = {"stream_mode": stream_mode}
        elif isinstance(metadata, dict):
            merged = dict(metadata)
            merged.setdefault("stream_mode", stream_mode)
            metadata = merged
        else:
            metadata = {"stream_mode": stream_mode, "metadata": metadata}

    return chunk, metadata


@dataclass(slots=True)
class AgentConversationBundle:
    """封装一次对话请求需要的上下文，方便在不同模式间复用。"""

    messages: List[Dict[str, str]]
    save_message: str
    original_message: str
    processed_message: str
    image_analysis: Optional[dict] = None
    image_path: Optional[str] = None
    tool_recorder: Optional[ToolTraceRecorder] = None


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


class RequestStageTimer:
    """轻量级请求分段计时器（用于本地链路耗时剖析）。"""

    __slots__ = ("enabled", "label", "_t0", "_last", "_stages", "_max_stages")

    def __init__(self, *, enabled: bool, label: str, max_stages: int = 24) -> None:
        self.enabled = bool(enabled)
        self.label = str(label or "request")
        now = time.perf_counter()
        self._t0 = now
        self._last = now
        self._stages: list[tuple[str, float]] = []
        self._max_stages = max(0, int(max_stages))

    def mark(self, stage: str) -> None:
        if not self.enabled:
            return
        now = time.perf_counter()
        ms = (now - self._last) * 1000
        self._last = now
        if self._max_stages and len(self._stages) >= self._max_stages:
            return
        self._stages.append((str(stage or "stage"), float(ms)))

    def record_ms(self, stage: str, ms: float) -> None:
        if not self.enabled:
            return
        if self._max_stages and len(self._stages) >= self._max_stages:
            return
        try:
            value = float(ms)
        except Exception:
            value = 0.0
        self._stages.append((str(stage or "stage"), value))

    def total_ms(self) -> float:
        return (time.perf_counter() - self._t0) * 1000

    def emit_debug(self, *, outcome: str = "ok") -> None:
        if not self.enabled:
            return
        parts = ", ".join(f"{name}={ms:.1f}ms" for name, ms in self._stages)
        logger.debug(
            "perf[%s](%s) total=%.1fms %s",
            self.label,
            str(outcome or "ok"),
            self.total_ms(),
            parts,
        )


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
        self.memory = memory_manager or MemoryManager(
            user_id=user_id, enable_auto_consolidate=False
        )

        # 高级记忆系统 - 使用用户特定路径
        self.core_memory = CoreMemory(user_id=user_id)

        # 并发记忆检索器（性能优化）
        self.memory_retriever = ConcurrentMemoryRetriever(
            long_term_memory=self.memory,
            core_memory=self.core_memory,
            max_workers=4,
            source_timeout_s=float(
                getattr(settings.agent, "memory_retriever_source_timeout_s", 0.0) or 0.0
            ),
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
        try:
            context_compress_max_tokens = int(
                getattr(settings.agent, "context_compress_max_tokens", 2000)
            )
        except Exception:
            context_compress_max_tokens = 2000
        try:
            context_compress_keep_recent = int(
                getattr(settings.agent, "context_compress_keep_recent_messages", 6)
            )
        except Exception:
            context_compress_keep_recent = 6
        try:
            context_compress_max_important = int(
                getattr(settings.agent, "context_compress_max_important_messages", 12)
            )
        except Exception:
            context_compress_max_important = 12

        self.context_compressor = ContextCompressor(
            max_tokens=context_compress_max_tokens,
            keep_recent=context_compress_keep_recent,
            max_important=context_compress_max_important,
        )
        self.style_learner = StyleLearner(user_id=user_id)
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
        summary_keep = getattr(settings.agent, "context_summary_keep_messages", None)
        if summary_keep is None:
            summary_keep = self._auto_compress_min_messages
        try:
            summary_keep_int = int(summary_keep)
        except Exception:
            summary_keep_int = self._auto_compress_min_messages
        self._history_summary_keep = max(6, summary_keep_int)
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
        self._async_loop_thread = AsyncLoopThread(thread_name="mintchat-agent-async-loop")
        self._state_persist_lock = Lock()
        self._pending_state_persist: Optional[Future] = None
        self._long_term_write_lock = Lock()
        self._pending_long_term_write: Optional[Future] = None
        self._long_term_write_buffer: deque[tuple[str, str, Optional[float]]] = deque()
        self._long_term_write_buffer_max = max(
            0, int(getattr(settings.agent, "long_term_write_buffer_max", 256))
        )
        try:
            drain_max_items = int(getattr(settings.agent, "long_term_write_drain_max_items", 32))
        except Exception:
            drain_max_items = 32
        self._long_term_write_drain_max_items = max(0, drain_max_items)
        try:
            drain_budget_s = float(
                getattr(settings.agent, "long_term_write_drain_budget_s", 0.25) or 0.0
            )
        except Exception:
            drain_budget_s = 0.25
        self._long_term_write_drain_budget_s = max(0.0, drain_budget_s)
        self._background_executor = ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="mintchat-agent-bg",
        )
        self._background_futures: set[Future] = set()
        self._background_lock = Lock()
        self._max_background_queue = 8
        self._context_cache: OrderedDict[tuple[int, str | bytes, str], list[Dict[str, str]]] = (
            OrderedDict()
        )
        self._context_cache_lock = Lock()
        self._context_cache_max = max(
            0, int(getattr(settings.agent, "context_cache_max_entries", 16))
        )
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
        self._tool_rewrite_llm = self._build_tool_rewrite_llm(self.llm)

        # 创建 Agent
        self._agent_middleware = self._build_agent_middleware_stack()
        self.agent = self._create_agent()

        logger.info(f"MintChat 智能体初始化完成 (流式输出: {self.enable_streaming})")

    def _initialize_llm(self):
        """
        初始化语言模型

        Returns:
            LLM 实例

        Raises:
            ValueError: 如果 LLM 提供商不支持或 API Key 未配置
        """
        provider = settings.default_llm_provider
        timeout_s = float(getattr(getattr(self, "_llm_timeouts", None), "total", 120.0))
        api_base = str(getattr(settings.llm, "api", "") or "").strip()

        try:
            streaming_requested = bool(getattr(self, "enable_streaming", False))
            if provider == "openai":
                if ChatOpenAI is None:
                    raise ImportError(
                        "langchain-openai 未安装或导入失败，无法创建 ChatOpenAI。"
                        " 请运行: uv sync --locked --no-install-project"
                    ) from _LANGCHAIN_OPENAI_IMPORT_ERROR
                if "api.openai.com" in api_base.lower() and not settings.openai_api_key:
                    raise ValueError("OpenAI API Key 未配置")

                try:
                    from src.llm.factory import get_llm

                    llm = get_llm(
                        model=self.model_name,
                        temperature=self.temperature,
                        max_tokens=settings.model_max_tokens,
                        timeout_s=timeout_s,
                        max_retries=2,
                        streaming=streaming_requested,
                    )
                except Exception:
                    raise
                logger.info(f"使用 OpenAI 模型: {self.model_name}，超时: {timeout_s:g}秒")

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
                    timeout=timeout_s,
                    max_retries=2,
                )
                if streaming_requested:
                    anthropic_kwargs["streaming"] = True
                try:
                    llm = ChatAnthropic(**anthropic_kwargs)
                except TypeError:
                    anthropic_kwargs.pop("streaming", None)
                    llm = ChatAnthropic(**anthropic_kwargs)
                logger.info(f"使用 Anthropic 模型: {self.model_name}，超时: {timeout_s:g}秒")

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
                    timeout=timeout_s,
                )
                if streaming_requested:
                    google_kwargs["streaming"] = True
                try:
                    llm = ChatGoogleGenerativeAI(**google_kwargs)
                except TypeError:
                    google_kwargs.pop("streaming", None)
                    llm = ChatGoogleGenerativeAI(**google_kwargs)
                logger.info(f"使用 Google 模型: {self.model_name}，超时: {timeout_s:g}秒")

            else:
                # 使用自定义 OpenAI 兼容 API（如 SiliconFlow、DeepSeek 等）
                if ChatOpenAI is None:
                    raise ImportError(
                        "langchain-openai 未安装或导入失败，无法创建 ChatOpenAI。"
                        " 请运行: uv sync --locked --no-install-project"
                    ) from _LANGCHAIN_OPENAI_IMPORT_ERROR

                if "api.openai.com" in api_base.lower() and not settings.llm.key:
                    raise ValueError("API Key 未配置")
                try:
                    from src.llm.factory import get_llm

                    llm = get_llm(
                        model=self.model_name,
                        temperature=self.temperature,
                        max_tokens=settings.model_max_tokens,
                        timeout_s=timeout_s,
                        max_retries=2,
                        streaming=streaming_requested,
                    )
                except Exception:
                    raise
                logger.info(
                    f"使用自定义 OpenAI 兼容 API: {settings.llm.api}, "
                    f"模型: {self.model_name}，超时: {timeout_s:g}秒"
                )

            return llm

        except Exception as e:
            logger.error(f"LLM 初始化失败: {e}")
            raise

    def _build_tool_rewrite_llm(self, llm: Any) -> Any:
        """
        为“工具结果兜底重写”构建更快、更稳定的模型调用配置。

        目标：
        - 尽量减少二次调用的延迟（工具链常见场景：工具已返回但模型未给最终答复）
        - 降低超时概率（默认收敛 max_tokens 与 temperature）
        - 兼容不同 provider：不支持 bind/参数时自动降级
        """
        if llm is None:
            return None

        try:
            max_tokens = int(getattr(settings.agent, "tool_rewrite_max_tokens", 384) or 384)
        except Exception:
            max_tokens = 384
        max_tokens = max(64, min(1024, max_tokens))

        try:
            temperature = float(getattr(settings.agent, "tool_rewrite_temperature", 0.2) or 0.2)
        except Exception:
            temperature = 0.2
        temperature = max(0.0, min(0.7, temperature))

        binder = getattr(llm, "bind", None)
        if not callable(binder):
            return llm

        # Prefer commonly supported kwargs. If the provider rejects them, fall back gracefully.
        candidate_kwargs = (
            {"max_tokens": max_tokens, "temperature": temperature},
            {"max_completion_tokens": max_tokens, "temperature": temperature},
            {"temperature": temperature},
        )
        for kwargs in candidate_kwargs:
            try:
                return binder(**kwargs)
            except TypeError:
                continue
            except Exception:
                continue

        return llm

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

## 工具使用与表达规范

- 工具返回只是“素材”，不要原样粘贴；要用角色语气把信息说得自然、贴心。
- 优先给**结论 + 3~5 个要点**；需要更多细节时，再向主人追问或分步展开。
- 尽量避免输出原始 JSON/超长列表/日志；必要时先总结，再补充关键链接或条目。
- 工具返回为空/失败/超时：说明原因，并给出下一步建议（换关键词、补充城市/出发地等）。

## Live2D 状态事件（可选，面向 GUI 角色表现）

- 你可以在回复中附加**隐藏 JSON 指令**来触发表情/动作：`[[live2d:{"event":"EVENT","intensity":0.0-1.0,"hold_s":0.2-30}]]`
  - UI 会自动剥离该指令，不会显示给主人，也不会保存到聊天记录。
  - 仅用于 Live2D 控制，不要解释，不要放进正文；除这条隐藏指令外不要输出原始 JSON。
  - `event` 可以是**表情语义标签**：`angry/shy/dizzy/love/sad/surprise`，
    也可以是中文关键词（如“猫尾/雾气/鱼干/脸黑”），或直接写 `.exp3.json` 文件名。
  - `event` 也可以是**动作标签**（触发点头/摇头等）：`nod/shake`（同义：`yes/no/affirm/deny/肯定/否定/点头/摇头`）。
  - `intensity` 为 0~1（可省略），`hold_s` 为停留秒数（可省略）。
- 使用原则：**少量、自然、服务于情绪表达**，不要在同一条回复里反复切换；不要向主人解释这些指令。
"""
            system_prompt = base_system_prompt + enhanced_instruction
            # Cache for rescue paths (e.g., tool-result rewrite without re-running the agent graph).
            self._system_prompt = system_prompt

            # 获取工具列表
            tools = self.tool_registry.get_all_tools()
            # Tool tracing/output truncation is handled by Agent middleware (ToolTraceMiddleware).

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

        # 性能优化：fast_mode 下优先跳过“额外一次 LLM 选工具”调用，避免首包延迟/超时。
        try:
            allow_in_fast_mode = bool(getattr(settings.agent, "tool_selector_in_fast_mode", False))
        except Exception:
            allow_in_fast_mode = False
        if getattr(settings.agent, "memory_fast_mode", False) and not allow_in_fast_mode:
            logger.info("fast_mode 跳过 LLM 工具筛选中间件")
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
                getattr(settings.agent, "tool_selector_structured_method", default_method)
                or default_method
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

        # v3.3.6: Tool tracing + output truncation must be done via middleware (ToolNode requires
        # ToolMessage/Command).
        try:
            tool_output_max_chars = int(
                getattr(settings.agent, "tool_output_max_chars", 12000) or 0
            )
        except Exception:
            tool_output_max_chars = 12000
        stack.append(ToolTraceMiddleware(max_output_chars=tool_output_max_chars))

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
        try:
            intensity = float(
                self.emotion_engine.estimate_message_intensity(message, detected_emotion)
            )
        except Exception:
            intensity = 0.6
        intensity = max(0.0, min(1.0, intensity))
        if intensity <= 0.0:
            intensity = 0.6
        self.emotion_engine.update_emotion(
            detected_emotion,
            intensity=intensity,
            trigger="用户消息",
            persist=False,
        )

        # 更新高级情绪系统
        if self.mood_system.enabled:
            is_positive = detected_emotion.value in self._POSITIVE_MOOD_EMOTIONS
            # 将情感强度映射到 mood 输入，保持与旧默认(0.3)同量级，但随强度动态变化
            mood_input = max(0.0, min(1.0, 0.15 + 0.25 * intensity))
            self.mood_system.update_mood(
                impact=mood_input,
                reason=f"user:{getattr(detected_emotion, 'name', detected_emotion)}",
                is_positive=is_positive,
                persist=False,
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
                        parts.append(
                            str(getattr(block, "text", "") or getattr(block, "content", ""))
                        )
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
                            if role_lower in {"assistant", "ai"} or role in {
                                "AIMessageChunk",
                                "AIMessage",
                            }:
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
        self, message: str, reply: str, save_to_long_term: bool
    ) -> None:
        """
        保存交互到记忆系统 (v2.30.34 重构)

        Args:
            message: 用户消息
            reply: AI回复
            save_to_long_term: 是否保存到长期记忆
        """
        # v3.3.8: 将长期记忆写入移出热路径（GUI 默认 save_to_long_term=True，会导致向量写入阻塞）。
        # - 短期记忆：下一轮对话必需，保持同步写入。
        # - 长期记忆：后台合并写入（coalesce），避免影响首包/流式体验。
        self.memory.add_interaction(
            user_message=message,
            assistant_message=reply,
            save_to_long_term=False,
        )
        if save_to_long_term:
            self._enqueue_long_term_write(message, reply, importance=None)

    def _enqueue_long_term_write(
        self,
        user_message: str,
        assistant_message: str,
        *,
        importance: Optional[float],
    ) -> None:
        """后台合并写入长期记忆，避免热路径被向量写入阻塞。"""
        memory = getattr(self, "memory", None)
        if memory is None:
            return

        with self._long_term_write_lock:
            max_buf = int(getattr(self, "_long_term_write_buffer_max", 0) or 0)
            if max_buf > 0:
                while len(self._long_term_write_buffer) >= max_buf:
                    try:
                        self._long_term_write_buffer.popleft()
                    except Exception:
                        break
            self._long_term_write_buffer.append((user_message, assistant_message, importance))

            pending = getattr(self, "_pending_long_term_write", None)
            if pending is not None and hasattr(pending, "done"):
                try:
                    if not pending.done():
                        return
                except Exception:
                    pass

        def _clear(_future: Future) -> None:
            """
            在每个 drain slice 完成后触发：
            1) 清理 pending 标记；2) 若仍有剩余缓冲，则再调度下一片 slice。

            这样可以避免长期写入独占后台线程池，提升系统协同与交互流畅度。
            """
            with self._long_term_write_lock:
                if getattr(self, "_pending_long_term_write", None) is not _future:
                    return
                self._pending_long_term_write = None
                has_remaining = bool(self._long_term_write_buffer)

            if not has_remaining:
                return

            next_future = self._submit_background_task(_drain, label="long-term-write")
            if not next_future:
                return

            with self._long_term_write_lock:
                self._pending_long_term_write = next_future

            try:
                next_future.add_done_callback(_clear)
            except Exception:
                pass

        def _drain() -> None:
            try:
                max_items = int(getattr(self, "_long_term_write_drain_max_items", 0) or 0)
            except Exception:
                max_items = 0
            try:
                budget_s = float(getattr(self, "_long_term_write_drain_budget_s", 0.0) or 0.0)
            except Exception:
                budget_s = 0.0

            start = time.monotonic()
            processed = 0

            while True:
                if max_items > 0 and processed >= max_items:
                    break
                if budget_s > 0.0 and (time.monotonic() - start) >= budget_s:
                    break

                item: Optional[tuple[str, str, Optional[float]]] = None
                with self._long_term_write_lock:
                    try:
                        if self._long_term_write_buffer:
                            item = self._long_term_write_buffer.popleft()
                    except Exception:
                        item = None

                if item is None:
                    break

                processed += 1
                msg, reply, imp = item
                try:
                    add_long_term = getattr(memory, "add_interaction_long_term", None)
                    if callable(add_long_term):
                        add_long_term(user_message=msg, assistant_message=reply, importance=imp)
                    else:
                        # Fallback for older MemoryManager versions.
                        memory.add_interaction(
                            user_message=msg,
                            assistant_message=reply,
                            save_to_long_term=True,
                            importance=imp,
                        )
                except Exception:
                    # 长期记忆写入失败不应影响对话流程
                    pass

            try:
                long_term = getattr(memory, "long_term", None)
                flush_batch = getattr(long_term, "flush_batch", None)
                if callable(flush_batch):
                    flush_batch()
            except Exception:
                pass

            return

        future = self._submit_background_task(_drain, label="long-term-write")
        if not future:
            return
        with self._long_term_write_lock:
            self._pending_long_term_write = future

        try:
            future.add_done_callback(_clear)
        except Exception:
            pass

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
        stage_timer = (
            RequestStageTimer(enabled=True, label="chat")
            if logger.isEnabledFor(logging.DEBUG)
            else None
        )
        outcome = "ok"
        try:
            try:
                logger.info("收到用户消息")
                bundle = self._build_agent_bundle(
                    message,
                    image_analysis=image_analysis,
                    image_path=image_path,
                    compression="auto",
                    use_cache=True,
                    stage_timer=stage_timer,
                )
            except ValueError:
                outcome = "empty"
                logger.warning("收到空消息")
                return "主人，您想说什么呢？喵~"
            except Exception as prep_exc:
                outcome = "prep_error"
                logger.error("准备消息失败: %s", prep_exc)
                return f"抱歉主人，准备消息时出错了：{str(prep_exc)} 喵~"

            if stage_timer:
                stage_timer.mark("build_bundle")

            try:
                response = self._invoke_with_failover(bundle)
                if stage_timer:
                    stage_timer.mark("invoke_llm")

                reply = self._extract_reply_from_response(response)
                if not reply.strip() or reply.strip() == _DEFAULT_EMPTY_REPLY:
                    rescued = self._rescue_empty_reply(bundle, raw_reply=reply, source="chat")
                    if rescued:
                        reply = rescued
                tool_recorder = getattr(bundle, "tool_recorder", None)
                if tool_recorder is not None:
                    user_message = (
                        bundle.original_message or bundle.processed_message or bundle.save_message
                    ) or ""
                    prefers_raw = (
                        self._user_prefers_raw_tool_output(user_message) if user_message else False
                    )
                else:
                    user_message = ""
                    prefers_raw = False
                if tool_recorder is not None and (
                    self._looks_like_progress_only_tool_reply(reply)
                    or (not prefers_raw and self._looks_like_tool_echo_reply(reply, tool_recorder))
                ):
                    fallback = self._format_tool_trace_fallback(
                        tool_recorder, user_message=user_message
                    )
                    if fallback:
                        reply = fallback
                    else:
                        rewritten = self._rewrite_final_reply_from_tool_trace(
                            bundle,
                            tool_recorder=tool_recorder,
                            source="chat-final",
                        )
                        if rewritten:
                            reply = rewritten
                        else:
                            implicit = self._maybe_rescue_implicit_tool_intent(
                                bundle, tool_recorder=tool_recorder
                            )
                            if implicit:
                                reply = implicit

                if not reply.strip():
                    reply = _DEFAULT_EMPTY_REPLY

                self._post_reply_actions(
                    bundle.save_message,
                    reply,
                    save_to_long_term,
                    stream=False,
                )
                if stage_timer:
                    stage_timer.mark("post_reply")

                logger.info("生成回复完成")
                return reply

            except AgentTimeoutError as timeout_exc:
                outcome = "timeout"
                logger.error("对话处理超时: %s", timeout_exc)
                return "抱歉主人，模型那边暂时没有回应，我们稍后再聊好吗？喵~"
            except Exception as e:
                outcome = "error"
                logger.error("对话处理失败: %s", e)
                return f"抱歉主人，我遇到了一些问题：{str(e)} 喵~"
        finally:
            if stage_timer:
                stage_timer.emit_debug(outcome=outcome)

    def _build_memory_context(
        self,
        relevant_memories: List[str],
        core_memories: List[str],
    ) -> str:
        """
        构建记忆上下文（辅助方法）

        Args:
            relevant_memories: 相关记忆列表
            core_memories: 核心记忆列表

        Returns:
            str: 格式化的记忆上下文
        """
        # 早期返回优化
        if not (relevant_memories or core_memories):
            return ""

        # 使用列表推导式和join优化，减少中间对象创建
        sections = [
            "\n【记忆规则】\n"
            "- 以下为检索到的历史内容，请优先据此回答。\n"
            "- 若不足以回答，请明确说明未找到相关记忆，不要编造。\n"
        ]
        if relevant_memories:
            sections.append("\n【相关记忆】\n- " + "\n- ".join(relevant_memories) + "\n")
        if core_memories:
            sections.append("\n【核心记忆】\n- " + "\n- ".join(core_memories) + "\n")
        return "".join(sections) if sections else ""

    def _build_context_with_state(self, use_compression: bool) -> str:
        """
        构建包含情感、情绪和角色状态的上下文（辅助方法）

        Args:
            use_compression: 是否包含较重的角色状态拼接（风格指导将尽量保持轻量并持续注入）

        Returns:
            str: 格式化的状态上下文
        """
        # 极速模式：保留情感/情绪这些轻量但关键的状态，跳过较重的角色状态拼接
        if getattr(settings.agent, "memory_fast_mode", False):
            use_compression = False

        # 使用海象运算符优化
        context_parts = []

        if emotion_context := self.emotion_engine.get_emotion_context():
            context_parts.append(f"\n{emotion_context}\n")

        if self.mood_system.enabled and (mood_context := self.mood_system.get_mood_context()):
            context_parts.append(mood_context)

        if use_compression:
            if character_state_context := self.character_state.get_state_context():
                context_parts.append(character_state_context)

        # 风格指导较轻量：用于工具兜底重写/普通对话都保持一致的“口吻趋向”
        if style_guidance := self.style_learner.get_style_guidance():
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
            if (state_context := self._build_context_with_state(use_compression=False)).strip():
                messages.insert(0, {"role": "system", "content": state_context.strip()})
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
            trimmed_messages = recent_messages[-self._history_summary_keep :]

        retrieval_plan = self._build_retrieval_plan(
            message=message,
            recent_messages=trimmed_messages,
            compression=compression,
        )
        memories = await self.memory_retriever.retrieve_all_memories_async(
            query=message,
            long_term_k=retrieval_plan["long_term_k"],
            core_k=retrieval_plan["core_k"],
            use_cache=use_cache,
        )

        include_state = compression != "off"
        additional_context = history_summary
        additional_context += self._build_context_with_state(include_state)
        memory_context = self._build_memory_context(
            relevant_memories=memories["long_term"],
            core_memories=memories["core"],
        )
        memory_query = any(
            token in message
            for token in (
                "记得",
                "还记得",
                "回忆",
                "聊了什么",
                "说了什么",
                "我们聊",
                "我们说",
                "刚才",
                "刚刚",
                "之前",
                "上次",
                "今天都聊",
                "昨天都聊",
            )
        )
        if memory_query and not memory_context.strip():
            additional_context += (
                "\n【记忆说明】\n" "- 未检索到相关记忆，请直接说明没有记录，不要编造。\n"
            )
        else:
            additional_context += memory_context

        messages: List[Dict[str, str]] = []

        should_compress = compression == "on" or (
            compression == "auto"
            and self._should_compress_context(trimmed_messages, additional_context)
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
            # 没有运行中的事件循环：复用后台 AsyncLoopThread，避免每次 asyncio.run 创建/关闭 event loop
            loop_thread = getattr(self, "_async_loop_thread", None)
            if loop_thread is None:
                loop_thread = AsyncLoopThread(thread_name="mintchat-agent-async-loop")
                try:
                    self._async_loop_thread = loop_thread
                except Exception:
                    pass
            return loop_thread.run(coro_factory(), timeout=300.0)

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
        tool_recorder: Optional[ToolTraceRecorder] = None,
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
            timeout_token = tool_timeout_s_var.set(_tool_timeout())
            trace_token = tool_trace_recorder_var.set(tool_recorder)
            try:
                return self.agent.invoke({"messages": messages})
            finally:
                tool_trace_recorder_var.reset(trace_token)
                tool_timeout_s_var.reset(timeout_token)

        future = self._llm_executor.submit(task)
        timeout_total = (
            self._llm_timeouts.total if timeout_s is None else max(1.0, float(timeout_s))
        )
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
        tool_recorder: Optional[ToolTraceRecorder] = None,
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
            timeout_token = tool_timeout_s_var.set(_tool_timeout())
            trace_token = tool_trace_recorder_var.set(tool_recorder)
            try:
                return self.agent.invoke({"messages": messages})
            finally:
                tool_trace_recorder_var.reset(trace_token)
                tool_timeout_s_var.reset(timeout_token)

        future = self._llm_executor.submit(task)
        timeout_total = (
            self._llm_timeouts.total if timeout_s is None else max(1.0, float(timeout_s))
        )
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
            return self._invoke_agent_with_timeout(
                bundle.messages,
                timeout_s=timeout_s,
                tool_recorder=getattr(bundle, "tool_recorder", None),
            )
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
                return self._invoke_agent_with_timeout(
                    fallback_messages,
                    timeout_s=timeout_s,
                    tool_recorder=getattr(bundle, "tool_recorder", None),
                )
            except AgentTimeoutError as secondary_exc:
                raise AgentTimeoutError("LLM 压缩上下文快速重试仍然超时") from secondary_exc

    async def _ainvoke_with_failover(
        self,
        bundle: AgentConversationBundle,
        *,
        timeout_s: Optional[float] = None,
    ) -> Any:
        """
        对异步环境下的 LLM 调用增加快速压缩重试以提升成功率。
        """
        try:
            return await self._ainvoke_agent_with_timeout(
                bundle.messages,
                timeout_s=timeout_s,
                tool_recorder=getattr(bundle, "tool_recorder", None),
            )
        except AgentTimeoutError as primary_exc:
            if not self._fast_retry_enabled:
                raise

            logger.warning("LLM 调用超时，尝试压缩上下文快速重试(异步)")
            try:
                fallback_messages = await self._prepare_messages_async(
                    bundle.processed_message,
                    compression="on",
                    use_cache=True,
                )
            except Exception as rebuild_exc:
                logger.error("构建快速重试上下文失败: %s", rebuild_exc)
                raise primary_exc

            try:
                return await self._ainvoke_agent_with_timeout(
                    fallback_messages,
                    timeout_s=timeout_s,
                    tool_recorder=getattr(bundle, "tool_recorder", None),
                )
            except AgentTimeoutError as secondary_exc:
                raise AgentTimeoutError("LLM 压缩上下文快速重试仍然超时") from secondary_exc

    def _build_image_analysis_fallback_reply(
        self, bundle: "AgentConversationBundle"
    ) -> Optional[str]:
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

        user_message = (
            bundle.original_message or bundle.processed_message or bundle.save_message
        ) or ""
        tool_recorder = getattr(bundle, "tool_recorder", None)
        tool_trace_fallback = self._format_tool_trace_fallback(
            tool_recorder, user_message=user_message
        )
        if tool_trace_fallback:
            logger.info("空回复使用工具轨迹兜底 (source=%s)", source)
            return tool_trace_fallback

        rewritten = self._rewrite_final_reply_from_tool_trace(
            bundle,
            tool_recorder=tool_recorder,
            source=source,
        )
        if rewritten:
            logger.info("empty-reply tool rewrite rescue (source=%s)", source)
            return rewritten

        implicit = self._maybe_rescue_implicit_tool_intent(bundle, tool_recorder=tool_recorder)
        if implicit:
            logger.info("空回复使用意图工具兜底 (source=%s)", source)
            return implicit

        if not getattr(self, "_fast_retry_enabled", False):
            return None

        try:
            emitted = len(raw_reply)
        except Exception:
            emitted = -1

        logger.warning("检测到空回复，尝试兜底重试 (source=%s, emitted=%s)", source, emitted)

        tool_reply = self._execute_tool_calls_from_text(raw_reply, tool_recorder=tool_recorder)
        if tool_reply:
            tool_trace_fallback = self._format_tool_trace_fallback(
                tool_recorder, user_message=user_message
            )
            if tool_trace_fallback:
                logger.info("空回复使用工具轨迹兜底 (source=%s)", source)
                return tool_trace_fallback

            rewritten = self._rewrite_final_reply_from_tool_trace(
                bundle,
                tool_recorder=tool_recorder,
                source=f"{source}:tool-call-rescue",
            )
            if rewritten:
                logger.info("空回复工具调用解析后重写成功 (source=%s)", source)
                return rewritten

            logger.info("空回复使用工具调用解析结果 (source=%s)", source)
            return tool_reply

        try:
            response = self._invoke_agent_with_timeout(
                bundle.messages,
                tool_recorder=getattr(bundle, "tool_recorder", None),
            )
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
            response = self._invoke_agent_with_timeout(
                fallback_messages,
                tool_recorder=getattr(bundle, "tool_recorder", None),
            )
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

        user_message = (
            bundle.original_message or bundle.processed_message or bundle.save_message
        ) or ""
        tool_recorder = getattr(bundle, "tool_recorder", None)
        tool_trace_fallback = self._format_tool_trace_fallback(
            tool_recorder, user_message=user_message
        )
        if tool_trace_fallback:
            logger.info("空回复使用工具轨迹兜底 (source=%s)", source)
            return tool_trace_fallback

        rewritten = await self._arewrite_final_reply_from_tool_trace(
            bundle,
            tool_recorder=tool_recorder,
            source=source,
        )
        if rewritten:
            logger.info("empty-reply tool rewrite rescue (source=%s)", source)
            return rewritten

        implicit = self._maybe_rescue_implicit_tool_intent(bundle, tool_recorder=tool_recorder)
        if implicit:
            logger.info("空回复使用意图工具兜底 (source=%s)", source)
            return implicit

        if not getattr(self, "_fast_retry_enabled", False):
            return None

        try:
            emitted = len(raw_reply)
        except Exception:
            emitted = -1

        logger.warning("检测到空回复，尝试兜底重试 (source=%s, emitted=%s)", source, emitted)

        tool_reply = self._execute_tool_calls_from_text(raw_reply, tool_recorder=tool_recorder)
        if tool_reply:
            tool_trace_fallback = self._format_tool_trace_fallback(
                tool_recorder, user_message=user_message
            )
            if tool_trace_fallback:
                logger.info("空回复使用工具轨迹兜底 (source=%s)", source)
                return tool_trace_fallback

            rewritten = await self._arewrite_final_reply_from_tool_trace(
                bundle,
                tool_recorder=tool_recorder,
                source=f"{source}:tool-call-rescue",
            )
            if rewritten:
                logger.info("空回复工具调用解析后重写成功 (source=%s)", source)
                return rewritten

            logger.info("空回复使用工具调用解析结果 (source=%s)", source)
            return tool_reply

        try:
            response = await self._ainvoke_agent_with_timeout(
                bundle.messages,
                tool_recorder=getattr(bundle, "tool_recorder", None),
            )
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
            response = await self._ainvoke_agent_with_timeout(
                fallback_messages,
                tool_recorder=getattr(bundle, "tool_recorder", None),
            )
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
            # 清理已完成的 future，避免队列计数偏大导致误丢任务。
            try:
                done_futures = [f for f in self._background_futures if f.done()]
                for f in done_futures:
                    self._background_futures.discard(f)
            except Exception:
                pass

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
            self.style_learner.learn_from_message(message, persist=False)
        except Exception as exc:
            logger.warning("更新对话风格失败: %s", exc)

        try:
            self.character_state.on_interaction(channel, persist=False)
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
        tokens = sum(
            self.context_compressor.estimate_tokens(msg.get("content", "")) for msg in messages
        )
        tokens += self.context_compressor.estimate_tokens(additional_context)

        if token_budget > 0 and tokens >= token_budget * self._auto_compress_ratio:
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
        }

        message_len = len(message)
        if message_len <= 32:
            plan["long_term_k"] = 3
        elif message_len >= 200:
            plan["long_term_k"] = 8

        turns = len(recent_messages)
        if turns >= 24:
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
        stage_timer: Optional["RequestStageTimer"] = None,
    ) -> AgentConversationBundle:
        """
        异步构建对话请求包，供 chat / stream / failover 共用。
        """
        message = (message or "").strip()
        if not message:
            raise ValueError("收到空消息")
        if len(message) > 8000:
            raise ValueError("消息过长，请精简后再试")
        timer = stage_timer if isinstance(stage_timer, RequestStageTimer) else None
        t0 = time.perf_counter() if (timer and timer.enabled) else 0.0

        original_message, enriched_message = self._prepare_interaction_context(
            message,
            image_analysis=image_analysis,
            image_path=image_path,
        )
        if t0:
            timer.record_ms("bundle.pre", (time.perf_counter() - t0) * 1000)
            t0 = time.perf_counter()

        try:
            prepare_timeout_s = float(
                getattr(settings.agent, "bundle_prepare_timeout_s", 0.0) or 0.0
            )
        except Exception:
            prepare_timeout_s = 0.0
        prepare_timeout_s = max(0.0, prepare_timeout_s)

        try:
            if prepare_timeout_s > 0.0:
                prepared_messages = await asyncio.wait_for(
                    self._prepare_messages_async(
                        enriched_message,
                        compression=compression,
                        use_cache=use_cache,
                    ),
                    timeout=prepare_timeout_s,
                )
            else:
                prepared_messages = await self._prepare_messages_async(
                    enriched_message,
                    compression=compression,
                    use_cache=use_cache,
                )
        except asyncio.TimeoutError:
            logger.warning(
                "构建对话上下文超时(%.0fms)，已降级到快路径(最近消息)",
                prepare_timeout_s * 1000,
            )
            recent_messages = self.memory.get_recent_messages()
            trimmed_messages = recent_messages[-4:] if len(recent_messages) > 4 else recent_messages
            prepared_messages = list(trimmed_messages)
            if (state_context := self._build_context_with_state(use_compression=False)).strip():
                prepared_messages.insert(0, {"role": "system", "content": state_context.strip()})
            prepared_messages.append({"role": "user", "content": enriched_message})
        if t0:
            timer.record_ms("bundle.prepare", (time.perf_counter() - t0) * 1000)

        return AgentConversationBundle(
            messages=prepared_messages,
            save_message=original_message,
            original_message=original_message,
            processed_message=enriched_message,
            image_analysis=image_analysis,
            image_path=image_path,
            tool_recorder=ToolTraceRecorder(),
        )

    def _build_agent_bundle(
        self,
        message: str,
        *,
        image_analysis: Optional[dict] = None,
        image_path: Optional[str] = None,
        compression: Literal["auto", "on", "off"] = "auto",
        use_cache: bool = True,
        stage_timer: Optional["RequestStageTimer"] = None,
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
                stage_timer=stage_timer,
            )
        )

    def _stream_llm_response(
        self,
        messages: list,
        *,
        tool_recorder: Optional[ToolTraceRecorder] = None,
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
            timeout_token = tool_timeout_s_var.set(
                float(getattr(settings.agent, "tool_timeout_s", 30.0))
                if getattr(settings.agent, "tool_timeout_s", 30.0)
                else None
            )
            trace_token = tool_trace_recorder_var.set(tool_recorder)
            try:
                try:
                    stream_holder["iterator"] = self.agent.stream(
                        {"messages": messages},
                        stream_mode="messages",
                    )
                    for item in stream_holder["iterator"]:
                        if stop_event.is_set() or (cancel_event and cancel_event.is_set()):
                            break
                        chunk, metadata = _unwrap_stream_item(item)
                        stream_mode = (
                            metadata.get("stream_mode") if isinstance(metadata, dict) else None
                        )
                        skip_internal = bool(
                            stream_mode and str(stream_mode).lower() != "messages"
                        ) or _metadata_looks_like_internal_routing(metadata)
                        while True:
                            if stop_event.is_set() or (cancel_event and cancel_event.is_set()):
                                break
                            try:
                                # Keep queue payload small: we only need a boolean for internal
                                # routing/tool traces.
                                chunk_queue.put(("data", (chunk, skip_internal)), timeout=0.1)
                                break
                            except Full:
                                continue
                finally:
                    tool_trace_recorder_var.reset(trace_token)
                    tool_timeout_s_var.reset(timeout_token)
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

                    tools_in_flight = 0
                    tool_done_at: Optional[float] = None
                    if tool_recorder is not None:
                        try:
                            in_flight, first_done_at, last_act = tool_recorder.state()
                        except Exception:
                            in_flight, first_done_at, last_act = 0, None, 0.0
                        tools_in_flight = in_flight
                        if in_flight > 0:
                            # 工具执行期间可能不会产生任何 stream chunk；这里保持看门狗活跃，避免误判“无输出超时”。
                            watchdog.mark_chunk()
                        # 仅当“工具不再执行中”时，才允许触发“工具结果直出兜底”。
                        if in_flight <= 0 and first_done_at is not None:
                            tool_done_at = last_act

                    tool_stream_ready = (
                        tool_first_received_at is not None
                        and (time.perf_counter() - tool_first_received_at) >= tool_direct_grace_s
                    )
                    if tool_recorder is not None and tools_in_flight > 0:
                        # 仍有工具在执行：不要因为“某个 tool 已返回”就提前中止后续工具链。
                        tool_stream_ready = False

                    # 若已经拿到 tool 结果但 assistant 迟迟不输出，则直接把 tool 结果作为回复返回，避免总超时。
                    if total_chars <= 0 and (
                        tool_stream_ready
                        or (
                            tool_done_at is not None
                            and (time.perf_counter() - tool_done_at) >= tool_direct_grace_s
                        )
                    ):
                        stop_event.set()
                        _close_stream()
                        break
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
            if total_chars <= 0:
                # Intentionally do not emit raw tool output here; `chat_stream` will
                # trigger a rewrite rescue based on the recorded tool traces.
                pass
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
        tool_recorder: Optional[ToolTraceRecorder] = None,
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
        timeout_token = tool_timeout_s_var.set(
            float(getattr(settings.agent, "tool_timeout_s", 30.0))
            if getattr(settings.agent, "tool_timeout_s", 30.0)
            else None
        )
        trace_token = tool_trace_recorder_var.set(tool_recorder)

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
            tool_first_received_at: Optional[float] = None
            tool_direct_grace_s = max(
                0.0,
                float(getattr(settings.agent, "tool_direct_grace_s", 1.5)),
            )
            prefix_stripper = StreamStructuredPrefixStripper(
                max_fragments=5, max_buffer_chars=100_000
            )
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
                        item = await asyncio.wait_for(
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

                        tool_done_at: Optional[float] = None
                        tools_in_flight = 0
                        if tool_recorder is not None:
                            try:
                                in_flight, first_done_at, last_act = tool_recorder.state()
                            except Exception:
                                in_flight, first_done_at, last_act = 0, None, 0.0
                            tools_in_flight = in_flight
                            if in_flight > 0:
                                # 工具执行期间可能不会产生任何 stream chunk；这里保持看门狗活跃，避免误判“无输出超时”。
                                watchdog.mark_chunk()
                            if in_flight <= 0 and first_done_at is not None:
                                tool_done_at = last_act

                        tool_stream_ready = (
                            tool_first_received_at is not None
                            and total_chars <= 0
                            and (time.perf_counter() - tool_first_received_at)
                            >= tool_direct_grace_s
                        )
                        if tool_recorder is not None and tools_in_flight > 0:
                            tool_stream_ready = False

                        if tool_stream_ready:
                            await _safe_aclose()
                            break
                        if (
                            tool_done_at is not None
                            and total_chars <= 0
                            and (time.perf_counter() - tool_done_at) >= tool_direct_grace_s
                        ):
                            await _safe_aclose()
                            break
                        if watchdog.remaining_total() > 0:
                            continue
                        await _safe_aclose()
                        raise AgentTimeoutError("LLM 异步流式输出在规定时间内无响应") from exc

                    chunk, metadata = _unwrap_stream_item(item)
                    stream_mode = (
                        metadata.get("stream_mode") if isinstance(metadata, dict) else None
                    )

                    first_latency = watchdog.mark_chunk()
                    if first_latency and not first_latency_logged:
                        first_latency_logged = True

                    tool_text = self._extract_tool_stream_text(chunk)
                    if tool_text:
                        normalized_tool = MintChatAgent._normalize_output_text(tool_text)
                        if normalized_tool:
                            if tool_first_received_at is None:
                                tool_first_received_at = time.perf_counter()

                    if bool(stream_mode and str(stream_mode).lower() != "messages") or (
                        _metadata_looks_like_internal_routing(metadata)
                    ):
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
            tool_trace_recorder_var.reset(trace_token)
            tool_timeout_s_var.reset(timeout_token)
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
            if "trace_scrubber" in locals() and "coalescer" in locals():
                scrub_tail = trace_scrubber.flush()
                if scrub_tail:
                    buffered = coalescer.push(scrub_tail)
                    if buffered:
                        chunk_count += 1
                        total_chars += len(buffered)
                        yield buffered
            if "coalescer" in locals():
                tail = coalescer.flush()
                if tail:
                    chunk_count += 1
                    total_chars += len(tail)
                    yield tail

            if total_chars <= 0:
                # Intentionally do not emit raw tool output here; `chat_stream` will
                # trigger a rewrite rescue based on the recorded tool traces.
                pass
            # v3.3.4: 确保stream被关闭（在所有情况下）
            await _safe_aclose()
            if "chunk_count" in locals():
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
                                parts.append(
                                    str(getattr(block, "text", "") or getattr(block, "content", ""))
                                )
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
                        parts.append(
                            str(getattr(block, "text", "") or getattr(block, "content", ""))
                        )
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

    def _format_tool_trace_fallback(
        self,
        tool_recorder: Optional[ToolTraceRecorder],
        *,
        user_message: Optional[str] = None,
    ) -> str:
        """
        将 recorder 中的工具轨迹整理为可展示文本。

        用途：当模型在工具调用后未能输出可展示文本（空回复/流式超时）时，
        直接把工具结果作为“最后兜底”，避免用户看到空白。
        """
        if tool_recorder is None:
            return ""
        try:
            traces = tool_recorder.snapshot()
        except Exception:
            return ""
        if not traces:
            return ""

        user_name = str(getattr(settings.agent, "user", "主人") or "主人").strip() or "主人"
        if user_message and self._user_prefers_raw_tool_output(user_message):
            parts: list[str] = []
            seen: set[str] = set()
            for trace in traces[-3:]:
                output = (getattr(trace, "output", "") or "").strip()
                error = (getattr(trace, "error", "") or "").strip()
                text = (output or error).strip()
                if not text or text in seen:
                    continue
                seen.add(text)
                parts.append(text)
            return "\n\n".join(parts).strip()

        def _maybe_parse_json(text: str) -> Any:
            raw = (text or "").strip()
            if not raw:
                return None
            if raw[0] not in "{[":
                return None
            if raw[-1] not in "}]":
                return None
            if len(raw) > 200_000:
                return None
            fragment = _extract_leading_json_fragment(raw)
            if not fragment:
                return None
            try:
                return json.loads(fragment)
            except Exception:
                return None

        def _as_clean_text(value: Any, *, max_chars: int = 120) -> str:
            if value is None:
                return ""
            if isinstance(value, bool):
                return "是" if value else "否"
            if isinstance(value, (int, float)):
                return str(value)
            if isinstance(value, str):
                text = value.strip()
                if len(text) > max_chars:
                    return text[: max_chars - 1].rstrip() + "…"
                return text
            try:
                dumped = json.dumps(value, ensure_ascii=False)
            except Exception:
                dumped = str(value)
            dumped = dumped.strip()
            if len(dumped) > max_chars:
                return dumped[: max_chars - 1].rstrip() + "…"
            return dumped

        def _fmt_json_result(tool_name: str, payload: Any) -> str:
            if isinstance(payload, dict):
                # Time-like payloads (e.g., get_time_in_timezone)
                date = _as_clean_text(payload.get("date") or payload.get("local_date"))
                time_s = _as_clean_text(payload.get("time") or payload.get("local_time"))
                timezone = _as_clean_text(payload.get("timezone") or payload.get("tz"))
                weekday = _as_clean_text(payload.get("day_of_week") or payload.get("weekday"))
                datetime_s = _as_clean_text(payload.get("datetime") or payload.get("current_time"))
                if date and time_s:
                    value = f"{date} {time_s}".strip()
                else:
                    value = datetime_s.replace("T", " ").strip() if datetime_s else time_s
                if value and (
                    "time" in tool_name
                    or "date" in tool_name
                    or timezone
                    or date
                    or time_s
                    or "timezone" in tool_name
                ):
                    where = f"{timezone} " if timezone else ""
                    suffix = f"（{weekday}）" if weekday else ""
                    return f"{user_name}，{where}现在是 {value}{suffix} 喵~".strip()

                # Weather-like payloads (covers many AMap variants)
                if any(
                    key in payload
                    for key in (
                        "weather",
                        "temperature",
                        "temperature_c",
                        "humidity",
                        "humidity_percent",
                        "wind",
                        "winddirection",
                        "windDirection",
                        "windpower",
                        "windPower",
                    )
                ):
                    kv: dict[str, str] = {}
                    city = _as_clean_text(payload.get("city"))
                    if city:
                        kv["city"] = city
                    weather = _as_clean_text(payload.get("weather"))
                    if weather:
                        kv["weather"] = weather
                    temp = payload.get("temperature_c")
                    if temp is None:
                        temp = payload.get("temperature")
                    temp_s = _as_clean_text(temp)
                    if temp_s:
                        temp_s = re.sub(r"[^0-9.+-]", "", temp_s) or temp_s
                        kv["temperature_c"] = temp_s
                    wind = _as_clean_text(payload.get("wind"))
                    if not wind:
                        wind_dir = _as_clean_text(
                            payload.get("winddirection") or payload.get("windDirection")
                        )
                        wind_power = _as_clean_text(
                            payload.get("windpower") or payload.get("windPower")
                        )
                        wind = (wind_dir + wind_power).strip()
                    if wind:
                        kv["wind"] = wind
                    humidity = payload.get("humidity_percent")
                    if humidity is None:
                        humidity = payload.get("humidity")
                    humidity_s = _as_clean_text(humidity)
                    if humidity_s:
                        humidity_s = re.sub(r"[^0-9.+-]", "", humidity_s) or humidity_s
                        kv["humidity_percent"] = humidity_s
                    tip = _as_clean_text(
                        payload.get("tip") or payload.get("advice") or payload.get("notice")
                    )
                    if tip:
                        kv["tip"] = tip
                    return _fmt_weather(kv)

                # Search-like payloads: {"results": [...], "query": "..."}
                if isinstance(payload.get("results"), list):
                    results_raw = payload.get("results") or []
                    results_lines: list[str] = []
                    for item in results_raw[:10]:
                        if isinstance(item, dict):
                            title = _as_clean_text(item.get("title") or item.get("name"))
                            link = _as_clean_text(
                                item.get("url") or item.get("link") or item.get("href")
                            )
                            snippet = _as_clean_text(item.get("snippet") or item.get("description"))
                            parts = [p for p in (title, link, snippet) if p]
                            if parts:
                                results_lines.append(" | ".join(parts))
                        else:
                            line = _as_clean_text(item, max_chars=160)
                            if line:
                                results_lines.append(line)
                    kv = {"query": _as_clean_text(payload.get("query") or payload.get("keyword"))}
                    return _fmt_web_search(kv, results_lines)

                # POI/map-like payloads: {"pois": [...], "city": "...", "keywords": "..."}
                if isinstance(payload.get("pois"), list):
                    pois = payload.get("pois") or []
                    result_lines: list[str] = []
                    for poi in pois[:10]:
                        if not isinstance(poi, dict):
                            continue
                        name = _as_clean_text(poi.get("name"))
                        if not name:
                            continue
                        address = _as_clean_text(poi.get("address"))
                        distance = _as_clean_text(poi.get("distance") or poi.get("distance_m"))
                        tel = _as_clean_text(poi.get("tel") or poi.get("phone"))
                        extras: list[str] = []
                        if address:
                            extras.append(f"address={address}")
                        if distance:
                            extras.append(f"distance_m={distance}")
                        if tel:
                            extras.append(f"tel={tel}")
                        suffix = " | " + " | ".join(extras) if extras else ""
                        result_lines.append(f"{len(result_lines) + 1}. {name}{suffix}")
                    kv = {
                        "keywords": _as_clean_text(
                            payload.get("keywords") or payload.get("keyword") or payload.get("q")
                        ),
                        "city": _as_clean_text(payload.get("city")),
                    }
                    return _fmt_map_search(kv, result_lines)

                # Generic dict: show a small set of scalar fields.
                bullets: list[str] = []
                for key, value in payload.items():
                    if len(bullets) >= 5:
                        break
                    if value is None or isinstance(value, (dict, list)):
                        continue
                    v = _as_clean_text(value)
                    if not v:
                        continue
                    bullets.append(f"- {str(key).strip()}: {v}")
                if bullets:
                    return (f"{user_name}，我查到这些信息：\n" + "\n".join(bullets)).strip()
                keys = [str(k).strip() for k in list(payload.keys())[:6] if str(k).strip()]
                if keys:
                    more = "…" if len(payload) > len(keys) else ""
                    return f"{user_name}，我拿到了一些数据字段：{', '.join(keys)}{more}。你想让我重点解释哪一项喵~"
                return f"{user_name}，我拿到了工具结果，不过信息有点复杂，需要我按哪个字段重点解释呢？喵~"

            if isinstance(payload, list):
                if not payload:
                    return f"{user_name}，我这边暂时没有查到结果喵~"
                preview: list[str] = []
                for item in payload[:3]:
                    if isinstance(item, dict):
                        name = _as_clean_text(item.get("name") or item.get("title"))
                        preview.append(name or _as_clean_text(item, max_chars=120))
                    else:
                        preview.append(_as_clean_text(item, max_chars=120))
                preview = [p for p in preview if p]
                if preview:
                    lines = [f"{user_name}，我查到这些结果："]
                    lines.extend(f"- {p}" for p in preview)
                    if len(payload) > 3:
                        lines.append(f"（还有 {len(payload) - 3} 条，需要我继续展开吗？）")
                    return "\n".join(lines).strip()
                return f"{user_name}，我拿到了一些结果，但内容不太规整，需要我换个方式再整理一下吗？喵~"

            return ""

        def _split_tool_result(text: str) -> tuple[str, dict[str, str], list[str]]:
            raw = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
            if not raw:
                return "", {}, []
            lines = [ln.strip() for ln in raw.split("\n") if ln.strip()]
            if not lines:
                return "", {}, []
            first = lines[0]
            tool_from_header = ""
            start_idx = 0
            if first.lower().startswith("tool_result"):
                _prefix, _sep, rest = first.partition(":")
                tool_from_header = rest.strip()
                start_idx = 1

            kv: dict[str, str] = {}
            results: list[str] = []
            in_results = False
            for ln in lines[start_idx:]:
                lower_ln = ln.lower()
                if lower_ln == "results:":
                    in_results = True
                    continue
                if in_results:
                    results.append(ln)
                    continue
                if ":" in ln:
                    k, v = ln.split(":", 1)
                    key = k.strip()
                    if key:
                        kv[key] = v.strip()
                else:
                    # Best-effort: treat as a free-form continuation.
                    results.append(ln)
            return tool_from_header, kv, results

        def _fmt_time(kv: dict[str, str], raw: str) -> str:
            value = (kv.get("local_time") or "").strip()
            if not value:
                match = re.search(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}", raw)
                value = match.group(0) if match else ""
            return (
                f"{user_name}，现在是 {value} 喵~"
                if value
                else f"{user_name}，我这边没有拿到明确的时间喵~"
            )

        def _fmt_date(kv: dict[str, str]) -> str:
            date = (kv.get("local_date") or kv.get("date") or "").strip()
            weekday = (kv.get("weekday") or "").strip()
            if date and weekday:
                return f"{user_name}，今天是 {date}（{weekday}）喵~"
            if date:
                return f"{user_name}，今天是 {date} 喵~"
            return f"{user_name}，我这边没有拿到明确的日期喵~"

        def _fmt_weather(kv: dict[str, str]) -> str:
            city = (kv.get("city") or "").strip()
            error = (kv.get("error") or "").strip()
            hint = (kv.get("hint") or "").strip()
            detail = (kv.get("detail") or "").strip()
            if error:
                if error == "missing_amap_key":
                    return (
                        f"{user_name}，我想帮你查天气，不过我这边还没配置高德 API Key。"
                        f"你可以在 config.user.yaml 里填 AMAP.api_key（或设置环境变量 AMAP_API_KEY），"
                        "然后再问我一次喵~"
                    )
                message = f"{user_name}，天气查询失败了（{error}）"
                if city:
                    message = f"{user_name}，{city} 的天气查询失败了（{error}）"
                if detail:
                    message += f"：{detail}"
                if hint and hint not in detail:
                    message += f"\n{hint}"
                return message.strip()

            weather = (kv.get("weather") or "").strip()
            temperature = (kv.get("temperature_c") or kv.get("temperature") or "").strip()
            wind = (kv.get("wind") or "").strip()
            humidity = (kv.get("humidity_percent") or kv.get("humidity") or "").strip()
            tip = (kv.get("tip") or "").strip()

            chunks: list[str] = []
            if city:
                chunks.append(city)
            if weather:
                chunks.append(f"现在{weather}")
            if temperature:
                chunks.append(f"{temperature}℃")
            if wind:
                chunks.append(f"风：{wind}")
            if humidity:
                chunks.append(f"湿度：{humidity}%")
            head = "，".join(chunks).strip("，")
            if not head:
                head = "我这边查到了天气信息"
            message = f"{user_name}，{head}。"
            if tip:
                if not tip.endswith(("。", "！", "?", "？", "~")):
                    tip = tip.rstrip() + "。"
                message += tip
            message += "喵~"
            return message

        def _fmt_map_search(kv: dict[str, str], results: list[str]) -> str:
            kw = (kv.get("keywords") or "").strip()
            city = (kv.get("city") or "").strip()
            error = (kv.get("error") or "").strip()
            hint = (kv.get("hint") or "").strip()
            detail = (kv.get("detail") or "").strip()
            if error:
                if error == "missing_amap_key":
                    return (
                        f"{user_name}，我想帮你查地图，不过我这边还没配置高德 API Key。"
                        f"你可以在 config.user.yaml 里填 AMAP.api_key（或设置环境变量 AMAP_API_KEY），"
                        "然后再问我一次喵~"
                    )
                message = f"{user_name}，地图查询失败了（{error}）"
                if detail:
                    message += f"：{detail}"
                if hint and hint not in detail:
                    message += f"\n{hint}"
                return message.strip()

            where = city or "附近"
            if kv.get("results", "").strip() == "[]":
                query = f"“{kw}”" if kw else "这个关键词"
                return f"{user_name}，我在{where}没有找到 {query} 相关的地点喵~"

            def _fmt_poi(line: str) -> str:
                raw = (line or "").strip()
                raw = re.sub(r"^\d+\.\s*", "", raw)
                parts = [p.strip() for p in raw.split(" | ") if p.strip()]
                if not parts:
                    return raw
                name = parts[0]
                fields: dict[str, str] = {}
                for part in parts[1:]:
                    if "=" not in part:
                        continue
                    k, v = part.split("=", 1)
                    key = k.strip()
                    value = v.strip()
                    if key and value:
                        fields[key] = value
                extras: list[str] = []
                dist = fields.get("distance_m") or fields.get("distance") or ""
                addr = fields.get("address") or ""
                tel = fields.get("tel") or ""
                if dist:
                    extras.append(f"约{dist}m")
                if addr:
                    extras.append(addr)
                if tel:
                    extras.append(f"电话:{tel}")
                if extras:
                    return f"{name}（{'，'.join(extras)}）"
                return name

            items = [_fmt_poi(line) for line in results if (line or "").strip()]
            items = [i for i in items if i]
            if not items:
                return f"{user_name}，我在{where}暂时没找到合适的地点喵~"
            top = items[:3]
            query = f"“{kw}”" if kw else "相关"
            lines = [f"{user_name}，我在{where}帮你找了{query}的地点："]
            lines.extend(f"- {item}" for item in top)
            lines.append("想让我按距离/评分再筛一筛吗？喵~")
            return "\n".join(lines).strip()

        def _fmt_web_search(kv: dict[str, str], results: list[str]) -> str:
            query = (kv.get("query") or "").strip()
            answer = (kv.get("answer") or "").strip()
            error = (kv.get("error") or "").strip()
            hint = (kv.get("hint") or "").strip()
            providers = (kv.get("providers_tried") or "").strip()
            if error:
                message = f"{user_name}，我这边搜索失败了（{error}）喵~"
                if providers:
                    message += f"\n已尝试：{providers}"
                if hint:
                    message += f"\n小建议：{hint}"
                return message.strip()

            def _fmt_hit(line: str) -> str:
                raw = (line or "").strip()
                raw = re.sub(r"^\d+\.\s*", "", raw)
                parts = [p.strip() for p in raw.split(" | ") if p.strip()]
                if not parts:
                    return raw
                title = parts[0]
                link = parts[1] if len(parts) >= 2 else ""
                snippet = parts[2] if len(parts) >= 3 else ""
                if snippet and len(snippet) > 60:
                    snippet = snippet[:59].rstrip() + "…"
                if link:
                    return f"{title}（{link}）" + (f"：{snippet}" if snippet else "")
                return f"{title}" + (f"：{snippet}" if snippet else "")

            items = [_fmt_hit(line) for line in results if (line or "").strip()]
            items = [i for i in items if i]
            if not items and not answer:
                q = f"“{query}”" if query else "这个关键词"
                return f"{user_name}，我暂时没搜到 {q} 的结果喵~ 你要不要换个关键词试试？"

            lines: list[str] = []
            if answer:
                lines.append(answer)
            if items:
                q = f"“{query}”" if query else ""
                lines.append(f"{user_name}，我搜到{q}这些可能有用的结果：")
                for item in items[:3]:
                    lines.append(f"- {item}")
                lines.append("想让我点开其中一条继续深挖吗？喵~")
            return "\n".join(lines).strip()

        parts: list[str] = []
        seen: set[str] = set()
        for trace in traces[-5:]:
            output = (getattr(trace, "output", "") or "").strip()
            error = (getattr(trace, "error", "") or "").strip()
            name = (getattr(trace, "name", "") or "").strip() or "tool"
            text = output or ""

            if output:
                first_line = (
                    output.splitlines()[0].strip() if output.splitlines() else output.strip()
                )
                if first_line.lower().startswith("tool_result"):
                    _tool, kv, results = _split_tool_result(output)
                    tool_name = (_tool or name).strip()
                    if tool_name == "get_current_time":
                        text = _fmt_time(kv, output)
                    elif tool_name == "get_current_date":
                        text = _fmt_date(kv)
                    elif tool_name == "get_weather":
                        text = _fmt_weather(kv)
                    elif tool_name == "map_search":
                        text = _fmt_map_search(kv, results)
                    elif tool_name == "web_search":
                        text = _fmt_web_search(kv, results)
                    else:
                        # Generic TOOL_RESULT: keep it minimal and user-facing.
                        if error:
                            text = f"{user_name}，我这边查询时遇到点问题：{error} 喵~"
                        elif results:
                            lines = [f"{user_name}，我查到这些信息："]
                            for item in results[:3]:
                                lines.append(f"- {item}")
                            text = "\n".join(lines).strip()
                        else:
                            # Drop the TOOL_RESULT header line, keep key-values if any.
                            bullet = []
                            for k, v in list(kv.items())[:5]:
                                if k and v:
                                    bullet.append(f"- {k}: {v}")
                            text = "\n".join(bullet).strip() if bullet else ""
                else:
                    parsed = _maybe_parse_json(output)
                    if parsed is not None:
                        formatted = _fmt_json_result(name, parsed)
                        if formatted:
                            text = formatted

            if not text and error:
                text = f"{user_name}，我这边查询时遇到点问题：{error} 喵~"

            text = (text or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            parts.append(text)

        if not parts:
            return ""
        return "\n\n".join(parts[-3:]).strip()

    @staticmethod
    def _format_tool_trace_for_rewrite(
        tool_recorder: Optional[ToolTraceRecorder],
        *,
        max_traces: int = 4,
    ) -> str:
        """Format tool traces for a secondary LLM rewrite (role-played final answer)."""
        if tool_recorder is None:
            return ""
        try:
            traces = tool_recorder.snapshot()
        except Exception:
            return ""
        if not traces:
            return ""

        lines: list[str] = []
        for trace in traces[-max(1, int(max_traces)) :]:
            name = (getattr(trace, "name", "") or "").strip() or "tool"
            args = getattr(trace, "args", None)
            try:
                args_text = (
                    json.dumps(args or {}, ensure_ascii=False) if isinstance(args, dict) else "{}"
                )
            except Exception:
                args_text = "{}"
            output = (getattr(trace, "output", "") or "").strip()
            error = (getattr(trace, "error", "") or "").strip()
            duration_s = None
            try:
                duration_s = float(getattr(trace, "duration_s", None))
            except Exception:
                duration_s = None

            if error and not output:
                result_text = f"[ERROR] {error}"
            else:
                result_text = output or error or ""
            result_text = result_text.strip()
            if not result_text:
                continue

            dur_text = (
                f" ({duration_s:.2f}s)" if isinstance(duration_s, float) and duration_s >= 0 else ""
            )
            lines.append(f"- {name} args={args_text}{dur_text}\n  result: {result_text}")

        return "\n".join(lines).strip()

    @staticmethod
    def _infer_implicit_tool_intents(user_message: str) -> list[str]:
        """
        推断“用户显式在问工具能力，但模型未触发工具调用”的简单意图。

        仅用于兜底：当模型输出了“我这就去查/让我看看”等进度话术或空回复，且本轮没有任何工具轨迹时，
        通过本地执行轻量工具（时间/日期）避免用户体验断裂。
        """
        message = (user_message or "").strip()
        if not message:
            return []

        # 防误触：避免把“设置提醒/日程”等当作“查询当前时间”。
        if any(
            kw in message
            for kw in (
                "提醒",
                "闹钟",
                "定时",
                "倒计时",
                "日程",
                "预约",
                "开会",
                "设置提醒",
                "提醒我",
            )
        ):
            return []

        intents: list[str] = []

        # 时间查询
        if "几点" in message or re.search(r"(现在|当前|此刻).{0,8}(时间)", message):
            intents.append("get_current_time")

        # 日期/星期查询
        if (
            ("今天" in message and any(k in message for k in ("几号", "日期", "星期", "周几")))
            or "星期几" in message
            or "周几" in message
            or ("日期" in message and any(k in message for k in ("今天", "当前", "现在")))
        ):
            intents.append("get_current_date")

        # 去重但保序
        seen: set[str] = set()
        ordered: list[str] = []
        for tool_name in intents:
            if tool_name in seen:
                continue
            seen.add(tool_name)
            ordered.append(tool_name)
        return ordered

    def _maybe_rescue_implicit_tool_intent(
        self,
        bundle: "AgentConversationBundle",
        *,
        tool_recorder: Optional[ToolTraceRecorder],
    ) -> Optional[str]:
        """
        当模型“像是在要用工具”但本轮没有工具轨迹时，本地执行轻量工具并生成最终回复。

        设计目标：非破坏性、仅兜底；不改变正常工具调用/LLM 输出的主路径。
        """
        if tool_recorder is None:
            return None

        try:
            enabled = bool(getattr(settings.agent, "implicit_tool_rescue_enabled", True))
        except Exception:
            enabled = True
        if not enabled:
            return None

        try:
            if tool_recorder.snapshot():
                return None
        except Exception:
            # 若 snapshot 异常，保守起见不做兜底执行
            return None

        user_message = (
            (getattr(bundle, "original_message", "") or "").strip()
            or (getattr(bundle, "save_message", "") or "").strip()
            or (getattr(bundle, "processed_message", "") or "").strip()
        )
        if not user_message:
            return None

        intents = self._infer_implicit_tool_intents(user_message)
        if not intents:
            return None

        try:
            tool_timeout_s = float(getattr(settings.agent, "tool_timeout_s", 30.0))
        except Exception:
            tool_timeout_s = 30.0
        if tool_timeout_s <= 0:
            tool_timeout_s = 30.0

        for tool_name in intents:
            started_at = time.perf_counter()
            try:
                tool_recorder.mark_start()
            except Exception:
                pass

            try:
                output = self.tool_registry.execute_tool(tool_name, timeout=tool_timeout_s)
                tool_recorder.record_end(
                    tool_name,
                    {},
                    started_at=started_at,
                    output=str(output or ""),
                )
            except Exception as exc:
                try:
                    tool_recorder.record_end(
                        tool_name,
                        {},
                        started_at=started_at,
                        error=str(exc) or repr(exc),
                    )
                except Exception:
                    pass

        reply = self._format_tool_trace_fallback(tool_recorder, user_message=user_message)
        return reply.strip() or None

    @staticmethod
    def _looks_like_progress_only_tool_reply(text: str) -> bool:
        """
        Heuristic: the model started a tool workflow but did not provide a final answer yet.
        We only use this when tool traces exist for the same turn.
        """
        s = (text or "").strip()
        if not s:
            return True
        if len(s) > 80:
            return False
        if s in {"~", "…", "...", "。。。", "...."}:
            return True
        progress_phrases = (
            "我去查",
            "我来查",
            "我帮你查",
            "我这就",
            "这就",
            "稍等",
            "等我",
            "正在查",
            "正在查询",
            "让我看看",
            "我看看",
            "查一下",
            "看一下",
            "帮你看看",
            "帮主人看看",
            "帮你查",
            "帮主人查",
        )
        if any(p in s for p in progress_phrases) and not re.search(r"\\d", s):
            return True
        return False

    @staticmethod
    def _user_prefers_raw_tool_output(text: str) -> bool:
        """
        Heuristic: the user explicitly requests raw/structured tool output (e.g., JSON).

        We use this to avoid "humanizing" / rewriting responses that must preserve a strict format.
        """
        s = (text or "").strip()
        if not s:
            return False

        lowered = s.lower()
        compact = re.sub(r"\\s+", "", lowered)

        # Strong negative overrides: user explicitly does NOT want JSON/structured/raw output.
        negative_tokens = (
            "不要json",
            "不用json",
            "别用json",
            "不需要json",
            "无需json",
            "不要raw",
            "不用raw",
            "别用raw",
            "不要原样",
            "不用原样",
            "别原样",
            "不要原始",
            "不用原始",
            "不要结构化",
            "不用结构化",
            "别结构化",
            "不需要结构化",
        )
        if any(tok in compact for tok in negative_tokens):
            return False

        # Avoid false positives: asking about JSON itself (definition/meaning).
        if "json" in compact and re.search(
            r"(json.*(是什么|什么意思|解释|介绍)|((是什么|什么意思|解释|介绍).*json))",
            lowered,
        ):
            return False

        # Positive: explicit JSON formatting directives.
        if "json" in compact:
            json_directives = (
                "格式",
                "返回",
                "输出",
                "给我",
                "只要",
                "仅",
                "原样",
                "raw",
                "asjson",
                "injson",
                "structured",
                "结构化",
            )
            if any(tok in compact for tok in json_directives):
                return True

        raw_markers = ("原样", "原始", "raw", "不加工", "未经处理", "原文")
        directive_markers = (
            "输出",
            "返回",
            "给我",
            "提供",
            "按",
            "按照",
            "以",
            "用",
            "格式",
            "return",
            "output",
        )
        if any(tok in compact for tok in raw_markers) and any(
            tok in compact for tok in directive_markers
        ):
            return True

        if "结构化" in compact and any(tok in compact for tok in directive_markers):
            return True

        return False

    @staticmethod
    def _looks_like_tool_echo_reply(text: str, tool_recorder: Optional[ToolTraceRecorder]) -> bool:
        """
        Heuristic: the model likely echoed tool output instead of producing a user-facing answer.

        We only use this when tool traces exist for the same turn.
        """
        if tool_recorder is None:
            return False
        raw = (text or "").strip()
        if not raw:
            return False

        lowered = raw.lower()
        if lowered.startswith("tool_result") or "[tool_result" in lowered:
            return True

        # Avoid over-triggering on short factual answers (e.g., time/date).
        if len(raw) < 120:
            # But if it looks like a raw JSON blob, it's almost certainly a tool echo.
            raw_stripped = raw.lstrip()
            if raw_stripped and raw_stripped[0] in "{[" and raw_stripped[-1] in "}]":
                fragment = _extract_leading_json_fragment(raw_stripped)
                if fragment and fragment.strip() == raw_stripped:
                    return True
            # Short but structured key/value blocks are usually tool output echoes.
            # Example: "city: xxx\\nweather: ..." (no TOOL_RESULT header).
            lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
            if len(lines) >= 3:
                kv_lines = 0
                for ln in lines:
                    if re.match(r"^[A-Za-z_][A-Za-z0-9_]{1,32}\s*:\s*\S", ln):
                        kv_lines += 1
                if kv_lines >= 2:
                    return True

            # If it doesn't look structured, treat it as a normal short answer.
            structured_hint = ("\n" in raw) or (":" in raw) or (raw_stripped[:1] in "{[")
            if not structured_hint:
                return False

        try:
            traces = tool_recorder.snapshot()
        except Exception:
            return False
        if not traces:
            return False

        def _norm(value: str) -> str:
            s = (value or "").strip()
            if not s:
                return ""
            s = s.replace("\r\n", "\n").replace("\r", "\n")
            s = re.sub(r"[ \t]+", " ", s)
            s = re.sub(r"\n{3,}", "\n\n", s)
            return s.strip()

        reply_norm = _norm(raw)
        reply_probe = reply_norm[:2000]

        for trace in traces[-5:]:
            candidate = (getattr(trace, "output", "") or getattr(trace, "error", "") or "").strip()
            cand_norm = _norm(candidate)
            if not cand_norm:
                continue

            if reply_norm == cand_norm:
                return True
            if len(cand_norm) >= 200 and cand_norm in reply_norm:
                return True
            if len(reply_norm) >= 200 and reply_norm in cand_norm:
                return True

            cand_probe = cand_norm[:2000]
            try:
                ratio = SequenceMatcher(None, reply_probe, cand_probe).ratio()
            except Exception:
                ratio = 0.0
            if ratio >= 0.92:
                return True

        return False

    def _rewrite_final_reply_from_tool_trace(
        self,
        bundle: "AgentConversationBundle",
        *,
        tool_recorder: Optional[ToolTraceRecorder],
        source: str,
    ) -> Optional[str]:
        """
        If the agent produced no final answer, ask the LLM to craft a role-played reply from tool
        results.
        """
        tool_trace = self._format_tool_trace_for_rewrite(tool_recorder)
        if not tool_trace:
            return None
        llm = getattr(self, "_tool_rewrite_llm", None) or getattr(self, "llm", None)
        if llm is None or not hasattr(self, "_llm_executor"):
            return None

        try:
            timeout_s = float(getattr(settings.agent, "tool_rewrite_timeout_s", 8.0))
            timeout_s = max(2.0, timeout_s)
        except Exception:
            timeout_s = 8.0

        system_prompt = str(getattr(self, "_system_prompt", "") or "")
        if not system_prompt:
            try:
                system_prompt = (
                    CharacterConfigLoader.generate_system_prompt()
                    or self.character.get_system_prompt()
                )
            except Exception:
                system_prompt = self.character.get_system_prompt()

        system_prompt += (
            "\n\n## 工具结果二次整理（输出给用户）\n"
            "- 你已经拿到工具结果；现在请直接给出最终答复。\n"
            "- 不要输出工具调用过程/JSON/日志；不要把工具结果原样粘贴。\n"
            "- 用角色语气说人话：先给结论，再给 3~5 个要点；必要时再追问缺失信息。\n"
        )
        try:
            state_context = (self._build_context_with_state(use_compression=False) or "").strip()
        except Exception:
            state_context = ""
        if state_context:
            system_prompt += f"\n\n{state_context}\n"

        user_question = (
            getattr(bundle, "original_message", "")
            or getattr(bundle, "processed_message", "")
            or ""
        ).strip()
        if not user_question:
            user_question = "（用户问题缺失）"

        prompt_text = (
            f"用户问题：{user_question}\n\n"
            f"工具结果（已截断，供参考）：\n{tool_trace}\n\n"
            "请输出面向用户的最终回答："
        )

        try:
            from langchain_core.messages import HumanMessage, SystemMessage
        except Exception:
            return None

        def _task() -> Any:
            return llm.invoke(
                [SystemMessage(content=system_prompt), HumanMessage(content=prompt_text)]
            )

        future = self._llm_executor.submit(_task)
        try:
            response = future.result(timeout=timeout_s)
        except FuturesTimeoutError:
            logger.warning("工具兜底重写超时(source=%s, timeout=%.1fs)", source, timeout_s)
            return None
        except Exception as exc:
            logger.debug("工具兜底重写失败(source=%s): %s", source, exc)
            return None
        finally:
            if not future.done():
                future.cancel()

        content = getattr(response, "content", response)
        text = self._filter_tool_info(content)
        text = (text or "").strip()
        if not text or text == _DEFAULT_EMPTY_REPLY:
            return None
        return text

    async def _arewrite_final_reply_from_tool_trace(
        self,
        bundle: "AgentConversationBundle",
        *,
        tool_recorder: Optional[ToolTraceRecorder],
        source: str,
    ) -> Optional[str]:
        tool_trace = self._format_tool_trace_for_rewrite(tool_recorder)
        if not tool_trace:
            return None
        llm = getattr(self, "_tool_rewrite_llm", None) or getattr(self, "llm", None)
        if llm is None or not callable(getattr(llm, "ainvoke", None)):
            return None

        try:
            timeout_s = float(getattr(settings.agent, "tool_rewrite_timeout_s", 8.0))
            timeout_s = max(2.0, timeout_s)
        except Exception:
            timeout_s = 8.0

        system_prompt = str(getattr(self, "_system_prompt", "") or "")
        if not system_prompt:
            try:
                system_prompt = (
                    CharacterConfigLoader.generate_system_prompt()
                    or self.character.get_system_prompt()
                )
            except Exception:
                system_prompt = self.character.get_system_prompt()

        system_prompt += (
            "\n\n## 工具结果二次整理（输出给用户）\n"
            "- 你已经拿到工具结果；现在请直接给出最终答复。\n"
            "- 不要输出工具调用过程/JSON/日志；不要把工具结果原样粘贴。\n"
            "- 用角色语气说人话：先给结论，再给 3~5 个要点；必要时再追问缺失信息。\n"
        )
        try:
            state_context = (self._build_context_with_state(use_compression=False) or "").strip()
        except Exception:
            state_context = ""
        if state_context:
            system_prompt += f"\n\n{state_context}\n"

        user_question = (
            getattr(bundle, "original_message", "")
            or getattr(bundle, "processed_message", "")
            or ""
        ).strip()
        if not user_question:
            user_question = "（用户问题缺失）"

        prompt_text = (
            f"用户问题：{user_question}\n\n"
            f"工具结果（已截断，供参考）：\n{tool_trace}\n\n"
            "请输出面向用户的最终回答："
        )

        try:
            from langchain_core.messages import HumanMessage, SystemMessage
        except Exception:
            return None

        async def _invoke() -> Any:
            return await llm.ainvoke(
                [SystemMessage(content=system_prompt), HumanMessage(content=prompt_text)]
            )

        try:
            response = await asyncio.wait_for(_invoke(), timeout=timeout_s)
        except asyncio.TimeoutError:
            logger.warning("工具兜底重写超时(source=%s, timeout=%.1fs)", source, timeout_s)
            return None
        except Exception as exc:
            logger.debug("工具兜底重写失败(source=%s): %s", source, exc)
            return None

        content = getattr(response, "content", response)
        text = self._filter_tool_info(content)
        text = (text or "").strip()
        if not text or text == _DEFAULT_EMPTY_REPLY:
            return None
        return text

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
            save_to_long_term=False,
            importance=None,
        )
        if save_to_long_term:
            self._enqueue_long_term_write(save_message, full_reply, importance=None)

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

                    should_extract = current_count % 3 == 0 or len(save_message) > 50
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
        sentences = re.split(r"[。！？\n]", normalized)
        sentences = [s.strip() for s in sentences if s.strip()][:3]  # 仅预取前3句
        if not sentences:
            return
        prefetch_text = "。".join(sentences) + "。"

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
        try:
            detected = self.emotion_engine.analyze_message(save_message)
            negative = bool(self.emotion_engine.is_negative_interaction(save_message, detected))
        except Exception:
            negative = False
        self.emotion_engine.update_user_profile(interaction_positive=not negative, persist=False)
        self.emotion_engine.decay_emotion(persist=False)

        def _persist_affect_states() -> None:
            try:
                self.emotion_engine.persist(force=False)
            except Exception:
                pass
            try:
                self.mood_system.persist(force=False)
            except Exception:
                pass
            try:
                self.style_learner.persist(force=False)
            except Exception:
                pass
            try:
                self.character_state.persist(force=False)
            except Exception:
                pass

        should_schedule = True
        try:
            with self._state_persist_lock:
                pending = self._pending_state_persist
                if pending is not None and not pending.done():
                    should_schedule = False
        except Exception:
            should_schedule = True

        if should_schedule:
            future = self._submit_background_task(_persist_affect_states, label="state-persist")
            if future:
                with self._state_persist_lock:
                    self._pending_state_persist = future

                def _clear(_future: Future) -> None:
                    with self._state_persist_lock:
                        if self._pending_state_persist is _future:
                            self._pending_state_persist = None

                future.add_done_callback(_clear)

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
        stage_timer = (
            RequestStageTimer(enabled=True, label="chat_stream")
            if logger.isEnabledFor(logging.DEBUG)
            else None
        )
        outcome = "ok"
        try:
            logger.info("收到用户消息(流式)")

            try:
                bundle = self._build_agent_bundle(
                    message,
                    image_analysis=image_analysis,
                    image_path=image_path,
                    compression="auto",
                    use_cache=True,
                    stage_timer=stage_timer,
                )
            except ValueError:
                outcome = "empty"
                logger.warning("收到空消息")
                yield "主人，您想说什么呢？喵~"
                return
            except Exception as prep_exc:
                outcome = "prep_error"
                logger.error("准备消息失败: %s", prep_exc)
                yield f"抱歉主人，准备消息时出错了：{str(prep_exc)} 喵~"
                return

            if stage_timer:
                stage_timer.mark("build_bundle")

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
                    if stage_timer:
                        stage_timer.mark("invoke_llm")
                    reply = self._extract_reply_from_response(response)
                    if not reply.strip() or reply.strip() == _DEFAULT_EMPTY_REPLY:
                        rescued = self._rescue_empty_reply(
                            bundle, raw_reply=reply, source="no_stream"
                        )
                        if rescued:
                            reply = rescued
                    if not reply.strip():
                        reply = _DEFAULT_EMPTY_REPLY

                    if cancel_event and cancel_event.is_set():
                        logger.info("非流式对话已取消（停止输出与保存）")
                        return

                    self._post_reply_actions(
                        bundle.save_message, reply, save_to_long_term, stream=False
                    )
                    if stage_timer:
                        stage_timer.mark("post_reply")
                    yield reply
                    logger.info("非流式回复完成（streaming disabled）")
                except AgentTimeoutError as timeout_exc:
                    outcome = "timeout"
                    logger.error("非流式对话超时: %s", timeout_exc)
                    yield "抱歉主人，模型那边暂时没有回应，我们稍后再聊好么？喵~"
                except Exception as exc:
                    outcome = "error"
                    logger.error("非流式对话失败: %s", exc)
                    yield f"抱歉主人，我遇到了一些问题：{str(exc)} 喵~"
                return

            reply_parts: list[str] = []
            try:
                stream_iter = self._stream_llm_response(
                    bundle.messages,
                    cancel_event=cancel_event,
                    tool_recorder=getattr(bundle, "tool_recorder", None),
                )
                canceled = False
                for chunk in stream_iter:
                    if cancel_event and cancel_event.is_set():
                        canceled = True
                        break
                    reply_parts.append(chunk)
                    yield chunk
                if canceled:
                    # Drain the iterator to ensure internal cleanup (closing streams, stopping
                    # threads).
                    try:
                        for _ in stream_iter:
                            pass
                    except Exception:
                        pass
                    logger.info("流式对话已取消（停止输出与保存）")
                    return
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
                    if self._stream_failure_count >= int(
                        getattr(self, "_stream_disable_after_failures", 2)
                    ):
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
                error_msg = (
                    str(stream_exc)
                    or repr(stream_exc)
                    or f"{type(stream_exc).__name__}: LLM调用失败"
                )

                def _is_connection_error(exc: BaseException) -> bool:
                    chain: list[BaseException] = []
                    current: BaseException | None = exc
                    for _ in range(8):
                        if current is None:
                            break
                        chain.append(current)
                        current = current.__cause__ or current.__context__

                    for item in chain:
                        name = type(item).__name__
                        if name in {
                            "APIConnectionError",
                            "APITimeoutError",
                            "ConnectError",
                            "ConnectTimeout",
                            "ReadTimeout",
                            "ReadError",
                            "RemoteProtocolError",
                            "ProtocolError",
                        }:
                            return True
                        if isinstance(item, ConnectionError):
                            return True
                        msg = (str(item) or "").lower()
                        if "connection error" in msg:
                            return True
                        if "unexpected_eof_while_reading" in msg or "unexpected eof" in msg:
                            return True
                    return False

                if _is_connection_error(stream_exc):
                    if cancel_event and cancel_event.is_set():
                        logger.info("流式对话已取消（忽略连接异常）: %s", error_msg)
                        return

                    if reply_parts:
                        logger.warning(
                            "LLM 流式输出中断（已输出部分内容）: %s",
                            error_msg,
                        )
                        self._stream_failure_count = 0
                    else:
                        logger.error("LLM 流式调用失败（连接异常）: %s", error_msg)
                        self._stream_failure_count = (
                            int(getattr(self, "_stream_failure_count", 0)) + 1
                        )
                        if self._stream_failure_count >= int(
                            getattr(self, "_stream_disable_after_failures", 2)
                        ):
                            if getattr(self, "enable_streaming", False):
                                logger.warning(
                                    "检测到多次流式失败（%s 次），将暂时禁用 streaming 以提升可用性",
                                    self._stream_failure_count,
                                )
                            try:
                                cooldown_s = float(
                                    getattr(self, "_stream_disable_cooldown_s", 60.0)
                                )
                            except Exception:
                                cooldown_s = 60.0
                            self._streaming_disabled_until = (
                                time.monotonic()
                                if cooldown_s <= 0
                                else time.monotonic() + cooldown_s
                            )
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
                            logger.warning(
                                "流式失败后的非流式兜底也失败: %s",
                                failover_exc,
                            )
                            fallback = (
                                "抱歉主人，网络连接似乎不太稳定，我暂时无法联系模型服务。"
                                "请检查网络/代理或稍后再试~"
                            )
                            reply_parts.append(fallback)
                            yield fallback
                else:
                    logger.error(f"LLM调用失败: {error_msg}")
                    raise

            if cancel_event and cancel_event.is_set():
                logger.info("流式对话已取消（忽略后处理）")
                return

            raw_reply = "".join(reply_parts)
            full_reply = self._filter_tool_info(raw_reply)
            if not full_reply or not _MEANINGFUL_CHAR_RE.search(full_reply):
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

            tool_recorder = getattr(bundle, "tool_recorder", None)
            if tool_recorder is not None:
                user_message = (
                    bundle.original_message or bundle.processed_message or bundle.save_message
                ) or ""
                prefers_raw = (
                    self._user_prefers_raw_tool_output(user_message) if user_message else False
                )
            else:
                user_message = ""
                prefers_raw = False
            if tool_recorder is not None and (
                self._looks_like_progress_only_tool_reply(full_reply)
                or (not prefers_raw and self._looks_like_tool_echo_reply(full_reply, tool_recorder))
            ):
                rewritten = self._format_tool_trace_fallback(
                    tool_recorder, user_message=user_message
                )
                if not rewritten:
                    rewritten = self._rewrite_final_reply_from_tool_trace(
                        bundle,
                        tool_recorder=tool_recorder,
                        source="stream-final",
                    )
                if not rewritten:
                    rewritten = self._maybe_rescue_implicit_tool_intent(
                        bundle, tool_recorder=tool_recorder
                    )
                if rewritten:
                    addition = f"\n\n{rewritten}" if full_reply.strip() else rewritten
                    reply_parts.append(addition)
                    full_reply = (f"{full_reply.rstrip()}{addition}").strip()
                    yield addition

            self._post_reply_actions(
                bundle.save_message, full_reply, save_to_long_term, stream=True
            )
            if stage_timer:
                stage_timer.mark("post_reply")
            logger.info("流式回复完成")

        except Exception as e:
            outcome = "error"
            # v3.3.4: 改进错误信息处理
            from src.utils.exceptions import handle_exception

            error_msg = str(e) or repr(e) or f"{type(e).__name__}: 流式对话处理失败"
            handle_exception(e, logger, "流式对话处理失败")
            if cancel_event and cancel_event.is_set():
                logger.info("流式对话已取消（忽略异常）: %s", error_msg)
                return
            yield f"抱歉主人，我遇到了一些问题：{error_msg} 喵~"
        finally:
            if stage_timer:
                stage_timer.emit_debug(outcome=outcome)

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
        stage_timer = (
            RequestStageTimer(enabled=True, label="chat_stream_async")
            if logger.isEnabledFor(logging.DEBUG)
            else None
        )
        outcome = "ok"
        try:
            logger.info("收到用户消息(异步流式)")

            try:
                bundle = await self._build_agent_bundle_async(
                    message,
                    image_analysis=image_analysis,
                    image_path=image_path,
                    compression="auto",
                    use_cache=True,
                    stage_timer=stage_timer,
                )
            except ValueError:
                outcome = "empty"
                logger.warning("收到空消息")
                yield "主人，您想说什么呢？喵~"
                return
            except Exception as prep_exc:
                outcome = "prep_error"
                logger.error("准备消息失败: %s", prep_exc)
                yield f"抱歉主人，准备消息时出错了：{str(prep_exc)} 喵~"
                return

            if stage_timer:
                stage_timer.mark("build_bundle")

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
                    response = await self._ainvoke_with_failover(
                        bundle,
                        timeout_s=getattr(self, "_stream_failover_timeout_s", None),
                    )
                    if stage_timer:
                        stage_timer.mark("invoke_llm")
                    reply = self._extract_reply_from_response(response)
                    if not reply.strip() or reply.strip() == _DEFAULT_EMPTY_REPLY:
                        rescued = await self._arescue_empty_reply(
                            bundle, raw_reply=reply, source="no_stream_async"
                        )
                        if rescued:
                            reply = rescued
                    if not reply.strip():
                        reply = _DEFAULT_EMPTY_REPLY

                    if cancel_event and cancel_event.is_set():
                        logger.info("非流式对话已取消（停止输出与保存）")
                        return

                    self._post_reply_actions(
                        bundle.save_message, reply, save_to_long_term, stream=False
                    )
                    if stage_timer:
                        stage_timer.mark("post_reply")
                    yield reply
                    logger.info("非流式回复完成（streaming disabled, async）")
                except AgentTimeoutError as timeout_exc:
                    outcome = "timeout"
                    logger.error("非流式对话超时: %s", timeout_exc)
                    yield "抱歉主人，模型那边暂时没有回应，我们稍后再聊好么？喵~"
                except Exception as exc:
                    outcome = "error"
                    logger.error("非流式对话失败: %s", exc)
                    yield f"抱歉主人，我遇到了一些问题：{str(exc)} 喵~"
                return

            reply_parts: list[str] = []
            try:
                stream_iter = self._astream_llm_response(
                    bundle.messages,
                    cancel_event=cancel_event,
                    tool_recorder=getattr(bundle, "tool_recorder", None),
                )
                canceled = False
                async for chunk in stream_iter:
                    if cancel_event and cancel_event.is_set():
                        canceled = True
                        break
                    reply_parts.append(chunk)
                    yield chunk
                if canceled:
                    # Drain the iterator to ensure internal cleanup (closing streams, avoiding
                    # dangling tasks).
                    try:
                        async for _ in stream_iter:
                            pass
                    except Exception:
                        pass
                    logger.info("异步流式对话已取消（停止输出与保存）")
                    return
                if reply_parts:
                    self._stream_failure_count = 0
            except AgentTimeoutError as stream_timeout:
                # v3.3.4: 改进错误信息处理
                error_msg = str(stream_timeout) or repr(stream_timeout) or "异步流式输出超时"
                if cancel_event and cancel_event.is_set():
                    logger.info("异步流式对话已取消（忽略超时）: %s", error_msg)
                    return
                if reply_parts:
                    logger.warning("LLM 异步流式输出中断（已输出部分内容）: %s", error_msg)
                    self._stream_failure_count = 0
                else:
                    logger.error("LLM 异步流式输出超时: %s", error_msg)
                    self._stream_failure_count = int(getattr(self, "_stream_failure_count", 0)) + 1
                    if self._stream_failure_count >= int(
                        getattr(self, "_stream_disable_after_failures", 2)
                    ):
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
                        response = await self._ainvoke_with_failover(
                            bundle,
                            timeout_s=getattr(self, "_stream_failover_timeout_s", None),
                        )
                        reply = self._extract_reply_from_response(response)
                        if not reply.strip() or reply.strip() == _DEFAULT_EMPTY_REPLY:
                            rescued = await self._arescue_empty_reply(
                                bundle, raw_reply=reply, source="astream_failover"
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
            except Exception as stream_error:
                # v3.3.4: 改进错误信息处理
                from src.utils.exceptions import handle_exception

                error_msg = (
                    str(stream_error)
                    or repr(stream_error)
                    or f"{type(stream_error).__name__}: 异步流式输出错误"
                )
                handle_exception(stream_error, logger, "异步流式输出错误")

            if cancel_event and cancel_event.is_set():
                logger.info("异步流式对话已取消（忽略后处理）")
                return

            raw_reply = "".join(reply_parts)
            full_reply = self._filter_tool_info(raw_reply)
            if not full_reply or not _MEANINGFUL_CHAR_RE.search(full_reply):
                rescued = await self._arescue_empty_reply(
                    bundle, raw_reply=raw_reply, source="astream"
                )
                if rescued:
                    full_reply = rescued
                    yield rescued
                elif raw_reply.strip():
                    full_reply = raw_reply.strip()
                else:
                    full_reply = _DEFAULT_EMPTY_REPLY
                    yield _DEFAULT_EMPTY_REPLY

            tool_recorder = getattr(bundle, "tool_recorder", None)
            if tool_recorder is not None:
                user_message = (
                    bundle.original_message or bundle.processed_message or bundle.save_message
                ) or ""
                prefers_raw = (
                    self._user_prefers_raw_tool_output(user_message) if user_message else False
                )
            else:
                user_message = ""
                prefers_raw = False
            if tool_recorder is not None and (
                self._looks_like_progress_only_tool_reply(full_reply)
                or (not prefers_raw and self._looks_like_tool_echo_reply(full_reply, tool_recorder))
            ):
                rewritten = self._format_tool_trace_fallback(
                    tool_recorder, user_message=user_message
                )
                if not rewritten:
                    rewritten = await self._arewrite_final_reply_from_tool_trace(
                        bundle,
                        tool_recorder=tool_recorder,
                        source="astream-final",
                    )
                if not rewritten:
                    rewritten = self._maybe_rescue_implicit_tool_intent(
                        bundle, tool_recorder=tool_recorder
                    )
                if rewritten:
                    addition = f"\n\n{rewritten}" if full_reply.strip() else rewritten
                    reply_parts.append(addition)
                    full_reply = (f"{full_reply.rstrip()}{addition}").strip()
                    yield addition

            self._post_reply_actions(
                bundle.save_message, full_reply, save_to_long_term, stream=True
            )
            if stage_timer:
                stage_timer.mark("post_reply")

            logger.info("异步流式回复完成")

        except AgentTimeoutError as timeout_exc:
            outcome = "timeout"
            # v3.3.4: 改进错误信息处理
            error_msg = str(timeout_exc) or repr(timeout_exc) or "异步流式对话超时"
            if cancel_event and cancel_event.is_set():
                outcome = "canceled"
                logger.info("异步流式对话已取消（忽略超时）: %s", error_msg)
                return
            logger.error(f"异步流式对话超时: {error_msg}")
            yield "抱歉主人，模型暂时没有新输出，我们稍后再继续聊好嘛？喵~"
        except Exception as e:
            outcome = "error"
            # v3.3.4: 改进错误信息处理，避免空错误信息
            error_msg = str(e) or repr(e) or f"{type(e).__name__}: 异步流式对话处理失败"
            logger.error(f"异步流式对话处理失败: {error_msg}")
            if cancel_event and cancel_event.is_set():
                outcome = "canceled"
                logger.info("异步流式对话已取消（忽略异常）: %s", error_msg)
                return
            yield f"抱歉主人，我遇到了一些问题：{error_msg} 喵~"
        finally:
            if stage_timer:
                stage_timer.emit_debug(outcome=outcome)

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
                core_data = self.core_memory.vectorstore.get(
                    include=["documents", "metadatas", "ids"]
                )
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
            if (
                isinstance(core_items, list)
                and getattr(self, "core_memory", None)
                and hasattr(self.core_memory, "import_records")
            ):
                try:
                    stats["core_memory"] = int(
                        self.core_memory.import_records(core_items, overwrite=overwrite)
                    )
                except Exception as e:
                    logger.warning("导入核心记忆失败: %s", e)

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
                self.__class__._PERSONAL_INFO_KEYWORDS = frozenset(
                    [
                        "我叫",
                        "我的名字",
                        "我是",
                        "我今年",
                        "我的生日",
                        "我住在",
                        "我来自",
                        "我的职业",
                        "我的工作",
                        "我的爱好",
                        "我喜欢",
                        "我讨厌",
                        "我的家人",
                        "我的朋友",
                        "我的宠物",
                    ]
                )
                self.__class__._PREFERENCES_KEYWORDS = frozenset(
                    [
                        "喜欢",
                        "不喜欢",
                        "讨厌",
                        "最爱",
                        "偏好",
                        "习惯",
                        "经常",
                        "总是",
                        "从不",
                        "一般",
                        "通常",
                    ]
                )
                self.__class__._IMPORTANT_EVENTS_KEYWORDS = frozenset(
                    [
                        "记住",
                        "重要",
                        "一定要",
                        "千万",
                        "务必",
                        "别忘了",
                        "提醒我",
                        "帮我记",
                        "不要忘记",
                    ]
                )
                self.__class__._IMPORTANT_WORDS = frozenset(
                    ["重要", "记住", "一定", "务必", "千万"]
                )

            # 使用any()和生成器表达式优化匹配
            if any(kw in user_message for kw in self.__class__._PERSONAL_INFO_KEYWORDS):
                self.core_memory.add_core_memory(
                    content=user_message, category="personal_info", importance=0.9
                )
                logger.info("提取个人信息到核心记忆")
                return

            if any(kw in user_message for kw in self.__class__._PREFERENCES_KEYWORDS):
                self.core_memory.add_core_memory(
                    content=user_message, category="preferences", importance=0.8
                )
                logger.info("提取偏好信息到核心记忆")
                return

            if any(kw in user_message for kw in self.__class__._IMPORTANT_EVENTS_KEYWORDS):
                self.core_memory.add_core_memory(
                    content=user_message, category="important_events", importance=0.95
                )
                logger.info("提取重要事件到核心记忆")
                return

            # 长消息（可能包含重要信息）
            if len(user_message) > 100 and any(
                word in user_message for word in self.__class__._IMPORTANT_WORDS
            ):
                self.core_memory.add_core_memory(
                    content=user_message, category="general", importance=0.7
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
        if hasattr(self, "_pending_tts_prefetch") and self._pending_tts_prefetch:
            with self._tts_prefetch_lock:
                if self._pending_tts_prefetch and not self._pending_tts_prefetch.done():
                    self._pending_tts_prefetch.cancel()
                self._pending_tts_prefetch = None

        # 1.1 取消待处理的状态持久化任务（不重要，可忽略）
        if hasattr(self, "_pending_state_persist") and self._pending_state_persist:
            with self._state_persist_lock:
                if self._pending_state_persist and not self._pending_state_persist.done():
                    self._pending_state_persist.cancel()
                self._pending_state_persist = None

        # 1.15 尽量落盘长期记忆写入（避免重启丢失）
        if hasattr(self, "_long_term_write_lock") and hasattr(self, "_long_term_write_buffer"):
            pending = getattr(self, "_pending_long_term_write", None)
            # Prevent the done-callback from rescheduling new slices during close().
            try:
                with self._long_term_write_lock:
                    self._pending_long_term_write = None
            except Exception:
                pass

            # Best-effort wait for the in-flight drain slice to finish quickly.
            try:
                if pending is not None and hasattr(pending, "done") and not pending.done():
                    try:
                        pending.result(timeout=2.0)
                    except Exception:
                        try:
                            pending.cancel()
                        except Exception:
                            pass
            except Exception:
                pass

            # Drain remaining buffered interactions synchronously and flush the batch buffer.
            try:
                memory = getattr(self, "memory", None)
                items: list[tuple[str, str, Optional[float]]] = []
                with self._long_term_write_lock:
                    try:
                        while self._long_term_write_buffer:
                            items.append(self._long_term_write_buffer.popleft())
                    except Exception:
                        try:
                            items = list(self._long_term_write_buffer)
                            self._long_term_write_buffer.clear()
                        except Exception:
                            items = []

                if memory is not None and items:
                    add_long_term = getattr(memory, "add_interaction_long_term", None)
                    for msg, reply, imp in items:
                        try:
                            if callable(add_long_term):
                                add_long_term(
                                    user_message=msg,
                                    assistant_message=reply,
                                    importance=imp,
                                )
                            else:
                                memory.add_interaction(
                                    user_message=msg,
                                    assistant_message=reply,
                                    save_to_long_term=True,
                                    importance=imp,
                                )
                        except Exception:
                            pass

                if memory is not None:
                    try:
                        long_term = getattr(memory, "long_term", None)
                        flush_batch = getattr(long_term, "flush_batch", None)
                        if callable(flush_batch):
                            flush_batch()
                    except Exception:
                        pass
            except Exception:
                pass

        # 1.2 关闭复用的 AsyncLoopThread（用于同步路径跑异步逻辑）
        try:
            loop_thread = getattr(self, "_async_loop_thread", None)
            if loop_thread is not None:
                loop_thread.close(timeout=3.0)
        except Exception as e:
            logger.debug("关闭 AsyncLoopThread 失败(可忽略): %s", e)

        # 2. 关闭后台执行器
        if hasattr(self, "_background_executor") and self._background_executor:
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
        if hasattr(self, "_llm_executor") and self._llm_executor:
            try:
                try:
                    self._llm_executor.shutdown(wait=False, cancel_futures=True)
                except TypeError:
                    self._llm_executor.shutdown(wait=False)
            except Exception as e:
                logger.warning(f"关闭LLM执行器时出错: {e}")
            finally:
                self._llm_executor = None
        if hasattr(self, "_stream_executor") and self._stream_executor:
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

        # 4. 关闭记忆检索器
        if hasattr(self, "memory_retriever") and self.memory_retriever:
            try:
                if hasattr(self.memory_retriever, "close"):
                    self.memory_retriever.close()
            except Exception as e:
                logger.warning(f"关闭记忆检索器时出错: {e}")

        # 5. 刷新批量缓冲区和清理缓存
        if hasattr(self, "memory") and self.memory:
            try:
                self.memory.cleanup_cache()
            except Exception as e:
                logger.warning(f"清理记忆缓存时出错: {e}")

        # 6.0 刷新情绪/情感系统的持久化数据（可忽略失败）
        try:
            if hasattr(self, "emotion_engine") and self.emotion_engine:
                flush_fn = getattr(self.emotion_engine, "flush", None)
                if callable(flush_fn):
                    flush_fn()
        except Exception as e:
            logger.debug("刷新情绪状态失败(可忽略): %s", e)

        try:
            if hasattr(self, "mood_system") and self.mood_system:
                flush_fn = getattr(self.mood_system, "flush", None)
                if callable(flush_fn):
                    flush_fn()
        except Exception as e:
            logger.debug("刷新情感状态失败(可忽略): %s", e)

        # 6. 刷新对话风格学习器持久化数据（可忽略失败）
        try:
            if hasattr(self, "style_learner") and self.style_learner:
                flush_fn = getattr(self.style_learner, "flush", None)
                if callable(flush_fn):
                    flush_fn()
        except Exception as e:
            logger.debug("刷新对话风格配置失败（可忽略）: %s", e)

        # 6.1 刷新角色状态持久化数据（可忽略失败）
        try:
            if hasattr(self, "character_state") and self.character_state:
                flush_fn = getattr(self.character_state, "flush", None)
                if callable(flush_fn):
                    flush_fn()
        except Exception as e:
            logger.debug("刷新角色状态失败（可忽略）: %s", e)

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

            return stats

        except Exception as e:
            logger.error(f"获取记忆统计失败: {e}")
            return {
                "error": str(e),
                "short_term_messages": 0,
                "long_term_memories": 0,
                "core_memories": 0,
            }

    def _execute_tool_calls_from_text(
        self,
        text: Any,
        *,
        tool_recorder: Optional[ToolTraceRecorder] = None,
    ) -> Optional[str]:
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
                if (
                    "poi" in key or "place" in key or "search" in key
                ) and "map_search" in available:
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

        recorder = tool_recorder
        results: list[str] = []
        for name, args in calls:
            if not name:
                continue
            resolved = _resolve_tool_name(name)
            started_at = time.perf_counter()
            if recorder is not None:
                try:
                    recorder.mark_start()
                except Exception:
                    recorder = None
            try:
                result = self.tool_registry.execute_tool(resolved, **(args or {}))
            except Exception as exc:  # pragma: no cover - defensive
                result = f"工具 {resolved} 执行失败: {exc}"
                if recorder is not None:
                    try:
                        recorder.record_end(
                            resolved,
                            args or {},
                            started_at=started_at,
                            error=str(exc) or repr(exc),
                        )
                    except Exception:
                        pass
            else:
                if recorder is not None:
                    try:
                        recorder.record_end(
                            resolved,
                            args or {},
                            started_at=started_at,
                            output=str(result),
                        )
                    except Exception:
                        pass
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
                        call_obj.get("arguments") or call_obj.get("args") or call_obj.get("params")
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

        if raw.startswith("[") and raw.endswith("]"):
            frag = _extract_leading_json_fragment(raw)
            if frag and frag == raw:
                try:
                    parsed = json.loads(frag)
                except Exception:
                    parsed = None
                if parsed is not None and _looks_like_route_tag_list(parsed):
                    return raw

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
            elif (
                isinstance(parsed, list)
                and parsed
                and all(isinstance(item, str) for item in parsed)
            ):
                # list[str] 作为“内部标签/模块名”通常为 snake_case；若后面紧跟多段 JSON/孤立 '}'，
                # 基本可以判定为工具/结构化输出残留。
                normalized = [item.strip() for item in parsed]
                if (
                    normalized
                    and all(_IDENT_TOKEN_RE.fullmatch(item) for item in normalized)
                    and any("_" in item for item in normalized)
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
                    or '"tools"' in lowered_raw
                    or '"tool"' in lowered_raw
                    or (
                        '"function"' in lowered_raw
                        and '"arguments"' in lowered_raw
                        and '"name"' in lowered_raw
                    )
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
            or '"tools"' in lower_cleaned
            or (
                '"function"' in lower_cleaned
                and '"arguments"' in lower_cleaned
                and '"name"' in lower_cleaned
            )
        )
        if maybe_tool_trace and ("{" in cleaned or "[" in cleaned):
            cleaned = _strip_tool_json_blocks(cleaned, max_blocks=3)
            lower_cleaned = cleaned.lower()
            maybe_tool_trace = (
                "toolselectionresponse" in lower_cleaned
                or "tool_calls" in lower_cleaned
                or '"tools"' in lower_cleaned
                or (
                    '"function"' in lower_cleaned
                    and '"arguments"' in lower_cleaned
                    and '"name"' in lower_cleaned
                )
            )

        # 处理“路由标签 list[str]”残留（通常不包含 "tool" 字样）
        if "[" in cleaned and "_" in cleaned:
            cleaned = _strip_route_tag_lists(cleaned, max_blocks=5)
            lower_cleaned = cleaned.lower()
            if '"tools"' in lower_cleaned or "tool_calls" in lower_cleaned:
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
                '"tools"' in compact
                or '"tool_calls"' in compact
                or '"type":"function"' in compact
                or ('"function"' in compact and '"arguments"' in compact and '"name"' in compact)
            ):
                continue
            if stripped.startswith("{") or stripped.startswith("["):
                compact = lower.replace(" ", "")
                if (
                    "tool_calls" in compact
                    or '"tools"' in compact
                    or '"tool"' in compact
                    or '"type":"function"' in compact
                    or (
                        '"function"' in compact and '"arguments"' in compact and '"name"' in compact
                    )
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
