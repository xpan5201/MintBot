from __future__ import annotations

import time

from src.agent.memory import MemoryManager


def test_search_relevant_memories_time_query_uses_time_range() -> None:
    manager = MemoryManager.__new__(MemoryManager)
    manager.optimizer = None  # type: ignore[assignment]

    now_unix = time.time()
    calls: list[tuple[float, float, int]] = []

    class DummyLongTerm:
        write_version = 0

        def get_memories_time_range(
            self,
            *,
            start_unix: float,
            end_unix: float,
            limit: int = 20,
            batch_size: int = 500,
        ):
            calls.append((float(start_unix), float(end_unix), int(limit)))
            return [
                {
                    "content": "主人: 你在吗？\n小雪糕: 在的！",
                    "metadata": {
                        "timestamp_unix": now_unix - 10,
                        "importance": 0.5,
                        "content_hash": "h1",
                    },
                }
            ]

        def search_memories(self, *args, **kwargs):  # pragma: no cover
            raise AssertionError("time query should not require semantic search")

        def summarize_memory(self, content: str, max_length: int = 200) -> str:
            return content[:max_length]

    manager.long_term = DummyLongTerm()  # type: ignore[assignment]

    results = MemoryManager.search_relevant_memories(manager, "今天都聊了什么", k=2)
    assert calls
    assert any("小雪糕" in item for item in results)


def test_parse_time_query_range_hours_ago() -> None:
    manager = MemoryManager.__new__(MemoryManager)
    manager.optimizer = None  # type: ignore[assignment]

    calls: list[tuple[float, float]] = []

    class DummyLongTerm:
        write_version = 0

        def get_memories_time_range(
            self,
            *,
            start_unix: float,
            end_unix: float,
            limit: int = 20,
            batch_size: int = 500,
        ):
            calls.append((float(start_unix), float(end_unix)))
            return []

        def search_memories(self, query: str, k: int = 5, filter_dict=None):
            return []

        def summarize_memory(self, content: str, max_length: int = 200) -> str:
            return content[:max_length]

    manager.long_term = DummyLongTerm()  # type: ignore[assignment]

    MemoryManager.search_relevant_memories(manager, "1个小时之前我们聊了什么", k=2)
    assert calls
    start_unix, end_unix = calls[0]
    assert end_unix - start_unix >= 3600.0
