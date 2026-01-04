from __future__ import annotations

from typing import Any

import src.agent.mcp_manager as mcp_manager_module
from src.llm_native.tools import callable_to_toolspec


class DummyToolMeta:
    def __init__(self, name: str, *, schema: dict[str, Any] | None = None) -> None:
        self.name = name
        self.description = name
        self.inputSchema = schema


def test_mcp_adapt_tools_binds_tool_name_per_function(monkeypatch):
    manager = mcp_manager_module.MCPManager()
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def fake_call_tool_sync(server: str, tool_name: str, arguments: dict[str, Any]) -> str:
        calls.append((server, tool_name, arguments))
        return f"{server}:{tool_name}"

    monkeypatch.setattr(manager, "call_tool_sync", fake_call_tool_sync)

    adapted = manager._adapt_tools(
        "srv",
        [
            DummyToolMeta("tool_one"),
            DummyToolMeta(
                "tool_two",
                schema={
                    "type": "object",
                    "properties": {"b": {"type": "integer"}},
                    "required": ["b"],
                },
            ),
        ],
    )
    assert len(adapted) == 2

    assert adapted[0](a=1) == "srv:tool_one"
    assert adapted[1](b=2) == "srv:tool_two"
    assert calls == [
        ("srv", "tool_one", {"a": 1}),
        ("srv", "tool_two", {"b": 2}),
    ]

    spec_one = callable_to_toolspec(adapted[0])
    assert spec_one is not None
    assert spec_one.name == "mcp_srv_tool_one"
    assert spec_one.parameters.get("type") == "object"

    spec_two = callable_to_toolspec(adapted[1])
    assert spec_two is not None
    assert spec_two.name == "mcp_srv_tool_two"
    assert spec_two.parameters.get("required") == ["b"]

    manager.close()
