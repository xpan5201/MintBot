from __future__ import annotations

from src.agent.tools import ToolRegistry
from src.config.settings import settings


def test_tool_registry_get_tool_specs(monkeypatch):
    monkeypatch.setattr(settings.agent, "enable_tools", True, raising=False)
    monkeypatch.setattr(settings.agent, "enable_builtin_tools", False, raising=False)
    monkeypatch.setattr(settings.agent, "enable_mcp_tools", False, raising=False)

    reg = ToolRegistry()
    try:
        specs = reg.get_tool_specs()
        assert specs

        names = {s.name for s in specs}
        assert "get_current_time" in names

        weather = next(s for s in specs if s.name == "get_weather")
        payload = weather.to_openai()
        assert payload["type"] == "function"
        assert payload["function"]["name"] == "get_weather"
        assert payload["function"]["parameters"].get("additionalProperties") is False
        assert "strict" not in payload["function"]

        strict_specs = reg.get_tool_specs(strict=True)
        strict_weather = next(s for s in strict_specs if s.name == "get_weather")
        strict_payload = strict_weather.to_openai()
        assert strict_payload["function"]["strict"] is True
    finally:
        reg.close()
