from __future__ import annotations

from src.gui.workers import agent_chat


def test_agent_cache_deduplicates_creation(monkeypatch) -> None:
    with agent_chat._AGENT_CACHE_LOCK:
        agent_chat._AGENT_CACHE.clear()

    created: list[object] = []

    def fake_create_agent(user_id: object) -> object:
        created.append(user_id)
        return object()

    monkeypatch.setattr(agent_chat, "_create_agent", fake_create_agent)

    first = agent_chat.get_or_create_agent(1)
    second = agent_chat.get_or_create_agent("1")
    assert first is second
    assert created == [1]

    agent_chat.invalidate_agent_cache(1)
    third = agent_chat.get_or_create_agent(1)
    assert third is not first
    assert created == [1, 1]
