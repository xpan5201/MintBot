from src.utils.embedding_cache import EmbeddingCache


def test_embedding_cache_set_get_roundtrip(temp_dir):
    cache_dir = temp_dir / "emb_cache"
    cache = EmbeddingCache(cache_dir=str(cache_dir), max_cache_size=10, cache_ttl_days=30)

    embedding = [0.1, 0.2, 0.3]
    cache.set("hello", "test-model", embedding)
    assert cache.get("hello", "test-model") == embedding


def test_embedding_cache_disk_fallback_without_index(temp_dir):
    cache_dir = temp_dir / "emb_cache"
    cache = EmbeddingCache(cache_dir=str(cache_dir), max_cache_size=10, cache_ttl_days=30)

    embedding = [0.4, 0.5]
    cache.set("persist-me", "test-model", embedding)

    # 新实例：即使 index.json 尚未落盘，也应能通过 .pkl 文件命中
    cache2 = EmbeddingCache(cache_dir=str(cache_dir), max_cache_size=10, cache_ttl_days=30)
    assert cache2.get("persist-me", "test-model") == embedding

