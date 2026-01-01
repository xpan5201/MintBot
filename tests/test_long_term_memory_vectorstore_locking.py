from __future__ import annotations

from pathlib import Path

import pytest

import src.agent.memory as memory_mod


class _RecordingLock:
    def __init__(self) -> None:
        self.held = False
        self.enter_count = 0

    def __enter__(self):  # noqa: ANN204
        assert not self.held, "vectorstore lock must not be re-entered"
        self.held = True
        self.enter_count += 1
        return self

    def __exit__(self, exc_type, exc, tb):  # noqa: ANN001,ANN201
        self.held = False
        return False


class _AssertingCollection:
    def __init__(self) -> None:
        self.items: list[tuple[str, str, dict]] = []
        self.lock: _RecordingLock | None = None
        self.count_calls = 0
        self.get_calls = 0
        self.delete_calls = 0

    def _assert_lock_held(self) -> None:
        if self.lock is None:
            return
        assert self.lock.held is True

    def count(self) -> int:
        self._assert_lock_held()
        self.count_calls += 1
        return len(self.items)

    def get(self, *, include=None, limit=None, offset=None):  # noqa: ANN001
        self._assert_lock_held()
        self.get_calls += 1
        start = int(offset or 0)
        if limit is None:
            subset = self.items[start:]
        else:
            subset = self.items[start : start + int(limit)]
        return {
            "ids": [doc_id for doc_id, _, _ in subset],
            "documents": [content for _, content, _ in subset],
            "metadatas": [meta for _, _, meta in subset],
        }

    def delete(self, *, ids):  # noqa: ANN001
        self._assert_lock_held()
        self.delete_calls += 1
        to_delete = {str(x) for x in ids or []}
        self.items = [item for item in self.items if item[0] not in to_delete]


class _DummyVectorStore:
    def __init__(self) -> None:
        self._collection = _AssertingCollection()

    def add_texts(self, *, texts, metadatas, ids=None):  # noqa: ANN001
        if ids is None:
            ids = [f"auto-{len(self._collection.items) + i}" for i in range(len(texts))]
        for doc_id, content, meta in zip(ids, texts, metadatas):
            self._collection.items.append((str(doc_id), str(content), dict(meta or {})))

    def delete_collection(self) -> None:
        self._collection.items.clear()


def _make_long_term(
    monkeypatch: pytest.MonkeyPatch, temp_dir: Path
) -> tuple[memory_mod.LongTermMemory, _RecordingLock]:
    def factory(**_kwargs):  # noqa: ANN001
        return _DummyVectorStore()

    monkeypatch.setattr(memory_mod, "create_chroma_vectorstore", factory)
    monkeypatch.setattr(memory_mod, "get_collection_count", lambda vs: vs._collection.count())

    lt = memory_mod.LongTermMemory(persist_directory=temp_dir / "lt", collection_name="t")
    lock = _RecordingLock()
    lt._vectorstore_lock = lock
    lt.vectorstore._collection.lock = lock  # type: ignore[union-attr]
    lt.vectorstore._collection.count_calls = 0
    lt.vectorstore._collection.get_calls = 0
    lt.vectorstore._collection.delete_calls = 0
    lock.enter_count = 0
    return lt, lock


def test_export_records_holds_vectorstore_lock(monkeypatch, temp_dir: Path) -> None:
    lt, lock = _make_long_term(monkeypatch, temp_dir)
    lt.add_memory("hello", metadata={"type": "conversation"}, batch=False)

    exported = lt.export_records(batch_size=1)
    assert exported["count"] == 1
    assert lt.vectorstore._collection.count_calls >= 1  # type: ignore[union-attr]
    assert lt.vectorstore._collection.get_calls >= 1  # type: ignore[union-attr]
    assert lock.enter_count >= 2  # count + get


def test_prune_holds_vectorstore_lock(monkeypatch, temp_dir: Path) -> None:
    lt, lock = _make_long_term(monkeypatch, temp_dir)
    lt.add_memory(
        "old-low", metadata={"timestamp": "2000-01-01T00:00:00", "importance": 0.2}, batch=False
    )
    lt.add_memory(
        "old-high", metadata={"timestamp": "2000-01-01T00:00:00", "importance": 0.95}, batch=False
    )

    result = lt.prune(max_age_days=30, preserve_importance_above=0.9, dry_run=False, batch_size=10)
    assert result["deleted"] == 1
    assert lt.vectorstore._collection.count_calls >= 1  # type: ignore[union-attr]
    assert lt.vectorstore._collection.get_calls >= 1  # type: ignore[union-attr]
    assert lt.vectorstore._collection.delete_calls >= 1  # type: ignore[union-attr]
    assert lock.enter_count >= 3  # count + get + delete


def test_get_memory_count_holds_vectorstore_lock(monkeypatch, temp_dir: Path) -> None:
    lt, lock = _make_long_term(monkeypatch, temp_dir)
    lt.add_memory("one", metadata={"type": "conversation"}, batch=False)

    lt.vectorstore._collection.count_calls = 0  # type: ignore[union-attr]
    lock.enter_count = 0
    assert lt.get_memory_count() == 1
    assert lt.vectorstore._collection.count_calls == 1  # type: ignore[union-attr]
    assert lock.enter_count == 1


def test_memory_manager_stats_uses_long_term_get_memory_count(monkeypatch, temp_dir: Path) -> None:
    lt, lock = _make_long_term(monkeypatch, temp_dir)
    lt.add_memory("one", metadata={"type": "conversation"}, batch=False)

    lt.vectorstore._collection.count_calls = 0  # type: ignore[union-attr]
    lock.enter_count = 0

    mgr = memory_mod.MemoryManager(enable_long_term=False, enable_optimizer=False)
    mgr.long_term = lt
    stats = mgr.get_memory_stats()
    assert stats["long_term_count"] == 1
    assert lt.vectorstore._collection.count_calls == 1  # type: ignore[union-attr]
    assert lock.enter_count == 1
