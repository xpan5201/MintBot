from __future__ import annotations

import threading
import time

from src.agent.performance_optimizer import MultiLevelCache
from src.utils.advanced_performance import SmartPreloader


def test_multi_level_cache_l1_basic_and_ttl_zero_expires():
    cache = MultiLevelCache(enable_redis=False, max_memory_items=10, default_ttl=60)
    try:
        assert cache.get("missing", prefix="pytest") is None

        cache.set("k1", {"v": 1}, ttl=5, prefix="pytest")
        assert cache.get("k1", prefix="pytest") == {"v": 1}

        cache.set("k2", "value", ttl=0, prefix="pytest")
        time.sleep(0.001)  # ensure monotonic advances past expire_at
        assert cache.get("k2", prefix="pytest") is None

        cache.close()
        cache.close()  # idempotent
    finally:
        # close() already clears, but keep test robust
        try:
            cache.close()
        except Exception:
            pass


def test_smart_preloader_threadsafe_and_deduplicates_inflight():
    preloader = SmartPreloader(max_cache_size=10)
    lock = threading.Lock()
    started = threading.Event()
    calls = 0

    def loader() -> int:
        nonlocal calls
        with lock:
            calls += 1
        started.set()
        time.sleep(0.05)
        return 123

    try:
        for _ in range(20):
            preloader.preload("key", loader)

        assert started.wait(timeout=1.0)

        deadline = time.time() + 2.0
        value = None
        while time.time() < deadline:
            value = preloader.get("key")
            if value is not None:
                break
            time.sleep(0.01)

        assert value == 123
        assert calls == 1

        preloader.close()
        preloader.close()  # idempotent
    finally:
        try:
            preloader.close()
        except Exception:
            pass


def test_smart_preloader_does_not_cache_failures_and_allows_retry():
    preloader = SmartPreloader(max_cache_size=10)
    lock = threading.Lock()
    fail_done = threading.Event()
    success_done = threading.Event()
    calls = 0

    def loader() -> int:
        nonlocal calls
        with lock:
            calls += 1
            current = calls
        if current == 1:
            fail_done.set()
            raise RuntimeError("boom")
        success_done.set()
        return 456

    try:
        preloader.preload("key", loader)
        assert fail_done.wait(timeout=1.0)

        # 等待后台线程完成收尾（inflight 清理），否则第二次 preload 可能被去重逻辑拦截
        deadline = time.time() + 2.0
        while time.time() < deadline:
            if preloader.get_stats().get("inflight", 0) == 0:
                break
            time.sleep(0.01)

        # 失败不会写入缓存，因此依旧为 None，且可再次触发 preload
        assert preloader.get("key") is None

        preloader.preload("key", loader)
        assert success_done.wait(timeout=2.0)

        deadline = time.time() + 2.0
        value = None
        while time.time() < deadline:
            value = preloader.get("key")
            if value is not None:
                break
            time.sleep(0.01)

        assert value == 456
        assert calls == 2
    finally:
        preloader.close()
