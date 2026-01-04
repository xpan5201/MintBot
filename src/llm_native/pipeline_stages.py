from __future__ import annotations

from dataclasses import dataclass, field
import collections
import json
import re
import time
from threading import Lock
from typing import Iterable, Mapping, Sequence

from src.utils.logger import logger

from .backend import ChatBackend, ChatRequest
from .events import ToolCallState
from .messages import ContentPart, Message, TextPart
from .pipeline import PipelineAbort, PipelineRequest, PipelineStage


@dataclass(slots=True)
class PermissionScopedToolsStage(PipelineStage):
    """
    Permission scoped tools stage (native pipeline).

    Mirrors legacy `PermissionScopedToolMiddleware` behavior:
    - Resolve runtime tool profile (tool_profile)
    - Fallback to default profile
    - Filter tools by allowlist
    """

    profile_map: Mapping[str, Iterable[str]] | None = None
    default_profile: str = "default"
    _normalized: dict[str, set[str]] = field(init=False, default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        default = str(self.default_profile or "default").strip() or "default"
        self.default_profile = default
        normalized: dict[str, set[str]] = {}
        for profile, tools in (self.profile_map or {}).items():
            if not tools:
                continue
            allowed = {str(name).strip() for name in tools if str(name).strip()}
            if allowed:
                normalized[str(profile).strip() or default] = allowed
        self._normalized = normalized

    def pre_model(self, request: PipelineRequest) -> PipelineRequest:
        if not self._normalized:
            return request

        profile = self._resolve_profile(request)
        allowed = self._normalized.get(profile)
        if allowed is None and profile != self.default_profile:
            allowed = self._normalized.get(self.default_profile)

        if not allowed:
            return request

        before = list(request.tools)
        request.tools = [tool for tool in request.tools if tool.name in allowed]

        # Stable-first: if misconfigured allowlist yields an empty toolset, auto-downgrade.
        if before and not request.tools:
            logger.warning(
                "PermissionScopedToolsStage produced empty tool list; skip filtering (profile=%s)",
                profile,
            )
            request.tools = before
        return request

    def _resolve_profile(self, request: PipelineRequest) -> str:
        runtime = request.runtime or {}
        profile = runtime.get("tool_profile")
        profile = str(profile).strip() if profile else ""
        return profile or self.default_profile


_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "time": ("时间", "几点", "日期", "today", "date", "time", "now"),
    "weather": ("天气", "气温", "温度", "下雨", "降雨", "forecast", "weather"),
    "map": ("地图", "导航", "路线", "怎么走", "附近", "地址", "map", "route", "nearby"),
    "search": ("搜索", "查一下", "查找", "资料", "news", "search", "google", "bing"),
    "file": (
        "文件",
        "目录",
        "路径",
        "读取",
        "打开",
        "保存",
        "file",
        "path",
        "directory",
        "read",
        "write",
    ),
    "note": ("笔记", "备忘", "记录一下", "note", "memo"),
    "reminder": ("提醒", "闹钟", "定时", "remind", "alarm", "schedule"),
    "calc": ("计算", "算一下", "calculator", "calc", "math"),
}

_CATEGORY_TOOL_NAME_HINTS: dict[str, tuple[str, ...]] = {
    "time": ("time", "date", "clock"),
    "weather": ("weather", "forecast"),
    "map": ("map", "geo", "route", "nearby", "amap", "gaode"),
    "search": ("search", "tavily", "ddg", "duck", "bing"),
    "file": ("file", "read", "write", "list", "path", "dir"),
    "note": ("note", "memo"),
    "reminder": ("remind", "alarm", "schedule"),
    "calc": ("calc", "calculator", "math"),
}

_DEFAULT_FALLBACK_TOOL_NAMES: tuple[str, ...] = (
    "calculator",
    "read_file",
    "write_file",
    "list_files",
)

_MATH_EXPR_RE = re.compile(r"(?:^|\s)(\d+(?:\.\d+)?)\s*([+*/-])\s*(\d+(?:\.\d+)?)(?:\s|$)")


def _extract_text(content: str | list[ContentPart] | None) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for part in content:
        if isinstance(part, TextPart):
            parts.append(part.text)
            continue
        if isinstance(part, dict) and part.get("type") == "text":
            value = part.get("text")
            if value:
                parts.append(str(value))
    return "\n".join(p for p in parts if p)


@dataclass(slots=True)
class ToolHeuristicPrefilterStage(PipelineStage):
    """
    Heuristic prefilter for tools (no extra LLM call).

    Stable-first design:
    - Only apply filtering when we detect a clear tool intent
      (category hit or explicit tool-name mention).
    - Never produce an empty tool list (auto-downgrade to no filtering).
    """

    always_include: Sequence[str] = ()
    max_tools: int | None = None
    min_tools: int = 16

    def pre_model(self, request: PipelineRequest) -> PipelineRequest:
        tools = list(request.tools or [])
        if not tools or len(tools) < max(0, int(self.min_tools)):
            return request

        user_text = self._last_user_text(request)
        if not user_text:
            return request

        always_include_set = {str(n).strip() for n in self.always_include if str(n).strip()}
        candidate_names = [t.name for t in tools if t.name not in always_include_set]
        selected_names = self._heuristic_select_tool_names(user_text, candidate_names)
        if not selected_names:
            return request

        name_to_tool = {t.name: t for t in tools}
        new_tools = self._build_filtered_tools(
            tools=tools,
            name_to_tool=name_to_tool,
            selected_names=selected_names,
            always_include_set=always_include_set,
        )
        if not new_tools:
            logger.warning("ToolHeuristicPrefilterStage produced empty tool list; skip filtering")
            return request

        request.tools = new_tools
        return request

    def _last_user_text(self, request: PipelineRequest) -> str:
        for msg in reversed(request.messages or []):
            if getattr(msg, "role", "") != "user":
                continue
            return _extract_text(getattr(msg, "content", None)).strip()
        return ""

    def _score_categories(self, user_text: str) -> dict[str, int]:
        if not user_text:
            return {}
        text = user_text.lower()
        scores: dict[str, int] = {}
        for category, keywords in _CATEGORY_KEYWORDS.items():
            score = 0
            for kw in keywords:
                if kw and kw.lower() in text:
                    score += 1
            if score > 0:
                scores[category] = score

        try:
            if _MATH_EXPR_RE.search(user_text):
                scores["calc"] = scores.get("calc", 0) + 2
        except Exception:
            pass
        return scores

    def _heuristic_select_tool_names(self, user_text: str, tool_names: list[str]) -> list[str]:
        if not tool_names:
            return []

        scores = self._score_categories(user_text)
        lower_text = user_text.lower()

        explicit_mentions: list[str] = []
        for name in tool_names:
            lname = name.lower()
            if lname and lname in lower_text:
                explicit_mentions.append(name)

        # Stable-first: no clear intent => do not filter.
        if not scores and not explicit_mentions:
            return []

        selected: list[str] = []
        name_set = set(tool_names)

        for category, _ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True):
            hints = _CATEGORY_TOOL_NAME_HINTS.get(category, ())
            for name in tool_names:
                lname = name.lower()
                if name not in name_set:
                    continue
                if any(h in lname for h in hints):
                    selected.append(name)

        for name in explicit_mentions:
            if name not in selected:
                selected.append(name)

        for name in _DEFAULT_FALLBACK_TOOL_NAMES:
            if name in name_set and name not in selected:
                selected.append(name)

        max_keep = 12
        if self.max_tools is not None:
            max_keep = max(8, min(24, int(self.max_tools) * 3))
        return selected[:max_keep]

    @staticmethod
    def _build_filtered_tools(
        *,
        tools: list,
        name_to_tool: Mapping[str, object],
        selected_names: Sequence[str],
        always_include_set: set[str],
    ) -> list:
        new_tools: list = []
        seen: set[str] = set()

        for name in selected_names:
            tool = name_to_tool.get(name)
            if tool is None:
                continue
            if name in always_include_set:
                continue
            if name in seen:
                continue
            new_tools.append(tool)
            seen.add(name)

        for tool in tools:
            tool_name = str(getattr(tool, "name", "") or "").strip()
            if not tool_name or tool_name not in always_include_set:
                continue
            if tool_name in seen:
                continue
            new_tools.append(tool)
            seen.add(tool_name)

        return new_tools


DEFAULT_TOOL_SELECTOR_SYSTEM_PROMPT = (
    "Your goal is to select the most relevant tools for answering the user's query."
)


_TOOL_SELECTOR_CACHE: collections.OrderedDict[tuple[str, tuple[str, ...]], list[str]] = (
    collections.OrderedDict()
)
_TOOL_SELECTOR_CACHE_LOCK = Lock()

_TOOL_SELECTOR_DISABLED_UNTIL: dict[tuple[str, str], float] = {}
_TOOL_SELECTOR_DISABLED_UNTIL_LOCK = Lock()


def _extract_json_snippet(text: str) -> str | None:
    """Extract the first JSON object/array fragment from noisy text for lenient parsing."""
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
        if ch in "}]":
            if not stack:
                continue
            opener = stack.pop()
            if (opener == "{" and ch != "}") or (opener == "[" and ch != "]"):
                return None
            if not stack:
                return s[start : i + 1]

    return None


def _parse_tool_selection(text: str) -> list[str] | None:
    snippet = _extract_json_snippet(text) or (text.strip() if text else "")
    if not snippet:
        return None
    try:
        obj = json.loads(snippet)
    except Exception:
        return None

    tools: object | None
    if isinstance(obj, dict):
        tools = obj.get("tools")
    elif isinstance(obj, list):
        tools = obj
    else:
        return None

    if tools is None:
        return None
    if not isinstance(tools, list):
        return None

    selected: list[str] = []
    for item in tools:
        name = str(item).strip()
        if name and name not in selected:
            selected.append(name)
    return selected


def _backend_breaker_key(backend: object) -> tuple[str, str]:
    cfg = getattr(backend, "config", None)
    base_url = str(getattr(cfg, "base_url", "") or "").strip()
    model = str(getattr(cfg, "model", "") or "").strip()
    return base_url, model


def _cache_get(key: tuple[str, tuple[str, ...]]) -> list[str] | None:
    with _TOOL_SELECTOR_CACHE_LOCK:
        value = _TOOL_SELECTOR_CACHE.get(key)
        if value is None:
            return None
        try:
            _TOOL_SELECTOR_CACHE.move_to_end(key)
        except Exception:
            pass
        return list(value)


def _cache_set(key: tuple[str, tuple[str, ...]], value: list[str], *, max_size: int) -> None:
    if not key:
        return
    with _TOOL_SELECTOR_CACHE_LOCK:
        _TOOL_SELECTOR_CACHE[key] = list(value)
        try:
            _TOOL_SELECTOR_CACHE.move_to_end(key)
        except Exception:
            pass
        while len(_TOOL_SELECTOR_CACHE) > max(1, int(max_size)):
            try:
                _TOOL_SELECTOR_CACHE.popitem(last=False)
            except Exception:
                break


def _is_disabled(key: tuple[str, str]) -> bool:
    with _TOOL_SELECTOR_DISABLED_UNTIL_LOCK:
        until = float(_TOOL_SELECTOR_DISABLED_UNTIL.get(key, 0.0) or 0.0)
    if until <= 0.0:
        return False
    try:
        return time.monotonic() < until
    except Exception:
        return True


def _trip_circuit(key: tuple[str, str], cooldown_s: float) -> None:
    if float(cooldown_s) <= 0:
        return
    try:
        until = time.monotonic() + float(cooldown_s)
    except Exception:
        until = float("inf")
    with _TOOL_SELECTOR_DISABLED_UNTIL_LOCK:
        _TOOL_SELECTOR_DISABLED_UNTIL[key] = until


@dataclass(slots=True)
class ToolLlmSelectorStage(PipelineStage):
    """
    Optional LLM tool selector stage (native pipeline).

    Behavior (stable-first):
    - Fail-open: on any error/timeout/parse failure, keep the original tool list.
    - Circuit breaker: disable selector temporarily after failures.
    - Cache: reuse selection results for identical (user_text, tool_names) inputs.
    """

    backend: ChatBackend
    max_tools: int = 4
    min_tools: int = 16
    always_include: Sequence[str] = ()
    system_prompt: str = DEFAULT_TOOL_SELECTOR_SYSTEM_PROMPT
    disable_cooldown_s: float = 300.0
    cache_max: int = 128
    max_tokens: int = 256
    _breaker_key: tuple[str, str] = field(init=False, repr=False, default=("", ""))

    def __post_init__(self) -> None:
        self.max_tools = max(1, int(self.max_tools))
        self.min_tools = max(0, int(self.min_tools))
        self.disable_cooldown_s = max(0.0, float(self.disable_cooldown_s))
        self.cache_max = max(1, int(self.cache_max))
        self.max_tokens = max(32, int(self.max_tokens))
        self._breaker_key = _backend_breaker_key(self.backend)

    def pre_model(self, request: PipelineRequest) -> PipelineRequest:
        tools = list(request.tools or [])
        if not tools or len(tools) < self.min_tools:
            return request

        if not self._is_last_turn_user(request.messages):
            return request

        if _is_disabled(self._breaker_key):
            return request

        user_text = self._last_user_text(request)
        if not user_text:
            return request

        valid_tool_names = [t.name for t in tools if str(getattr(t, "name", "") or "").strip()]
        cache_key = (user_text.strip().lower()[:500], tuple(valid_tool_names))
        cached = _cache_get(cache_key)
        if cached is not None:
            filtered = self._apply_selection(tools, cached)
            if filtered:
                request.tools = filtered
            return request

        try:
            selected = self._select_tools(user_text, valid_tool_names)
        except Exception as exc:
            logger.warning("ToolLlmSelectorStage failed; skip selection: %s", exc)
            _trip_circuit(self._breaker_key, self.disable_cooldown_s)
            return request

        if selected is None:
            logger.warning("ToolLlmSelectorStage output missing tools field; skip selection")
            _trip_circuit(self._breaker_key, self.disable_cooldown_s)
            return request

        try:
            _cache_set(cache_key, selected, max_size=self.cache_max)
        except Exception:
            pass

        filtered = self._apply_selection(tools, selected)
        if tools and not filtered:
            logger.warning("ToolLlmSelectorStage produced empty tool list; skip filtering")
            _trip_circuit(self._breaker_key, self.disable_cooldown_s)
            return request

        if filtered:
            request.tools = filtered
        return request

    @staticmethod
    def _is_last_turn_user(messages: Sequence[Message]) -> bool:
        for msg in reversed(messages or []):
            role = str(getattr(msg, "role", "") or "")
            if role == "system":
                continue
            return role == "user"
        return False

    @staticmethod
    def _last_user_text(request: PipelineRequest) -> str:
        for msg in reversed(request.messages or []):
            if getattr(msg, "role", "") != "user":
                continue
            return _extract_text(getattr(msg, "content", None)).strip()
        return ""

    def _select_tools(self, user_text: str, tool_names: list[str]) -> list[str] | None:
        names = [str(n).strip() for n in tool_names if str(n).strip()]
        if not names:
            return None

        # Keep prompt compact: pass only tool names (no schemas).
        system = (
            f"{self.system_prompt}\n"
            f"Select at most {self.max_tools} tools.\n"
            'Return JSON: {"tools": ["tool_name", ...]}\n'
            "Only choose from the provided tool names.\n"
            f"Tool names: {json.dumps(names, ensure_ascii=False)}"
        )
        req = ChatRequest(
            messages=[
                Message(role="system", content=system),
                Message(role="user", content=user_text),
            ],
            tools=[],
            temperature=0.0,
            max_tokens=self.max_tokens,
        )
        resp = self.backend.complete(req)
        return _parse_tool_selection(str(getattr(resp, "output_text", "") or ""))

    def _apply_selection(self, tools: list, selection: Sequence[str]) -> list:
        valid = {str(getattr(t, "name", "") or "").strip() for t in tools}
        always_include_set = {str(n).strip() for n in self.always_include if str(n).strip()}

        selected_names: list[str] = []
        for name in selection or []:
            tool_name = str(name).strip()
            if not tool_name or tool_name not in valid:
                continue
            if tool_name in selected_names:
                continue
            if len(selected_names) >= self.max_tools:
                break
            selected_names.append(tool_name)

        selected_set = set(selected_names)
        new_tools = [t for t in tools if str(getattr(t, "name", "") or "").strip() in selected_set]
        for t in tools:
            tool_name = str(getattr(t, "name", "") or "").strip()
            if not tool_name or tool_name not in always_include_set:
                continue
            if tool_name in selected_set:
                continue
            new_tools.append(t)
        return new_tools


@dataclass(slots=True)
class ToolCallLimitStage(PipelineStage):
    """Limit total tool calls executed per run (stable-first)."""

    per_run_limit: int
    _used: int = field(init=False, default=0, repr=False)

    def __post_init__(self) -> None:
        if int(self.per_run_limit) <= 0:
            raise ValueError("per_run_limit must be > 0")
        self.per_run_limit = int(self.per_run_limit)

    def pre_tool_calls(self, tool_calls: list[ToolCallState]) -> list[ToolCallState]:
        remaining = self.per_run_limit - self._used
        if remaining <= 0:
            raise PipelineAbort(
                "tool call limit exceeded",
                exception_type="ToolCallLimitError",
                finish_reason="tool_call_limit",
            )

        if len(tool_calls) > remaining:
            raise PipelineAbort(
                f"tool call limit exceeded (limit={self.per_run_limit}, used={self._used})",
                exception_type="ToolCallLimitError",
                finish_reason="tool_call_limit",
            )

        self._used += len(tool_calls)
        return tool_calls


@dataclass(slots=True)
class ToolTraceStage(PipelineStage):
    """
    Tool trace stage (native pipeline).

    Mirrors `ToolTraceMiddleware` behavior needed for stability:
    - Truncate verbose tool outputs before appending to the conversation.

    Note: tool call tracing (args/output/error) is handled by `ToolRunner`
    via `tool_trace_recorder_var`.
    """

    max_output_chars: int = 12_000

    def __post_init__(self) -> None:
        self.max_output_chars = int(self.max_output_chars)

    def post_tool_messages(self, tool_messages: list[Message]) -> list[Message]:
        max_chars = int(self.max_output_chars)
        if max_chars <= 0:
            return tool_messages

        changed = False
        out: list[Message] = []

        for msg in tool_messages:
            if str(getattr(msg, "role", "") or "") != "tool":
                out.append(msg)
                continue

            tool_call_id = str(getattr(msg, "tool_call_id", "") or "")
            if not tool_call_id:
                out.append(msg)
                continue

            content_text = _extract_text(getattr(msg, "content", None))
            if len(content_text) <= max_chars:
                out.append(msg)
                continue

            suffix = (
                f"\n\n[...工具输出已截断：原始 {len(content_text)} 字符，阈值 {max_chars} 字符]"
            )
            keep = max(0, max_chars - len(suffix))
            truncated = suffix.strip() if keep <= 0 else content_text[:keep] + suffix
            if truncated == content_text:
                out.append(msg)
                continue

            try:
                out.append(
                    Message(
                        role="tool",
                        content=truncated,
                        name=getattr(msg, "name", None),
                        tool_call_id=tool_call_id,
                    )
                )
                changed = True
            except Exception:
                out.append(msg)

        return out if changed else tool_messages


_TRUNC_SUFFIX = "\n...[truncated]"


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return (len(text) + 3) // 4


def _tool_noise_tokens_for_message(message: Message) -> int:
    role = str(getattr(message, "role", "") or "")
    if role == "tool":
        return _estimate_tokens(_extract_text(getattr(message, "content", None)))

    tool_calls = getattr(message, "tool_calls", None)
    if role == "assistant" and tool_calls:
        parts: list[str] = []
        for call in tool_calls:
            name = str(getattr(call, "name", "") or "")
            args = str(getattr(call, "arguments_json", "") or "")
            if name or args:
                parts.append(f"{name}:{args}")
        return _estimate_tokens("\n".join(parts))

    return 0


def _collect_tool_groups(messages: Sequence[Message]) -> list[tuple[int, int, int]]:
    groups: list[tuple[int, int, int]] = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        role = str(getattr(msg, "role", "") or "")

        if role == "assistant" and getattr(msg, "tool_calls", None):
            start = i
            end = i + 1
            while end < len(messages) and str(getattr(messages[end], "role", "") or "") == "tool":
                end += 1
            cost = sum(_tool_noise_tokens_for_message(m) for m in messages[start:end])
            groups.append((start, end, cost))
            i = end
            continue

        if role == "tool":
            start = i
            end = i + 1
            while end < len(messages) and str(getattr(messages[end], "role", "") or "") == "tool":
                end += 1
            cost = sum(_tool_noise_tokens_for_message(m) for m in messages[start:end])
            groups.append((start, end, cost))
            i = end
            continue

        i += 1

    return groups


def _truncate_text_to_tokens(text: str, max_tokens: int) -> str:
    if max_tokens <= 0:
        return ""
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text
    if max_chars <= 0:
        return ""
    if max_chars <= len(_TRUNC_SUFFIX):
        return _TRUNC_SUFFIX[:max_chars]
    return text[: max_chars - len(_TRUNC_SUFFIX)] + _TRUNC_SUFFIX


def _shrink_last_tool_group(
    messages: list[Message],
    *,
    start: int,
    end: int,
    allowed_tokens: int,
) -> list[Message]:
    assistant_cost = 0
    tool_indices: list[int] = []
    for idx in range(start, end):
        msg = messages[idx]
        role = str(getattr(msg, "role", "") or "")
        if role == "tool":
            tool_indices.append(idx)
            continue
        assistant_cost += _tool_noise_tokens_for_message(msg)

    tool_budget = max(0, int(allowed_tokens) - assistant_cost)
    if not tool_indices:
        return messages

    base = tool_budget // len(tool_indices)
    remainder = tool_budget % len(tool_indices)

    new_messages = list(messages)
    for pos, msg_idx in enumerate(tool_indices):
        extra = 1 if pos >= (len(tool_indices) - remainder) else 0
        msg_budget = base + extra
        msg = messages[msg_idx]
        content_text = _extract_text(getattr(msg, "content", None))
        truncated = _truncate_text_to_tokens(content_text, msg_budget)
        if truncated == content_text:
            continue

        new_messages[msg_idx] = Message(
            role="tool",
            content=truncated,
            name=getattr(msg, "name", None),
            tool_call_id=str(getattr(msg, "tool_call_id", "") or ""),
        )
    return new_messages


@dataclass(slots=True)
class ContextToolUsesTrimStage(PipelineStage):
    """
    Context editing stage for native pipeline.

    Mirrors `ContextEditingMiddleware + ClearToolUsesEdit` at a stable-first level:
    - Only trims historical tool uses (assistant tool_calls + tool messages).
    - Never drops normal user/system/assistant text messages.
    - Protects the most recent tool-call group needed for the current tool-loop step.
    """

    max_tool_context_tokens: int = 1200

    def __post_init__(self) -> None:
        self.max_tool_context_tokens = max(0, int(self.max_tool_context_tokens))

    def pre_model(self, request: PipelineRequest) -> PipelineRequest:
        budget = int(self.max_tool_context_tokens)
        if budget <= 0:
            return request

        messages = list(request.messages or [])
        groups = _collect_tool_groups(messages)
        if not groups:
            return request

        total = sum(cost for _, _, cost in groups)
        if total <= budget:
            return request

        spans_to_remove: list[tuple[int, int]] = []
        remaining_total = total
        for start, end, cost in groups[:-1]:
            if remaining_total <= budget:
                break
            spans_to_remove.append((start, end))
            remaining_total -= cost

        if spans_to_remove:
            spans_to_remove.sort()
            new_messages: list[Message] = []
            span_idx = 0
            for idx, msg in enumerate(messages):
                while span_idx < len(spans_to_remove) and idx >= spans_to_remove[span_idx][1]:
                    span_idx += 1
                if span_idx < len(spans_to_remove):
                    s, e = spans_to_remove[span_idx]
                    if s <= idx < e:
                        continue
                new_messages.append(msg)
            messages = new_messages

        groups = _collect_tool_groups(messages)
        if not groups:
            request.messages = messages
            return request

        total = sum(cost for _, _, cost in groups)
        if total > budget:
            other_cost = sum(cost for _, _, cost in groups[:-1])
            allowed_for_last = max(0, budget - other_cost)
            start, end, _ = groups[-1]
            messages = _shrink_last_tool_group(
                messages, start=start, end=end, allowed_tokens=allowed_for_last
            )

        if messages != request.messages:
            logger.debug(
                "ContextToolUsesTrimStage applied: tool_tokens=%s budget=%s groups=%s",
                total,
                budget,
                len(groups),
            )
            request.messages = messages
        return request
