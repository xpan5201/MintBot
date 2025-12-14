from __future__ import annotations

from typing import Any

import src.agent.mcp_manager as mcp_manager_module


class DummyStructuredTool:
    def __init__(self, func, *, name: str, description: str, args_schema=None) -> None:
        self._func = func
        self.name = name
        self.description = description
        self.args_schema = args_schema

    @classmethod
    def from_function(cls, func, *, name: str, description: str, args_schema=None):
        return cls(func, name=name, description=description, args_schema=args_schema)

    def invoke(self, kwargs: dict[str, Any]) -> str:
        return str(self._func(**kwargs))


class DummyToolMeta:
    def __init__(self, name: str) -> None:
        self.name = name
        self.description = name
        self.inputSchema = None


def test_mcp_adapt_tools_binds_tool_name_per_function(monkeypatch):
    monkeypatch.setattr(mcp_manager_module, "HAS_STRUCTURED_TOOL", True)
    monkeypatch.setattr(mcp_manager_module, "StructuredTool", DummyStructuredTool)

    manager = mcp_manager_module.MCPManager()
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def fake_call_tool_sync(server: str, tool_name: str, arguments: dict[str, Any]) -> str:
        calls.append((server, tool_name, arguments))
        return f"{server}:{tool_name}"

    monkeypatch.setattr(manager, "call_tool_sync", fake_call_tool_sync)

    adapted = manager._adapt_tools("srv", [DummyToolMeta("tool_one"), DummyToolMeta("tool_two")])
    assert len(adapted) == 2

    assert adapted[0].invoke({"a": 1}) == "srv:tool_one"
    assert adapted[1].invoke({"b": 2}) == "srv:tool_two"
    assert calls == [
        ("srv", "tool_one", {"a": 1}),
        ("srv", "tool_two", {"b": 2}),
    ]

    manager.close()

