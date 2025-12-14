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

import json
from dataclasses import dataclass
from functools import lru_cache
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

DEFAULT_SYSTEM_PROMPT = "Your goal is to select the most relevant tools for answering the user's query."


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
    ) -> None:
        super().__init__()
        self.system_prompt = system_prompt
        self.max_tools = max_tools
        self.always_include = always_include or []
        self.structured_output_method = structured_output_method or "json_mode"

        if isinstance(model, (BaseChatModel, type(None))):
            self.model: BaseChatModel | None = model
        else:
            if init_chat_model is None:  # pragma: no cover
                raise ImportError("langchain 未安装，无法通过字符串初始化选择模型")
            self.model = init_chat_model(model)

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
                f"If you exceed the maximum number of tools, only the first {self.max_tools} will be used."
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
        selection_request = self._prepare_selection_request(request)
        if selection_request is None:
            return handler(request)

        schema = _build_selection_schema(selection_request.valid_tool_names)
        try:
            structured_model = selection_request.model.with_structured_output(
                schema,
                method=self.structured_output_method,
                include_raw=True,
            )
            result = structured_model.invoke(
                [
                    {"role": "system", "content": selection_request.system_message},
                    selection_request.last_user_message,
                ]
            )
        except Exception as exc:
            logger.warning("工具筛选调用失败，已跳过筛选: %s", exc)
            return handler(request)

        tools = _extract_tools_from_any(result)
        if tools is None:
            logger.warning("工具筛选输出缺少 tools 字段，已跳过筛选")
            return handler(request)

        try:
            modified_request = self._apply_selection(
                request,
                tools,
                selection_request.available_tools,
                selection_request.valid_tool_names,
            )
        except Exception as exc:
            logger.warning("工具筛选结果处理失败，已跳过筛选: %s", exc)
            return handler(request)
        return handler(modified_request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        selection_request = self._prepare_selection_request(request)
        if selection_request is None:
            return await handler(request)

        schema = _build_selection_schema(selection_request.valid_tool_names)
        try:
            structured_model = selection_request.model.with_structured_output(
                schema,
                method=self.structured_output_method,
                include_raw=True,
            )
            result = await structured_model.ainvoke(
                [
                    {"role": "system", "content": selection_request.system_message},
                    selection_request.last_user_message,
                ]
            )
        except Exception as exc:
            logger.warning("工具筛选调用失败，已跳过筛选: %s", exc)
            return await handler(request)

        tools = _extract_tools_from_any(result)
        if tools is None:
            logger.warning("工具筛选输出缺少 tools 字段，已跳过筛选")
            return await handler(request)

        try:
            modified_request = self._apply_selection(
                request,
                tools,
                selection_request.available_tools,
                selection_request.valid_tool_names,
            )
        except Exception as exc:
            logger.warning("工具筛选结果处理失败，已跳过筛选: %s", exc)
            return await handler(request)
        return await handler(modified_request)
