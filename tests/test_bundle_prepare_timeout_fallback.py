from __future__ import annotations

import asyncio
import time

import pytest

from src.config.settings import settings


@pytest.mark.anyio
async def test_build_agent_bundle_falls_back_when_prepare_times_out(monkeypatch):
    from src.agent.core import MintChatAgent

    monkeypatch.setattr(settings.agent, "bundle_prepare_timeout_s", 0.05, raising=False)

    agent = MintChatAgent.__new__(MintChatAgent)
    agent.user_id = 1

    class _DummyMemory:
        def get_recent_messages(self):  # noqa: ANN001
            return [{"role": "assistant", "content": "prev"}]

    agent.memory = _DummyMemory()  # type: ignore[assignment]
    agent._build_context_with_state = lambda *_, **__: ""  # type: ignore[assignment]
    agent._prepare_interaction_context = lambda msg, **_: (msg, msg)  # type: ignore[assignment]

    never = asyncio.Event()

    async def _hang_prepare(*_args, **_kwargs):  # noqa: ANN001
        await never.wait()
        return []  # pragma: no cover

    async def _noop_proactive(*_args, **_kwargs):  # noqa: ANN001
        return None

    agent._prepare_messages_async = _hang_prepare  # type: ignore[assignment]
    agent._maybe_inject_proactive_knowledge = _noop_proactive  # type: ignore[assignment]

    class _DummyLoreBook:
        pusher = None

        def get_last_search_hit(self):  # noqa: ANN001
            return None

    agent.lore_book = _DummyLoreBook()  # type: ignore[assignment]

    started = time.monotonic()
    bundle = await agent._build_agent_bundle_async("hi")
    elapsed = time.monotonic() - started

    assert elapsed < 0.5
    assert bundle.messages[-1] == {"role": "user", "content": "hi"}
    assert bundle.messages[-2] == {"role": "assistant", "content": "prev"}
