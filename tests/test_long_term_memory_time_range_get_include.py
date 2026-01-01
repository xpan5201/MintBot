from __future__ import annotations

import time
from threading import Lock

from src.agent.memory import LongTermMemory


def test_get_memories_time_range_does_not_include_ids() -> None:
    now = time.time()

    class DummyCollection:
        def count(self) -> int:
            return 1

        def get(self, *, include=None, limit=None, offset=None, where=None, where_document=None):
            assert include is not None
            assert "ids" not in include
            if where is not None:
                raise RuntimeError("where not supported in dummy")
            return {
                "ids": ["id1"],
                "documents": ["u: hi\na: hello"],
                "metadatas": [{"timestamp_unix": now, "importance": 0.5}],
            }

    class DummyVectorStore:
        _collection = DummyCollection()

    lt = LongTermMemory.__new__(LongTermMemory)
    lt.vectorstore = DummyVectorStore()  # type: ignore[assignment]
    lt._vectorstore_lock = Lock()  # type: ignore[assignment]

    results = lt.get_memories_time_range(
        start_unix=now - 60,
        end_unix=now + 60,
        limit=5,
        batch_size=10,
    )
    assert results
