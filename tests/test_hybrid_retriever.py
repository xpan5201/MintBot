from __future__ import annotations

from src.agent.hybrid_retriever import HybridRetriever


class _Doc:
    def __init__(self, *, page_content: str, metadata: dict) -> None:
        self.page_content = page_content
        self.metadata = metadata


class _VectorStore:
    def __init__(self, results: list[tuple[_Doc, float]]) -> None:
        self._results = results

    def similarity_search_with_score(self, _query: str, *, k: int):  # noqa: ANN001
        return self._results[: int(k)]


def test_hybrid_retriever_bm25_all_zero_does_not_return_noise() -> None:
    vs = _VectorStore(results=[])
    docs = [
        {
            "id": "d1",
            "title": "T1",
            "content": "hello world",
            "category": "general",
            "keywords": ["hello"],
            "source": "manual",
        },
        {
            "id": "d2",
            "title": "T2",
            "content": "something else",
            "category": "general",
            "keywords": ["something"],
            "source": "manual",
        },
        {
            "id": "d3",
            "title": "T3",
            "content": "another doc",
            "category": "general",
            "keywords": ["another"],
            "source": "manual",
        },
    ]

    retriever = HybridRetriever(vectorstore=vs, documents=docs)
    assert retriever.search("qwertyuiop", k=5, alpha=0.6, threshold=0.0) == []


def test_hybrid_retriever_can_retrieve_by_bm25_without_metadata_shape() -> None:
    vs = _VectorStore(results=[])
    docs = [
        {
            "id": "d1",
            "title": "T1",
            "content": "hello world",
            "category": "general",
            "keywords": ["hello"],
            "source": "manual",
        },
        {
            "id": "d2",
            "title": "T2",
            "content": "something else",
            "category": "general",
            "keywords": ["something"],
            "source": "manual",
        },
        {
            "id": "d3",
            "title": "T3",
            "content": "another doc",
            "category": "general",
            "keywords": ["another"],
            "source": "manual",
        },
    ]

    retriever = HybridRetriever(vectorstore=vs, documents=docs)
    results = retriever.search("hello", k=5, alpha=0.6, threshold=0.0)
    assert results and results[0]["id"] == "d1"


def test_hybrid_retriever_combines_vector_and_bm25_scores() -> None:
    docs = [
        {
            "id": "d1",
            "title": "T1",
            "content": "hello world",
            "category": "general",
            "keywords": ["hello"],
            "source": "manual",
        },
        {
            "id": "d2",
            "title": "T2",
            "content": "something else",
            "category": "general",
            "keywords": ["something"],
            "source": "manual",
        },
        {
            "id": "d3",
            "title": "T3",
            "content": "another doc",
            "category": "general",
            "keywords": ["another"],
            "source": "manual",
        },
    ]
    vs = _VectorStore(
        results=[
            (
                _Doc(
                    page_content="【T1】\nhello world", metadata={"id": "d1", "category": "general"}
                ),
                0.2,
            ),
            (
                _Doc(
                    page_content="【T2】\nsomething else",
                    metadata={"id": "d2", "category": "general"},
                ),
                0.4,
            ),
        ]
    )

    retriever = HybridRetriever(vectorstore=vs, documents=docs)
    results = retriever.search("hello", k=2, alpha=0.6, threshold=0.0)
    assert results and results[0]["id"] == "d1"
    assert float(results[0].get("vector_score", 0.0) or 0.0) > 0.0
    assert float(results[0].get("bm25_score", 0.0) or 0.0) > 0.0


def test_hybrid_retriever_vector_results_merge_documents_metadata() -> None:
    docs = [
        {
            "id": "d1",
            "title": "T1",
            "content": "hello world",
            "category": "general",
            "keywords": ["hello"],
            "source": "manual",
            "usage_count": 5,
        },
        {
            "id": "d2",
            "title": "T2",
            "content": "something else",
            "category": "general",
            "keywords": ["something"],
            "source": "manual",
        },
        {
            "id": "d3",
            "title": "T3",
            "content": "another doc",
            "category": "general",
            "keywords": ["another"],
            "source": "manual",
        },
    ]
    vs = _VectorStore(
        results=[
            (
                _Doc(
                    page_content="【T1】\nhello world",
                    metadata={"id": "d1", "category": "general", "usage_count": 0},
                ),
                0.0,
            )
        ]
    )

    retriever = HybridRetriever(vectorstore=vs, documents=docs)
    results = retriever.search("hello", k=1, alpha=1.0, threshold=0.0)
    assert results and results[0]["metadata"].get("usage_count") == 5
