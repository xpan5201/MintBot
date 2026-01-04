from __future__ import annotations

import pytest

from src.llm_native.tools import ToolRegistry, ToolSpec


def test_tool_spec_to_openai():
    spec = ToolSpec(
        name="get_weather",
        description="Get current weather.",
        parameters={
            "type": "object",
            "properties": {"location": {"type": "string"}},
            "required": ["location"],
            "additionalProperties": False,
        },
        strict=True,
    )
    payload = spec.to_openai()
    assert payload["type"] == "function"
    assert payload["function"]["name"] == "get_weather"
    assert payload["function"]["strict"] is True


def test_tool_registry_register_and_list():
    reg = ToolRegistry()
    reg.register(
        ToolSpec(
            name="foo",
            description="x",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
        )
    )
    assert reg.get("foo") is not None
    assert len(reg.tools()) == 1
    payload = reg.to_openai()[0]
    assert payload["function"]["name"] == "foo"
    assert "strict" not in payload["function"]


def test_tool_registry_rejects_duplicates():
    reg = ToolRegistry()
    reg.register(
        ToolSpec(
            name="foo",
            description="x",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
        )
    )
    with pytest.raises(ValueError, match="already registered"):
        reg.register(
            ToolSpec(
                name="foo",
                description="y",
                parameters={"type": "object", "properties": {}, "additionalProperties": False},
            )
        )
