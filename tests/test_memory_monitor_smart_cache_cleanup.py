from __future__ import annotations


def test_memory_monitor_cleanup_callback_cleans_smart_cache(monkeypatch) -> None:
    from src.utils import memory_monitor
    from src.utils.cache_manager import cache_manager

    memory_monitor._memory_monitor = None
    monitor = memory_monitor.get_memory_monitor()
    monitor._cleanup_callbacks.clear()

    called: dict[str, int] = {"smart": 0}

    def fake_smart_cleanup_all() -> int:
        called["smart"] += 1
        return 3

    monkeypatch.setattr(cache_manager, "cleanup_all", fake_smart_cleanup_all)

    class _DummyEnhancedManager:
        def cleanup_all(self) -> dict[str, int]:
            return {"enhanced": 0}

    monkeypatch.setattr(
        "src.utils.enhanced_cache.get_cache_manager", lambda: _DummyEnhancedManager()
    )
    monkeypatch.setattr(memory_monitor.MemoryMonitor, "start_monitoring", lambda self, **_: None)

    memory_monitor.setup_memory_monitoring(auto_cleanup=True)
    monitor.trigger_cleanup("test")
    assert called["smart"] == 1
