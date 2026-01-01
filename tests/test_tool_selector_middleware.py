from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List

import pytest

pytest.importorskip("langchain")
pytest.importorskip("langchain_core")

from langchain_core.messages import HumanMessage  # noqa: E402

from src.agent.tool_selector_middleware import MintChatToolSelectorMiddleware  # noqa: E402


class _DummyTool:
    def __init__(self, name: str):
        self.name = name


class _DummyMessage:
    def __init__(self, content: str):
        self.content = content


class _DummyStructuredModel:
    def __init__(self, result: Any):
        self._result = result

    def invoke(self, messages: Any) -> Any:
        return self._result

    async def ainvoke(self, messages: Any) -> Any:
        return self._result


class _DummyModel:
    def __init__(self, result: Any):
        self._result = result

    def with_structured_output(self, schema: Any, **kwargs: Any) -> _DummyStructuredModel:
        return _DummyStructuredModel(self._result)


@dataclass
class _DummyRequest:
    model: Any
    messages: List[Any]
    tools: List[Any]


def _handler(request: _DummyRequest) -> list[str]:
    return [tool.name for tool in request.tools if not isinstance(tool, dict)]


def test_tool_selector_parses_from_raw_when_parsed_missing() -> None:
    tools = [_DummyTool("calculator"), _DummyTool("get_weather")]
    result = {
        "raw": _DummyMessage('{"tools": ["calculator"]}'),
        "parsed": {},
        "parsing_error": Exception("bad"),
    }
    request = _DummyRequest(
        model=_DummyModel(result),
        messages=[HumanMessage(content="2+2")],
        tools=tools,
    )

    middleware = MintChatToolSelectorMiddleware(
        max_tools=4,
        always_include=[],
        structured_output_method="json_mode",
    )
    selected = middleware.wrap_model_call(request, _handler)
    assert selected == ["calculator"]


def test_tool_selector_keeps_all_on_unparseable_output() -> None:
    tools = [_DummyTool("calculator"), _DummyTool("get_weather")]
    result = {
        "raw": _DummyMessage("not json"),
        "parsed": {},
        "parsing_error": Exception("bad"),
    }
    request = _DummyRequest(
        model=_DummyModel(result),
        messages=[HumanMessage(content="hi")],
        tools=tools,
    )

    middleware = MintChatToolSelectorMiddleware(
        max_tools=4,
        always_include=[],
        structured_output_method="json_mode",
    )
    selected = middleware.wrap_model_call(request, _handler)
    assert selected == ["calculator", "get_weather"]
