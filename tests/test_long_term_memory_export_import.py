from __future__ import annotations

from datetime import datetime
import time
from pathlib import Path

import pytest

import src.agent.memory as memory_mod


class _DummyDoc:
    def __init__(self, page_content: str, metadata: dict) -> None:
        self.page_content = page_content
        self.metadata = metadata


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


class _DummyVectorStore:
    def __init__(self) -> None:
        self._collection = _DummyCollection()

    def add_texts(self, *, texts, metadatas, ids=None):  # noqa: ANN001
        if ids is None:
            ids = [f"auto-{len(self._collection.items) + i}" for i in range(len(texts))]
        for doc_id, content, meta in zip(ids, texts, metadatas):
            self._collection.items.append((str(doc_id), str(content), dict(meta or {})))

    def similarity_search_with_score(self, *, query, k, filter=None):  # noqa: ANN001
        results = []
        for _, content, meta in self._collection.items:
            if filter:
                ok = True
                for key, value in dict(filter).items():
                    if meta.get(key) != value:
                        ok = False
                        break
                if not ok:
                    continue
            results.append((_DummyDoc(page_content=content, metadata=dict(meta)), 0.0))
            if len(results) >= int(k):
                break
        return results

    def delete_collection(self) -> None:
        self._collection.items.clear()


def _patch_dummy_chroma(monkeypatch: pytest.MonkeyPatch) -> list[_DummyVectorStore]:
    instances: list[_DummyVectorStore] = []

    def factory(**_kwargs):  # noqa: ANN001
        vs = _DummyVectorStore()
        instances.append(vs)
        return vs

    monkeypatch.setattr(memory_mod, "create_chroma_vectorstore", factory)
    monkeypatch.setattr(memory_mod, "get_collection_count", lambda vs: vs._collection.count())
    return instances


def test_long_term_add_memory_preserves_timestamp_and_sets_content_hash(
    monkeypatch, temp_dir: Path
):
    _patch_dummy_chroma(monkeypatch)
    lt = memory_mod.LongTermMemory(persist_directory=temp_dir / "lt", collection_name="t")

    lt.add_memory("Hello World", metadata={"timestamp": "2020-01-01T00:00:00"}, batch=False)

    exported = lt.export_records(batch_size=10)
    assert exported["count"] == 1
    item = exported["items"][0]
    assert item["metadata"]["timestamp"] == "2020-01-01T00:00:00"
    assert item["metadata"]["timestamp_unix"] == pytest.approx(
        datetime.fromisoformat("2020-01-01T00:00:00").timestamp()
    )
    assert item["metadata"]["content_hash"]


def test_long_term_add_memory_parses_z_timestamp(monkeypatch, temp_dir: Path):
    _patch_dummy_chroma(monkeypatch)
    lt = memory_mod.LongTermMemory(persist_directory=temp_dir / "lt", collection_name="t")

    lt.add_memory("Hello Z", metadata={"timestamp": "2020-01-01T00:00:00Z"}, batch=False)

    exported = lt.export_records(batch_size=10)
    assert exported["count"] == 1
    item = exported["items"][0]
    assert item["metadata"]["timestamp"] == "2020-01-01T00:00:00Z"
    assert item["metadata"]["timestamp_unix"] == pytest.approx(
        datetime.fromisoformat("2020-01-01T00:00:00+00:00").timestamp()
    )


def test_long_term_export_import_roundtrip(monkeypatch, temp_dir: Path):
    _patch_dummy_chroma(monkeypatch)
    lt = memory_mod.LongTermMemory(persist_directory=temp_dir / "lt", collection_name="t")

    lt.add_memory("A", metadata={"type": "conversation"}, batch=False)
    lt.add_memory("B", metadata={"type": "conversation"}, batch=False)

    exported = lt.export_records(batch_size=1)
    assert exported["count"] == 2
    assert len(exported["items"]) == 2

    lt2 = memory_mod.LongTermMemory(persist_directory=temp_dir / "lt2", collection_name="t2")
    imported = lt2.import_records(exported["items"], overwrite=False, batch_size=1)
    assert imported == 2
    assert lt2.export_records()["count"] == 2

    # overwrite=False 时应保留原 id 到 metadata.original_id
    _, _, meta0 = lt2.vectorstore._collection.items[0]
    assert meta0.get("original_id")
    assert meta0.get("content_hash")
    assert meta0.get("timestamp_unix") is not None


def test_long_term_batch_flush_by_time(monkeypatch, temp_dir: Path):
    _patch_dummy_chroma(monkeypatch)
    lt = memory_mod.LongTermMemory(persist_directory=temp_dir / "lt", collection_name="t")

    lt._batch_size = 10_000  # 禁止按条数触发
    lt._batch_flush_interval_s = 0.1
    lt._last_batch_flush_mono = time.monotonic() - 999

    assert lt.add_memory("timed flush", metadata={"type": "conversation"}, batch=True) is True
    assert lt.export_records()["count"] == 1
    assert len(lt._batch_buffer) == 0


def test_memory_manager_get_export_data_includes_long_term(monkeypatch, temp_dir: Path):
    _patch_dummy_chroma(monkeypatch)
    lt = memory_mod.LongTermMemory(persist_directory=temp_dir / "lt", collection_name="t")
    lt.add_memory("memory", metadata={"type": "conversation"}, batch=False)

    mgr = memory_mod.MemoryManager(enable_long_term=False, enable_optimizer=False)
    mgr.long_term = lt
    data = mgr.get_export_data(include_long_term=True, include_optimizer_stats=False)
    assert "short_term" in data
    assert "long_term" in data
    assert data["long_term"]["count"] == 1


def test_long_term_flush_batch_persists_buffer(monkeypatch, temp_dir: Path):
    _patch_dummy_chroma(monkeypatch)
    lt = memory_mod.LongTermMemory(persist_directory=temp_dir / "lt", collection_name="t")

    lt._batch_size = 10_000
    lt._batch_flush_interval_s = 10_000
    lt._last_batch_flush_mono = time.monotonic()

    assert lt.add_memory("buffered", metadata={"type": "conversation"}, batch=True) is True
    assert len(lt._batch_buffer) == 1
    assert lt._batch_buffer[0]["metadata"].get("timestamp_unix") is not None

    before_version = lt.write_version
    flushed = lt.flush_batch()
    assert flushed == 1
    assert len(lt._batch_buffer) == 0
    assert lt.export_records()["count"] == 1
    assert lt.write_version > before_version


def test_long_term_clear_drops_batch_buffer(monkeypatch, temp_dir: Path):
    _patch_dummy_chroma(monkeypatch)
    lt = memory_mod.LongTermMemory(persist_directory=temp_dir / "lt", collection_name="t")

    lt._batch_size = 10_000
    lt._batch_flush_interval_s = 10_000
    lt._last_batch_flush_mono = time.monotonic()

    assert lt.add_memory("buffered", metadata={"type": "conversation"}, batch=True) is True
    assert len(lt._batch_buffer) == 1

    lt.clear()
    assert len(lt._batch_buffer) == 0
    assert lt.flush_batch() == 0
    assert lt.export_records()["count"] == 0


def test_search_memories_prefers_timestamp_unix_over_invalid_timestamp(monkeypatch, temp_dir: Path):
    _patch_dummy_chroma(monkeypatch)
    lt = memory_mod.LongTermMemory(persist_directory=temp_dir / "lt", collection_name="t")

    old_unix = time.time() - 400 * 86400
    lt.add_memory(
        "Old memory",
        metadata={"timestamp": "not-a-timestamp", "timestamp_unix": old_unix},
        batch=False,
    )

    results = lt.search_memories("query", k=1)
    assert results
    assert results[0]["recency_score"] == pytest.approx(0.5)


def test_search_memories_rerank_uses_character_consistency(monkeypatch, temp_dir: Path):
    _patch_dummy_chroma(monkeypatch)
    lt = memory_mod.LongTermMemory(persist_directory=temp_dir / "lt", collection_name="t")

    # 让角色一致性对 rerank 有明显影响，避免只依赖插入顺序
    monkeypatch.setattr(
        memory_mod.settings.agent, "memory_character_consistency_weight", 1.0, raising=False
    )

    scorer_version = 2
    if getattr(memory_mod, "CharacterConsistencyScorer", None) is not None:
        scorer_version = int(getattr(memory_mod.CharacterConsistencyScorer, "SCORER_VERSION", 2))

    meta = {
        "type": "conversation",
        "importance": 0.5,
        "timestamp": "2020-01-01T00:00:00",
        "character_consistency_version": scorer_version,
    }

    lt.add_memory(
        "主人: 你好\n小雪糕: 好的",
        metadata={**meta, "character_consistency": 0.1},
        batch=False,
    )
    lt.add_memory(
        "主人: 你好\n小雪糕: 主人我在喵~",
        metadata={**meta, "character_consistency": 0.9},
        batch=False,
    )

    results = lt.search_memories("query", k=2)
    assert len(results) == 2
    assert results[0]["character_consistency"] == pytest.approx(0.9)
