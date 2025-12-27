from __future__ import annotations

from types import MethodType

from src.agent.advanced_memory import LoreBook


class _DummyMultiCache:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], object] = {}

    def get(self, key: str, *, prefix: str) -> object | None:
        return self._store.get((prefix, key))

    def set(self, key: str, value: object, *, ttl: int, prefix: str) -> None:  # noqa: ARG002
        self._store[(prefix, key)] = value


def test_search_lore_cache_ignores_context_when_not_hybrid() -> None:
    lore = LoreBook.__new__(LoreBook)
    lore.vectorstore = object()
    lore.multi_cache = _DummyMultiCache()
    lore._last_search_hit = None
    lore._update_usage_count = lambda _lores: None  # type: ignore[assignment]
    lore._summarize_search_hit = staticmethod(lambda _lores: None)  # type: ignore[assignment]

    calls = {"n": 0}

    def _fake_vector(self, _query: str, _k: int, _category):  # noqa: ANN001
        calls["n"] += 1
        return [{"content": "x", "similarity": 0.9, "metadata": {}}]

    lore._search_with_vector_store = MethodType(_fake_vector, lore)  # type: ignore[assignment]

    r1 = lore.search_lore(
        query="hello",
        k=3,
        use_hybrid=False,
        use_rerank=True,
        context={"topic": "a", "keywords": ["x"]},
        use_cache=True,
    )
    r2 = lore.search_lore(
        query="hello",
        k=3,
        use_hybrid=False,
        use_rerank=True,
        context={"topic": "b", "keywords": ["y"]},
        use_cache=True,
    )
    assert calls["n"] == 1
    assert r1 == r2


def test_search_lore_cache_distinguishes_context_when_hybrid_and_rerank() -> None:
    lore = LoreBook.__new__(LoreBook)
    lore.vectorstore = object()
    lore.multi_cache = _DummyMultiCache()
    lore._last_search_hit = None
    lore._update_usage_count = lambda _lores: None  # type: ignore[assignment]
    lore._summarize_search_hit = staticmethod(lambda _lores: None)  # type: ignore[assignment]
    lore.query_expander = type("_QE", (), {"enabled": False})()

    calls = {"n": 0}

    def _fake_hybrid(
        self, _query: str, _k: int, _category, _use_rerank: bool, _context
    ):  # noqa: ANN001
        calls["n"] += 1
        return [{"content": "x", "similarity": 0.9, "metadata": {}}]

    lore._search_with_hybrid_retriever = MethodType(_fake_hybrid, lore)  # type: ignore[assignment]

    r1 = lore.search_lore(
        query="hello",
        k=3,
        use_hybrid=True,
        use_rerank=True,
        context={"topic": "a", "keywords": ["x"]},
        use_cache=True,
    )
    r2 = lore.search_lore(
        query="hello",
        k=3,
        use_hybrid=True,
        use_rerank=True,
        context={"topic": "b", "keywords": ["y"]},
        use_cache=True,
    )
    r3 = lore.search_lore(
        query="hello",
        k=3,
        use_hybrid=True,
        use_rerank=True,
        context={"topic": "a", "keywords": ["x"]},
        use_cache=True,
    )
    assert calls["n"] == 2
    assert r1 == r3
    assert r1 == r2
