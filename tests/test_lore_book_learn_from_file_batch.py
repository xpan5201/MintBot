"""
LoreBook 从文件学习 - 性能回归测试

覆盖两类问题：
1) 文件内容读取的编码回退（避免只支持 utf-8 导致读取失败）
2) learn_from_file 的批量写入逻辑（避免逐条 add_texts 带来的性能瓶颈）
"""

from threading import Lock


def test_lorebook_read_file_content_gbk_decoding(temp_dir):
    from src.agent.advanced_memory import LoreBook

    lore_book = LoreBook.__new__(LoreBook)
    path = temp_dir / "gbk.txt"
    path.write_bytes("中文".encode("gbk"))

    content = lore_book._read_file_content(str(path), "txt")
    assert content is not None
    assert "中文" in content


def test_lorebook_learn_from_file_batches_vectorstore_add():
    from src.agent.advanced_memory import LoreBook

    class DummyVectorStore:
        def __init__(self):
            self.calls = []

        def add_texts(self, *, texts, metadatas, ids):
            self.calls.append((texts, metadatas, ids))

    lore_book = LoreBook.__new__(LoreBook)
    lore_book.vectorstore = DummyVectorStore()
    lore_book._lock = Lock()

    lore_book._read_file_content = lambda filepath, file_type=None: "a\n\nb\n\nc"
    lore_book._split_content_into_chunks = lambda content, chunk_size, overlap=100: ["chunk1", "chunk2"]
    lore_book._extract_title_from_chunk = lambda chunk, idx: f"title{idx}"
    lore_book._extract_category_from_content = lambda chunk: "general"
    lore_book._extract_keywords_from_content = lambda chunk: ["k1"]
    lore_book._invalidate_cache = lambda: None

    def _create_lore_metadata(lore_id, title, category, keywords, source):
        return {
            "id": lore_id,
            "title": title,
            "category": category,
            "keywords": ",".join(keywords or []),
            "source": source,
            "timestamp": "t",
            "update_count": 0,
            "usage_count": 0,
            "positive_feedback": 0,
            "negative_feedback": 0,
        }

    lore_book._create_lore_metadata = _create_lore_metadata
    lore_book._read_json_records_unlocked = lambda: []
    lore_book._write_json_records_unlocked = lambda data: None
    lore_book._save_to_json = lambda record: None

    learned_ids = lore_book.learn_from_file("dummy.txt", file_type="txt", chunk_size=10)
    assert len(learned_ids) == 2
    assert len(lore_book.vectorstore.calls) == 1
    texts, metadatas, ids = lore_book.vectorstore.calls[0]
    assert ids == learned_ids
    assert len(texts) == 2
    assert len(metadatas) == 2
