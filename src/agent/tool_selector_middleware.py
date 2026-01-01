"""
工具筛选中间件（兼容增强版）

背景：
LangChain 1.0.x 的 `LLMToolSelectorMiddleware` 会通过 `with_structured_output()` 让模型输出
`{"tools": [...]}` 结构。但在部分 OpenAI 兼容网关/模型组合下（尤其是 `json_schema` 模式），
解析可能得到 `{}` 或缺少 `tools` 字段，进而触发 `KeyError: 'tools'` 使程序闪退。

目标：
- 工具筛选失败时不崩溃，自动降级为“不过滤工具”（保持功能可用）
- 默认使用更兼容的 `json_mode` structured output
- 使用更小的 JSON Schema（enum 工具名）减少请求负担
"""

from __future__ import annotations

import asyncio
import collections
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from functools import lru_cache
from threading import Lock
from typing import Any, Awaitable, Callable, Optional

from src.utils.logger import get_logger

try:
    from langchain.agents.middleware.types import (
        AgentMiddleware,
        ModelCallResult,
        ModelRequest,
        ModelResponse,
    )
    from langchain.chat_models import init_chat_model
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import HumanMessage
    from langchain_core.tools import BaseTool
except Exception:  # pragma: no cover - 允许在缺少 LangChain 依赖时导入本模块
    AgentMiddleware = object  # type: ignore[misc,assignment]
    ModelCallResult = Any  # type: ignore[assignment]
    ModelRequest = Any  # type: ignore[assignment]
    ModelResponse = Any  # type: ignore[assignment]
    init_chat_model = None  # type: ignore[assignment]
    BaseChatModel = Any  # type: ignore[assignment]
    HumanMessage = Any  # type: ignore[assignment]
    BaseTool = Any  # type: ignore[assignment]

logger = get_logger(__name__)

DEFAULT_SYSTEM_PROMPT = (
    "Your goal is to select the most relevant tools for answering the user's query."
)

_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "time": ("时间", "几点", "日期", "today", "date", "time", "now"),
    "weather": ("天气", "气温", "温度", "下雨", "降雨", "forecast", "weather"),
    "map": ("地图", "导航", "路线", "怎么走", "附近", "地址", "map", "route", "nearby"),
    "search": ("搜索", "查一下", "查找", "搜一下", "资料", "news", "search", "google", "bing"),
    "file": (
        "文件",
        "目录",
        "路径",
        "读取",
        "打开",
        "保存到",
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
    "save_note",
    "set_reminder",
)

# 启发式：检测简单二元算式（避免把 calculator 误判成无关工具）。
# 注意：不要在字符类里引入多余的反斜杠，否则会触发 “bad character range \-*” 的正则错误。
_MATH_EXPR_RE = re.compile(r"(?:^|\s)(\d+(?:\.\d+)?)\s*([+*/-])\s*(\d+(?:\.\d+)?)(?:\s|$)")


@dataclass
class _SelectionRequest:
    available_tools: list[BaseTool]
    system_message: str
    last_user_message: HumanMessage
    model: BaseChatModel
    valid_tool_names: list[str]


def _build_selection_schema(valid_tool_names: list[str]) -> dict[str, Any]:
    return _build_selection_schema_cached(tuple(valid_tool_names))


@lru_cache(maxsize=128)
def _build_selection_schema_cached(valid_tool_names: tuple[str, ...]) -> dict[str, Any]:
    # 选择器只需要工具名枚举，避免 LangChain 默认 anyOf+description 过大导致兼容性问题。
    return {
        "title": "ToolSelectionResponse",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "tools": {
                "type": "array",
                "items": {"type": "string", "enum": list(valid_tool_names)},
                "description": "Tools to use. Place the most relevant tools first.",
            }
        },
        "required": ["tools"],
    }


def _extract_json_snippet(text: str) -> Optional[str]:
    """
    从文本中提取首个 JSON 对象/数组片段（支持前后带杂讯/代码块），用于宽松解析。
    """
    if not text:
        return None
    s = text.strip()
    if not s:
        return None

    # 找到第一个 '{' 或 '['
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


def _normalize_tool_list(value: Any) -> Optional[list[str]]:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        # 尝试把字符串当作 JSON 解析
        snippet = _extract_json_snippet(raw) or raw
        try:
            parsed = json.loads(snippet)
            if isinstance(parsed, dict):
                return _normalize_tool_list(parsed.get("tools"))
            if isinstance(parsed, list):
                return _normalize_tool_list(parsed)
        except Exception:
            pass
        # 退化：按逗号/换行切分
        parts = [p.strip() for p in raw.replace("\n", ",").split(",")]
        return [p for p in parts if p]
    return None


def _extract_tools_from_any(result: Any) -> Optional[list[str]]:
    """
    兼容 `with_structured_output(include_raw=True)` 的返回：
    - dict(raw, parsed, parsing_error)
    也兼容直接返回 dict / message content。
    """
    if result is None:
        return None

    if isinstance(result, dict):
        # include_raw=True 的结构
        if "parsed" in result:
            parsed = result.get("parsed")
            if isinstance(parsed, dict):
                tools = _normalize_tool_list(parsed.get("tools"))
                if tools is not None:
                    return tools

            raw_msg = result.get("raw")
            content = getattr(raw_msg, "content", None)
            if isinstance(content, str):
                snippet = _extract_json_snippet(content)
                if snippet:
                    try:
                        parsed = json.loads(snippet)
                        if isinstance(parsed, dict):
                            tools = _normalize_tool_list(parsed.get("tools"))
                            if tools is not None:
                                return tools
                        if isinstance(parsed, list):
                            tools = _normalize_tool_list(parsed)
                            if tools is not None:
                                return tools
                    except Exception:
                        pass
            return None

        # 直接 dict（理论上应该包含 tools）
        tools = _normalize_tool_list(result.get("tools"))
        if tools is not None:
            return tools
        return None

    # 直接 message/对象
    content = getattr(result, "content", None)
    if isinstance(content, str):
        snippet = _extract_json_snippet(content)
        if snippet:
            try:
                parsed = json.loads(snippet)
                if isinstance(parsed, dict):
                    return _normalize_tool_list(parsed.get("tools"))
                if isinstance(parsed, list):
                    return _normalize_tool_list(parsed)
            except Exception:
                return None
    return None


class MintChatToolSelectorMiddleware(AgentMiddleware):
    """
    LLM 工具筛选中间件（兼容增强版）。

    - 成功解析到 `tools` 字段：按选择结果过滤工具（并保留 always_include）
    - 选择失败/解析失败：不修改 request.tools，继续执行主模型（避免闪退）
    """

    def __init__(
        self,
        *,
        model: str | BaseChatModel | None = None,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        max_tools: int | None = None,
        always_include: list[str] | None = None,
        structured_output_method: str = "json_mode",
        timeout_s: float = 4.0,
        disable_cooldown_s: float = 300.0,
    ) -> None:
        super().__init__()
        self.system_prompt = system_prompt
        self.max_tools = max_tools
        self.always_include = always_include or []
        self.structured_output_method = structured_output_method or "json_mode"
        self.timeout_s = max(0.0, float(timeout_s))
        self.disable_cooldown_s = max(0.0, float(disable_cooldown_s))
        self._disabled_until: float = 0.0
        self._executor: ThreadPoolExecutor | None = None
        self._selection_cache: collections.OrderedDict[tuple[str, tuple[str, ...]], list[str]] = (
            collections.OrderedDict()
        )
        self._selection_cache_lock = Lock()
        self._selection_cache_max = 128

        if isinstance(model, (BaseChatModel, type(None))):
            self.model: BaseChatModel | None = model
        else:
            if init_chat_model is None:  # pragma: no cover
                raise ImportError("langchain 未安装，无法通过字符串初始化选择模型")
            self.model = init_chat_model(model)

    def _trip_circuit(self) -> None:
        if self.disable_cooldown_s <= 0:
            return
        try:
            self._disabled_until = time.monotonic() + self.disable_cooldown_s
        except Exception:
            self._disabled_until = float("inf")

    def _should_bypass(self) -> bool:
        try:
            is_finalizing = bool(getattr(sys, "is_finalizing", lambda: False)())
        except Exception:
            is_finalizing = False
        if is_finalizing:
            return True

        if self._disabled_until <= 0:
            return False
        try:
            return time.monotonic() < self._disabled_until
        except Exception:
            return True

    def _ensure_executor(self) -> ThreadPoolExecutor:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="mintchat-tool-select"
            )
        return self._executor

    def close(self) -> None:
        """释放中间件内部资源（线程池/缓存）。"""
        self._selection_cache.clear()
        executor = self._executor
        self._executor = None
        if executor is None:
            return
        try:
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                executor.shutdown(wait=False)
        except Exception:
            pass

    def _cache_get(self, key: tuple[str, tuple[str, ...]]) -> Optional[list[str]]:
        with self._selection_cache_lock:
            value = self._selection_cache.get(key)
            if value is None:
                return None
            # LRU: move to end
            try:
                self._selection_cache.move_to_end(key)
            except Exception:
                pass
            return list(value)

    def _cache_set(self, key: tuple[str, tuple[str, ...]], value: list[str]) -> None:
        if not key or not value:
            return
        with self._selection_cache_lock:
            self._selection_cache[key] = list(value)
            try:
                self._selection_cache.move_to_end(key)
            except Exception:
                pass
            while len(self._selection_cache) > self._selection_cache_max:
                try:
                    self._selection_cache.popitem(last=False)
                except Exception:
                    break

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

        # 额外启发：检测算式（提升 calculator 命中率）
        try:
            if _MATH_EXPR_RE.search(user_text):
                scores["calc"] = scores.get("calc", 0) + 2
        except Exception:
            pass
        return scores

    def _heuristic_select_tool_names(
        self, user_text: str, tool_names: list[str]
    ) -> tuple[list[str], int]:
        """
        启发式预筛选：基于用户文本快速缩小候选工具集合，减少工具 schema 体积与额外 LLM 调用次数。

        Returns:
            (selected_tool_names, hit_score)
        """
        if not tool_names:
            return [], 0

        scores = self._score_categories(user_text)
        hit_score = sum(scores.values())
        if not scores:
            # 无明显意图：不要强行收缩候选工具，避免误删可用工具导致“工具不可用/空回复”。
            return [], 0

        selected: list[str] = []
        name_set = set(tool_names)

        # 1) 优先按类别得分排序
        for category, _ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True):
            hints = _CATEGORY_TOOL_NAME_HINTS.get(category, ())
            for name in tool_names:
                lname = name.lower()
                if name not in name_set:
                    continue
                if any(h in lname for h in hints):
                    selected.append(name)

        # 2) 如果用户文本显式提到工具名（或类似片段），也加入（提高可控性）
        lower_text = (user_text or "").lower()
        for name in tool_names:
            lname = name.lower()
            if lname in lower_text and name not in selected:
                selected.append(name)

        # 3) 兜底补齐一些通用工具（仍保持小集合）
        for name in _DEFAULT_FALLBACK_TOOL_NAMES:
            if name in name_set and name not in selected:
                selected.append(name)

        # 限制数量：防止 optional/mcp 工具名过于相似导致候选膨胀
        max_keep = 12
        if self.max_tools is not None:
            max_keep = max(8, min(24, int(self.max_tools) * 3))
        return selected[:max_keep], hit_score

    def _apply_heuristic_prefilter(self, request: ModelRequest, user_text: str) -> int:
        """
        基于启发式预筛选 request.tools，避免每次都把大量工具传入主模型。

        Returns:
            hit_score: 启发式命中强度（0 表示未命中明显工具意图）。
        """
        tools = list(getattr(request, "tools", []) or [])
        if not tools:
            return 0

        base_tools = [tool for tool in tools if not isinstance(tool, dict)]
        if not base_tools:
            return 0

        always_include_set = set(self.always_include)
        provider_tools = [tool for tool in tools if isinstance(tool, dict)]
        name_to_tool = {tool.name: tool for tool in base_tools}

        candidate_names = [tool.name for tool in base_tools if tool.name not in always_include_set]
        selected_names, hit_score = self._heuristic_select_tool_names(user_text, candidate_names)
        if not selected_names and not always_include_set:
            return hit_score

        new_tools: list[Any] = []
        seen: set[str] = set()

        for name in selected_names:
            tool = name_to_tool.get(name)
            if tool is None:
                continue
            if tool.name in always_include_set:
                continue
            if tool.name in seen:
                continue
            new_tools.append(tool)
            seen.add(tool.name)

        # always_include 按原始顺序保留，避免影响使用习惯
        for tool in base_tools:
            if tool.name not in always_include_set:
                continue
            if tool.name in seen:
                continue
            new_tools.append(tool)
            seen.add(tool.name)

        new_tools.extend(provider_tools)
        request.tools = new_tools
        return hit_score

    def _invoke_with_timeout(self, structured_model: Any, messages: list[Any]) -> Any:
        if self.timeout_s <= 0:
            return structured_model.invoke(messages)
        future = self._ensure_executor().submit(structured_model.invoke, messages)
        try:
            return future.result(timeout=self.timeout_s)
        except FuturesTimeoutError as exc:
            try:
                future.cancel()
            except Exception:
                pass
            raise TimeoutError(f"tool_selector_timeout_s={self.timeout_s}") from exc

    def _prepare_selection_request(self, request: ModelRequest) -> Optional[_SelectionRequest]:
        if not getattr(request, "tools", None):
            return None
        tools = list(request.tools)
        if not tools:
            return None

        base_tools = [tool for tool in tools if not isinstance(tool, dict)]
        if not base_tools:
            return None

        if self.always_include:
            available_tool_names = {tool.name for tool in base_tools}
            missing = [name for name in self.always_include if name not in available_tool_names]
            if missing:
                logger.warning("always_include 中存在未注册工具: %s", ",".join(missing))

        available_tools = [tool for tool in base_tools if tool.name not in set(self.always_include)]
        if not available_tools:
            return None

        system_message = self.system_prompt
        if self.max_tools is not None:
            system_message += (
                "\nIMPORTANT: List the tool names in order of relevance, "
                "with the most relevant first. "
                f"If you exceed the maximum number of tools, only the first "
                f"{self.max_tools} will be used."
            )
        # 显式要求返回固定结构，提升兼容性（尤其是 json_mode 场景）
        system_message += '\nReturn ONLY a JSON object like: {"tools": ["tool_name"]}.'

        last_user_message: HumanMessage
        for message in reversed(request.messages):
            if isinstance(message, HumanMessage):
                last_user_message = message
                break
        else:
            raise AssertionError("No user message found in request messages")

        model = self.model or request.model
        valid_tool_names = [tool.name for tool in available_tools]
        return _SelectionRequest(
            available_tools=available_tools,
            system_message=system_message,
            last_user_message=last_user_message,
            model=model,
            valid_tool_names=valid_tool_names,
        )

    def _apply_selection(
        self,
        request: ModelRequest,
        selection: list[str],
        available_tools: list[BaseTool],
        valid_tool_names: list[str],
    ) -> ModelRequest:
        selected_tool_names: list[str] = []
        for tool_name in selection:
            if tool_name not in valid_tool_names:
                continue
            if tool_name in selected_tool_names:
                continue
            if self.max_tools is not None and len(selected_tool_names) >= self.max_tools:
                break
            selected_tool_names.append(tool_name)

        selected_tools = [tool for tool in available_tools if tool.name in set(selected_tool_names)]
        always_included_tools = [
            tool
            for tool in request.tools
            if not isinstance(tool, dict) and tool.name in set(self.always_include)
        ]
        selected_tools.extend(always_included_tools)
        provider_tools = [tool for tool in request.tools if isinstance(tool, dict)]
        request.tools = [*selected_tools, *provider_tools]
        return request

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelCallResult:
        if self._should_bypass():
            return handler(request)

        # 性能优化：先用启发式快速缩小候选工具集合，避免每次都额外调用一次 LLM。
        # 这样即便后续 LLM 筛选超时/失败，也不会把大量工具 schema 塞进主模型上下文。
        # NOTE: 这里不依赖 LLM 输出，预筛选应尽量轻量且容错。
        try:
            last_user_text = ""
            for message in reversed(request.messages):
                if isinstance(message, HumanMessage):
                    last_user_text = str(getattr(message, "content", "") or "")
                    break
            if last_user_text:
                self._apply_heuristic_prefilter(request, last_user_text)
        except Exception:
            pass

        selection_request = self._prepare_selection_request(request)
        if selection_request is None:
            return handler(request)

        # 若候选工具已经足够小，跳过 LLM 筛选（避免增加首包延迟）。
        # 经验阈值：max_tools*3（默认 12）内的工具，交给主模型自行决定即可。
        try:
            llm_select_threshold = 12
            if self.max_tools is not None:
                llm_select_threshold = max(8, int(self.max_tools) * 3)
        except Exception:
            llm_select_threshold = 12
        if len(selection_request.valid_tool_names) <= llm_select_threshold:
            return handler(request)

        # 对同一条用户消息的多次 model call（工具链循环/重试）复用筛选结果
        try:
            user_key = (
                str(getattr(selection_request.last_user_message, "content", "") or "")
                .strip()
                .lower()
            )
            cache_key = (user_key[:500], tuple(selection_request.valid_tool_names))
            cached = self._cache_get(cache_key)
        except Exception:
            cached = None
            cache_key = None  # type: ignore[assignment]
        if cached:
            try:
                modified_request = self._apply_selection(
                    request,
                    cached,
                    selection_request.available_tools,
                    selection_request.valid_tool_names,
                )
                return handler(modified_request)
            except Exception:
                # 缓存命中但应用失败：继续走实时筛选（或降级）
                pass

        schema = _build_selection_schema(selection_request.valid_tool_names)
        try:
            structured_model = selection_request.model.with_structured_output(
                schema,
                method=self.structured_output_method,
                include_raw=True,
            )
            messages = [
                {"role": "system", "content": selection_request.system_message},
                selection_request.last_user_message,
            ]
            result = self._invoke_with_timeout(structured_model, messages)
        except TimeoutError as exc:
            logger.warning("工具筛选调用超时，已跳过筛选: %s", exc)
            self._trip_circuit()
            return handler(request)
        except Exception as exc:
            logger.warning("工具筛选调用失败，已跳过筛选: %s", exc)
            self._trip_circuit()
            return handler(request)

        tools = _extract_tools_from_any(result)
        if tools is None:
            logger.warning("工具筛选输出缺少 tools 字段，已跳过筛选")
            self._trip_circuit()
            return handler(request)

        try:
            if cache_key is not None:
                self._cache_set(cache_key, tools)
        except Exception:
            pass

        try:
            modified_request = self._apply_selection(
                request,
                tools,
                selection_request.available_tools,
                selection_request.valid_tool_names,
            )
        except Exception as exc:
            logger.warning("工具筛选结果处理失败，已跳过筛选: %s", exc)
            self._trip_circuit()
            return handler(request)
        return handler(modified_request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        if self._should_bypass():
            return await handler(request)

        try:
            last_user_text = ""
            for message in reversed(request.messages):
                if isinstance(message, HumanMessage):
                    last_user_text = str(getattr(message, "content", "") or "")
                    break
            if last_user_text:
                self._apply_heuristic_prefilter(request, last_user_text)
        except Exception:
            pass

        selection_request = self._prepare_selection_request(request)
        if selection_request is None:
            return await handler(request)

        try:
            llm_select_threshold = 12
            if self.max_tools is not None:
                llm_select_threshold = max(8, int(self.max_tools) * 3)
        except Exception:
            llm_select_threshold = 12
        if len(selection_request.valid_tool_names) <= llm_select_threshold:
            return await handler(request)

        try:
            user_key = (
                str(getattr(selection_request.last_user_message, "content", "") or "")
                .strip()
                .lower()
            )
            cache_key = (user_key[:500], tuple(selection_request.valid_tool_names))
            cached = self._cache_get(cache_key)
        except Exception:
            cached = None
            cache_key = None  # type: ignore[assignment]
        if cached:
            try:
                modified_request = self._apply_selection(
                    request,
                    cached,
                    selection_request.available_tools,
                    selection_request.valid_tool_names,
                )
                return await handler(modified_request)
            except Exception:
                pass

        schema = _build_selection_schema(selection_request.valid_tool_names)
        try:
            structured_model = selection_request.model.with_structured_output(
                schema,
                method=self.structured_output_method,
                include_raw=True,
            )
            messages = [
                {"role": "system", "content": selection_request.system_message},
                selection_request.last_user_message,
            ]
            if self.timeout_s > 0:
                result = await asyncio.wait_for(
                    structured_model.ainvoke(messages), timeout=self.timeout_s
                )
            else:
                result = await structured_model.ainvoke(messages)
        except asyncio.TimeoutError:
            logger.warning("工具筛选调用超时，已跳过筛选: timeout=%.1fs", self.timeout_s)
            self._trip_circuit()
            return await handler(request)
        except Exception as exc:
            logger.warning("工具筛选调用失败，已跳过筛选: %s", exc)
            self._trip_circuit()
            return await handler(request)

        tools = _extract_tools_from_any(result)
        if tools is None:
            logger.warning("工具筛选输出缺少 tools 字段，已跳过筛选")
            self._trip_circuit()
            return await handler(request)

        try:
            if cache_key is not None:
                self._cache_set(cache_key, tools)
        except Exception:
            pass

        try:
            modified_request = self._apply_selection(
                request,
                tools,
                selection_request.available_tools,
                selection_request.valid_tool_names,
            )
        except Exception as exc:
            logger.warning("工具筛选结果处理失败，已跳过筛选: %s", exc)
            self._trip_circuit()
            return await handler(request)
        return await handler(modified_request)
