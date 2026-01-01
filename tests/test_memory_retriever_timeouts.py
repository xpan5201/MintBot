from __future__ import annotations

import asyncio
import time

import pytest


class _DummyLongTermManager:
    def __init__(self) -> None:
        self.user_id = 1
        self.long_term = type("_LT", (), {"write_version": 0})()

    def search_relevant_memories(self, query: str, k: int):  # noqa: ANN001
        return [f"lt:{query}:{k}"]


class _DummyCoreMemory:
    def __init__(self) -> None:
        self.vectorstore = object()

    def search_core_memories(self, query: str, k: int):  # noqa: ANN001
        return [{"content": f"core:{query}:{k}"}]


@pytest.mark.anyio
async def test_memory_retriever_source_timeout_skips_hanging_source(monkeypatch):
    from src.agent.memory_retriever import ConcurrentMemoryRetriever

    retriever = ConcurrentMemoryRetriever(
        long_term_memory=_DummyLongTermManager(),
        core_memory=_DummyCoreMemory(),
        max_workers=1,
        source_timeout_s=0.1,
    )
    try:
        hang_event = asyncio.Event()

        async def _hang_long_term(query: str, k: int):  # noqa: ANN001
            return await retriever._await_with_metrics("long_term", hang_event.wait())

        monkeypatch.setattr(retriever, "_retrieve_long_term_async", _hang_long_term)

        started = time.monotonic()
        result = await retriever.retrieve_all_memories_async("hello", use_cache=False)
        elapsed = time.monotonic() - started
    finally:
        retriever.close()

    assert elapsed < 0.5
    assert result["long_term"] == []
    assert result["core"] == ["core:hello:2"]
