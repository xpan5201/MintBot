from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import pytest


@pytest.mark.anyio
async def test_proactive_push_skipped_in_memory_fast_mode(monkeypatch):
    from src.agent.core import MintChatAgent
    from src.config.settings import settings

    monkeypatch.setattr(settings.agent, "memory_fast_mode", True, raising=False)
    monkeypatch.setattr(settings.agent, "proactive_push_in_fast_mode", False, raising=False)
    monkeypatch.setattr(settings.agent, "proactive_push_enabled", True, raising=False)
    monkeypatch.setattr(settings.agent, "proactive_push_k", 1, raising=False)

    agent = MintChatAgent.__new__(MintChatAgent)
    agent.user_id = 1
    agent._background_executor = ThreadPoolExecutor(max_workers=1)

    class _DummyLoreBook:
        pusher = object()

        def push_knowledge(self, user_id, context, k):  # noqa: ANN001
            raise AssertionError("push_knowledge should not run in memory_fast_mode")

    agent.lore_book = _DummyLoreBook()

    try:
        messages = [{"role": "user", "content": "hi"}]
        await agent._maybe_inject_proactive_knowledge(messages, context={"user_message": "hi"})
    finally:
        agent._background_executor.shutdown(wait=True, cancel_futures=True)

    assert messages == [{"role": "user", "content": "hi"}]


@pytest.mark.anyio
async def test_proactive_push_timeout_skips_injection(monkeypatch):
    from src.agent.core import MintChatAgent
    from src.config.settings import settings

    monkeypatch.setattr(settings.agent, "memory_fast_mode", False, raising=False)
    monkeypatch.setattr(settings.agent, "proactive_push_in_fast_mode", False, raising=False)
    monkeypatch.setattr(settings.agent, "proactive_push_enabled", True, raising=False)
    monkeypatch.setattr(settings.agent, "proactive_push_k", 1, raising=False)
    monkeypatch.setattr(settings.agent, "proactive_push_timeout_s", 0.01, raising=False)

    agent = MintChatAgent.__new__(MintChatAgent)
    agent.user_id = 1
    agent._background_executor = ThreadPoolExecutor(max_workers=1)

    class _DummyLoreBook:
        pusher = object()

        def push_knowledge(self, user_id, context, k):  # noqa: ANN001
            time.sleep(0.05)
            return [{"title": "T", "content": "C"}]

    agent.lore_book = _DummyLoreBook()

    try:
        messages = [{"role": "user", "content": "hi"}]
        await agent._maybe_inject_proactive_knowledge(messages, context={"user_message": "hi"})
    finally:
        agent._background_executor.shutdown(wait=True, cancel_futures=True)

    assert messages == [{"role": "user", "content": "hi"}]
