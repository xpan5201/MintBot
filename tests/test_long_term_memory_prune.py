from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

import src.agent.memory as memory_mod


class _DummyCollection:
    def __init__(self) -> None:
        self.items: list[tuple[str, str, dict]] = []

    def count(self) -> int:
        return len(self.items)

    def get(self, *, include=None, limit=None, offset=None):  # noqa: ANN001
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
        to_delete = {str(x) for x in ids or []}
        self.items = [item for item in self.items if item[0] not in to_delete]


class _DummyVectorStore:
    def __init__(self) -> None:
        self._collection = _DummyCollection()

    def add_texts(self, *, texts, metadatas, ids=None):  # noqa: ANN001
        if ids is None:
            ids = [f"auto-{len(self._collection.items) + i}" for i in range(len(texts))]
        for doc_id, content, meta in zip(ids, texts, metadatas):
            self._collection.items.append((str(doc_id), str(content), dict(meta or {})))

    def delete_collection(self) -> None:
        self._collection.items.clear()


def _patch_dummy_chroma(monkeypatch: pytest.MonkeyPatch) -> None:
    def factory(**_kwargs):  # noqa: ANN001
        return _DummyVectorStore()

    monkeypatch.setattr(memory_mod, "create_chroma_vectorstore", factory)
    monkeypatch.setattr(memory_mod, "get_collection_count", lambda vs: vs._collection.count())


def test_long_term_prune_by_age_respects_protected_importance(monkeypatch, temp_dir: Path):
    _patch_dummy_chroma(monkeypatch)
    lt = memory_mod.LongTermMemory(persist_directory=temp_dir / "lt", collection_name="t")

    now_iso = datetime.now().isoformat()
    lt.add_memory("old-low", metadata={"timestamp": "2000-01-01T00:00:00", "importance": 0.2}, batch=False)
    lt.add_memory("old-high", metadata={"timestamp": "2000-01-01T00:00:00", "importance": 0.95}, batch=False)
    lt.add_memory("new-low", metadata={"timestamp": now_iso, "importance": 0.2}, batch=False)

    dry = lt.prune(max_age_days=30, preserve_importance_above=0.9, dry_run=True)
    assert dry["total_before"] == 3
    assert dry["protected"] == 1
    assert dry["would_delete"] == 1
    assert lt.export_records()["count"] == 3

    applied = lt.prune(max_age_days=30, preserve_importance_above=0.9, dry_run=False)
    assert applied["deleted"] == 1
    assert lt.export_records()["count"] == 2


def test_long_term_prune_by_count_keeps_protected(monkeypatch, temp_dir: Path):
    _patch_dummy_chroma(monkeypatch)
    lt = memory_mod.LongTermMemory(persist_directory=temp_dir / "lt", collection_name="t")

    # 1 protected + 3 unprotected
    lt.add_memory("protected", metadata={"timestamp": "2000-01-01T00:00:00", "importance": 0.95}, batch=False)
    lt.add_memory("u1", metadata={"timestamp": "2000-01-01T00:00:00", "importance": 0.8}, batch=False)
    lt.add_memory("u2", metadata={"timestamp": "2020-01-01T00:00:00", "importance": 0.7}, batch=False)
    lt.add_memory("u3", metadata={"timestamp": "2024-01-01T00:00:00", "importance": 0.1}, batch=False)

    # max_items=2 => 保留 protected + 最佳 unprotected (u1: importance 0.8)
    applied = lt.prune(max_items=2, preserve_importance_above=0.9, dry_run=False)
    assert applied["deleted"] == 2
    exported = lt.export_records(batch_size=10)
    contents = [item["content"] for item in exported["items"]]
    assert "protected" in contents
    assert "u1" in contents
    assert len(contents) == 2


def test_long_term_prune_handles_timezone_aware_timestamp(monkeypatch, temp_dir: Path):
    _patch_dummy_chroma(monkeypatch)
    lt = memory_mod.LongTermMemory(persist_directory=temp_dir / "lt", collection_name="t")

    lt.add_memory(
        "old-low",
        metadata={"timestamp": "2000-01-01T00:00:00+00:00", "importance": 0.2},
        batch=False,
    )
    lt.add_memory(
        "old-high",
        metadata={"timestamp": "2000-01-01T00:00:00+00:00", "importance": 0.95},
        batch=False,
    )
    lt.add_memory(
        "new-low",
        metadata={"timestamp": datetime.now().isoformat(), "importance": 0.2},
        batch=False,
    )

    applied = lt.prune(max_age_days=30, preserve_importance_above=0.9, dry_run=False)
    assert applied["deleted"] == 1
    exported = lt.export_records(batch_size=10)
    contents = [item["content"] for item in exported["items"]]
    assert "old-low" not in contents
    assert "old-high" in contents
    assert "new-low" in contents


def test_long_term_prune_does_not_require_export_records(monkeypatch, temp_dir: Path):
    _patch_dummy_chroma(monkeypatch)
    lt = memory_mod.LongTermMemory(persist_directory=temp_dir / "lt", collection_name="t")

    lt.add_memory("old-low", metadata={"timestamp": "2000-01-01T00:00:00", "importance": 0.2}, batch=False)
    lt.add_memory("old-high", metadata={"timestamp": "2000-01-01T00:00:00", "importance": 0.95}, batch=False)

    def should_not_be_called(*_args, **_kwargs):  # noqa: ANN001
        raise AssertionError("prune should not call export_records()")

    monkeypatch.setattr(lt, "export_records", should_not_be_called)
    applied = lt.prune(max_age_days=30, preserve_importance_above=0.9, dry_run=False)
    assert applied["deleted"] == 1
