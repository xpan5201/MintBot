from __future__ import annotations

from src.utils.cache_manager import LRUCache, SmartCacheManager


def test_lru_cache_set_prefers_purging_expired(monkeypatch) -> None:
    from src.utils import cache_manager as cache_manager_module

    now = 0.0

    def fake_monotonic() -> float:
        return now

    monkeypatch.setattr(cache_manager_module.time, "monotonic", fake_monotonic)

    cache = LRUCache(max_size=2, ttl=10)
    cache.set("a", 1)
    cache.set("b", 2)
    assert cache.get("a") == 1

    now = 20.0
    cache.set("c", 3)

    assert cache.get("a") is None
    assert cache.get("b") is None
    assert cache.get("c") == 3
    assert cache.get_stats()["evictions"] == 0


def test_generate_key_handles_unserializable_objects() -> None:
    key = SmartCacheManager._generate_key(object(), payload=b"\x00\x01")
    assert isinstance(key, str)
    assert len(key) == 32
