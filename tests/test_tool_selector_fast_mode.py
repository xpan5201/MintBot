from __future__ import annotations

import src.agent.core as core_module
from src.agent.core import MintChatAgent
from src.config.settings import settings


def test_tool_selector_skipped_in_fast_mode(monkeypatch) -> None:
    monkeypatch.setattr(settings.agent, "memory_fast_mode", True, raising=False)
    monkeypatch.setattr(settings.agent, "tool_selector_enabled", True, raising=False)
    monkeypatch.setattr(settings.agent, "tool_selector_in_fast_mode", False, raising=False)
    monkeypatch.setattr(core_module, "HAS_TOOL_SELECTOR", True, raising=False)

    agent = MintChatAgent.__new__(MintChatAgent)

    class ExplodingRegistry:
        def get_tool_names(self) -> list[str]:
            raise AssertionError("tool_registry.get_tool_names should not be called")

    agent.tool_registry = ExplodingRegistry()  # type: ignore[assignment]

    assert agent._build_tool_selector_middleware() is None
