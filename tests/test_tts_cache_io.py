from __future__ import annotations

import asyncio
import threading

from src.multimodal.tts_cache import PersistentTTSAudioCache
from src.multimodal.tts_manager import TTSConfig, TTSManager


def test_disk_cache_get_does_not_write_index_on_hit(tmp_path) -> None:
    cache = PersistentTTSAudioCache(
        root_dir=tmp_path,
        max_entries=10,
        compress=False,
    )
    cache.set("k", b"HELLO")

    calls = 0
    original_save_index = cache._save_index  # type: ignore[attr-defined]

    def _wrapped_save_index() -> None:
        nonlocal calls
        calls += 1
        original_save_index()

    cache._save_index = _wrapped_save_index  # type: ignore[attr-defined]

    assert cache.get("k") == b"HELLO"
    assert cache.get("k") == b"HELLO"
    assert calls == 0


async def _run_disk_cache_get_uses_executor() -> None:
    manager = TTSManager(
        TTSConfig(
            api_url="http://127.0.0.1:9880/tts",
            disk_cache_enabled=False,
        )
    )

    main_thread = threading.current_thread()
    called_thread: threading.Thread | None = None

    class _DummyDiskCache:
        def get(self, _key: str):
            nonlocal called_thread
            called_thread = threading.current_thread()
            return b"CACHED"

    manager._disk_cache = _DummyDiskCache()  # type: ignore[attr-defined]

    result = await manager._get_from_cache("cache-key")  # type: ignore[attr-defined]
    assert result == b"CACHED"
    assert called_thread is not None
    assert called_thread.ident is not None and main_thread.ident is not None
    assert called_thread.ident != main_thread.ident


def test_ttsmanager_disk_cache_get_runs_in_executor() -> None:
    asyncio.run(_run_disk_cache_get_uses_executor())


async def _run_disk_cache_clear_uses_executor() -> None:
    manager = TTSManager(
        TTSConfig(
            api_url="http://127.0.0.1:9880/tts",
            disk_cache_enabled=False,
        )
    )

    main_thread = threading.current_thread()
    called_thread: threading.Thread | None = None

    class _DummyDiskCache:
        def clear(self) -> None:
            nonlocal called_thread
            called_thread = threading.current_thread()

    manager._disk_cache = _DummyDiskCache()  # type: ignore[attr-defined]

    await manager.clear_cache()
    assert called_thread is not None
    assert called_thread.ident is not None and main_thread.ident is not None
    assert called_thread.ident != main_thread.ident


def test_ttsmanager_disk_cache_clear_runs_in_executor() -> None:
    asyncio.run(_run_disk_cache_clear_uses_executor())


def test_ttsmanager_get_stats_includes_client_compat_fields() -> None:
    manager = TTSManager(
        TTSConfig(
            api_url="http://127.0.0.1:9880/tts",
            disk_cache_enabled=False,
        )
    )

    class _DummyClient:
        def get_stats(self):  # noqa: ANN001
            return {
                "total_requests": 10,
                "successful_requests": 7,
                "failed_requests": 3,
                "total_retries": 5,
            }

    manager.client = _DummyClient()  # type: ignore[assignment]

    stats = manager.get_stats()
    assert stats["client_stats"]["total_requests"] == 10
    assert stats["total_requests"] == 10
    assert stats["successful_requests"] == 7
    assert stats["failed_requests"] == 3
    assert stats["retry_count"] == 5
