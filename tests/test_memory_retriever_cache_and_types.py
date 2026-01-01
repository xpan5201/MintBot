from __future__ import annotations

from dataclasses import dataclass

import pytest


@dataclass
class _DummyCache:
    seen_keys: list[str]

    def get(self, key: str):  # noqa: ANN001
        self.seen_keys.append(str(key))
        return None

    def set(self, key: str, value):  # noqa: ANN001
        return None


class _DummyLongTermManager:
    def __init__(self, *, user_id: int, lt_version: int = 0) -> None:
        self.user_id = user_id
        self.long_term = type("_LT", (), {"write_version": lt_version})()

    def search_relevant_memories(self, query: str, k: int):  # noqa: ANN001
        return [f"lt:{query}:{k}"]


class _DummyCoreMemory:
    def __init__(self, *, version: int = 0) -> None:
        self.vectorstore = object()
        self.write_version = version

    def search_core_memories(self, query: str, k: int):  # noqa: ANN001
        return [{"content": f"core:{query}:{k}"}]


@pytest.mark.anyio
async def test_memory_retriever_core_returns_strings(monkeypatch):
    from src.agent.memory_retriever import ConcurrentMemoryRetriever, cache_manager as cm

    dummy_cache = _DummyCache(seen_keys=[])
    monkeypatch.setattr(cm, "memory_cache", dummy_cache)

    retriever = ConcurrentMemoryRetriever(
        long_term_memory=_DummyLongTermManager(user_id=1),
        core_memory=_DummyCoreMemory(),
        max_workers=1,
    )
    try:
        result = await retriever.retrieve_all_memories_async("hello", use_cache=True)
    finally:
        retriever.close()

    assert result["long_term"] == ["lt:hello:5"]
    assert result["core"] == ["core:hello:2"]


@pytest.mark.anyio
async def test_memory_retriever_cache_key_is_user_scoped(monkeypatch):
    from src.agent.memory_retriever import ConcurrentMemoryRetriever, cache_manager as cm

    dummy_cache = _DummyCache(seen_keys=[])
    monkeypatch.setattr(cm, "memory_cache", dummy_cache)

    async def run(
        user_id: int,
        lt_version: int,
        *,
        core_version: int = 0,
    ) -> str:
        retriever = ConcurrentMemoryRetriever(
            long_term_memory=_DummyLongTermManager(user_id=user_id, lt_version=lt_version),
            core_memory=_DummyCoreMemory(version=core_version),
            max_workers=1,
        )
        try:
            await retriever.retrieve_all_memories_async("same-query", use_cache=True)
        finally:
            retriever.close()
        assert dummy_cache.seen_keys
        return dummy_cache.seen_keys[-1]

    key_u1 = await run(user_id=1, lt_version=0)
    key_u2 = await run(user_id=2, lt_version=0)
    assert key_u1 != key_u2

    key_v0 = await run(user_id=1, lt_version=0)
    key_v1 = await run(user_id=1, lt_version=1)
    assert key_v0 != key_v1

    key_c0 = await run(user_id=1, lt_version=0, core_version=0)
    key_c1 = await run(user_id=1, lt_version=0, core_version=1)
    assert key_c0 != key_c1
