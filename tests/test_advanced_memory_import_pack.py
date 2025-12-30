from __future__ import annotations

import json
from pathlib import Path

import pytest

import src.agent.advanced_memory as adv


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
        to_delete = {str(x) for x in (ids or [])}
        self.items = [item for item in self.items if item[0] not in to_delete]


class _DummyVectorStore:
    def __init__(self) -> None:
        self._collection = _DummyCollection()

    def add_texts(self, *, texts, metadatas, ids=None):  # noqa: ANN001
        if ids is None:
            ids = [f"auto-{len(self._collection.items) + i}" for i in range(len(texts))]
        for doc_id, content, meta in zip(ids, texts, metadatas):
            self._collection.items.append((str(doc_id), str(content), dict(meta or {})))

    def get(self, **_kwargs):  # noqa: ANN001
        return self._collection.get()

    def delete_collection(self) -> None:
        self._collection.items.clear()

    def delete(self, *, ids):  # noqa: ANN001
        self._collection.delete(ids=ids)


def _patch_dummy_chroma(monkeypatch: pytest.MonkeyPatch) -> list[_DummyVectorStore]:
    instances: list[_DummyVectorStore] = []

    def factory(**_kwargs):  # noqa: ANN001
        vs = _DummyVectorStore()
        instances.append(vs)
        return vs

    monkeypatch.setattr(adv, "create_chroma_vectorstore", factory)
    monkeypatch.setattr(adv, "get_collection_count", lambda vs: vs._collection.count())
    return instances


def test_core_memory_import_records_overwrite_preserves_ids(monkeypatch, temp_dir: Path):
    _patch_dummy_chroma(monkeypatch)
    monkeypatch.setattr(adv.settings.agent, "is_core_mem", True, raising=False)

    core = adv.CoreMemory(persist_directory=str(temp_dir / "core"), user_id=1)
    assert core.vectorstore is not None

    imported = core.import_records(
        [
            {
                "id": "c1",
                "content": "hello",
                "metadata": {"category": "general", "importance": 1.0},
            },
            {
                "id": "c2",
                "content": "world",
                "metadata": {"category": "general", "importance": 0.9},
            },
        ],
        overwrite=True,
        batch_size=10,
    )
    assert imported == 2
    ids = [doc_id for doc_id, _, _ in core.vectorstore._collection.items]
    assert ids == ["c1", "c2"]


def test_diary_import_entries_rebuilds_vectorstore(monkeypatch, temp_dir: Path):
    _patch_dummy_chroma(monkeypatch)
    monkeypatch.setattr(adv.settings.agent, "long_memory", True, raising=False)

    diary = adv.DiaryMemory(persist_directory=str(temp_dir / "diary"), user_id=1)
    assert diary.vectorstore is not None
    assert diary.diary_file is not None

    imported = diary.import_entries(
        [{"content": "today", "timestamp": "2020-01-01T00:00:00", "emotion": "happy"}],
        overwrite=True,
        batch_size=10,
    )
    assert imported == 1
    data = json.loads(Path(diary.diary_file).read_text(encoding="utf-8"))
    assert isinstance(data, list) and len(data) == 1
    assert diary.vectorstore._collection.count() == 1


def test_lore_book_import_records_preserves_ids_and_json(monkeypatch, temp_dir: Path):
    _patch_dummy_chroma(monkeypatch)
    monkeypatch.setattr(adv.settings.agent, "lore_books", True, raising=False)

    lore = adv.LoreBook(persist_directory=str(temp_dir / "lore"), user_id=1)
    assert lore.vectorstore is not None
    assert lore.json_file is not None

    imported = lore.import_records(
        [
            {
                "id": "l1",
                "title": "T",
                "content": "C",
                "category": "general",
                "keywords": ["k"],
                "source": "import",
                "timestamp": "2020-01-01T00:00:00",
                "usage_count": 3,
            }
        ],
        overwrite=True,
        batch_size=10,
    )
    assert imported == 1
    json_data = json.loads(Path(lore.json_file).read_text(encoding="utf-8"))
    assert isinstance(json_data, list) and json_data and json_data[0]["id"] == "l1"
    ids = [doc_id for doc_id, _, _ in lore.vectorstore._collection.items]
    assert ids == ["l1"]
