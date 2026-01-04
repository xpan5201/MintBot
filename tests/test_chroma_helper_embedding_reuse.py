import src.utils.chroma_helper as chroma_helper


def test_local_embedding_function_is_cached(monkeypatch):
    class DummyLocalEmbeddings:
        instances = 0

        def __init__(self, *, model_name, cache_dir, device, enable_cache):
            DummyLocalEmbeddings.instances += 1
            self.model_name = model_name
            self.cache_dir = cache_dir
            self.device = device
            self.enable_cache = enable_cache

    monkeypatch.setattr(chroma_helper, "SENTENCE_TRANSFORMERS_AVAILABLE", True)
    monkeypatch.setattr(chroma_helper, "LocalEmbeddings", DummyLocalEmbeddings)
    chroma_helper._get_local_embedding_function.cache_clear()

    first = chroma_helper._get_local_embedding_function("m1", True)
    second = chroma_helper._get_local_embedding_function("m1", True)
    assert first is second
    assert DummyLocalEmbeddings.instances == 1

    third = chroma_helper._get_local_embedding_function("m1", False)
    assert third is not first
    assert DummyLocalEmbeddings.instances == 2


def test_openai_embedding_function_is_cached_and_base_url_logic(monkeypatch):
    class DummyOpenAIEmbeddingClient:
        instances = 0

        def __init__(self, *, model, api_key, base_url=None, enable_cache=True):  # noqa: ANN001
            DummyOpenAIEmbeddingClient.instances += 1
            self.kwargs = {"model": model, "api_key": api_key, "enable_cache": enable_cache}
            if base_url:
                self.kwargs["base_url"] = base_url

    monkeypatch.setattr(chroma_helper, "OpenAIEmbeddingClient", DummyOpenAIEmbeddingClient)
    chroma_helper._get_openai_embedding_function.cache_clear()

    emb = chroma_helper._get_openai_embedding_function("model-x", "", "key", True)
    emb2 = chroma_helper._get_openai_embedding_function("model-x", "", "key", True)
    assert emb is emb2
    assert DummyOpenAIEmbeddingClient.instances == 1
    assert emb.kwargs == {"model": "model-x", "api_key": "key", "enable_cache": True}

    emb_no_cache = chroma_helper._get_openai_embedding_function("model-x", "", "key", False)
    assert emb_no_cache is not emb
    assert DummyOpenAIEmbeddingClient.instances == 2
    assert emb_no_cache.kwargs["enable_cache"] is False

    emb3 = chroma_helper._get_openai_embedding_function(
        "model-x", "https://gw.example/v1", "key", True
    )
    assert emb3.kwargs["base_url"] == "https://gw.example/v1"

    emb4 = chroma_helper._get_openai_embedding_function(
        "model-x", "https://gw.example", "key", True
    )
    assert emb4.kwargs["base_url"] == "https://gw.example/v1"

    emb5 = chroma_helper._get_openai_embedding_function(
        "model-x", "https://api.openai.com/v1", "key", True
    )
    assert emb5.kwargs["base_url"] == "https://api.openai.com/v1"


def test_openai_embedding_client_reuses_cached_vectors(monkeypatch):
    class DummyEmbeddingItem:
        def __init__(self, index, embedding):  # noqa: ANN001
            self.index = index
            self.embedding = embedding

    class DummyEmbeddingResponse:
        def __init__(self, data):  # noqa: ANN001
            self.data = data

    class DummyEmbeddingsApi:
        def __init__(self):
            self.calls = 0
            self.last_inputs = None

        def create(self, *, model, input):  # noqa: ANN001, A002
            self.calls += 1
            self.last_inputs = (model, list(input))
            items = [
                DummyEmbeddingItem(i, [float(i)]) for i in reversed(range(len(input)))
            ]  # out-of-order on purpose
            return DummyEmbeddingResponse(items)

    class DummyOpenAI:
        def __init__(self, **kwargs):  # noqa: ANN003
            self.kwargs = kwargs
            self.embeddings = DummyEmbeddingsApi()

    monkeypatch.setattr(chroma_helper, "OpenAI", DummyOpenAI)

    client = chroma_helper.OpenAIEmbeddingClient(model="m", api_key="k", enable_cache=True)
    vectors = client.embed_documents(["a", "b", "a"])
    assert vectors == [[0.0], [1.0], [0.0]]
    assert client._client.embeddings.calls == 1
    assert client._client.embeddings.last_inputs == ("m", ["a", "b"])

    vectors2 = client.embed_documents(["a"])
    assert vectors2 == [[0.0]]
    assert client._client.embeddings.calls == 1


def test_similarity_search_with_score_fails_open_on_errors():
    import threading

    store = chroma_helper.ChromaVectorStore.__new__(chroma_helper.ChromaVectorStore)

    class DummyEmbedding:
        def embed_documents(self, texts):  # noqa: ANN001
            return [[0.0] for _ in texts]

        def embed_query(self, text):  # noqa: ANN001
            raise RuntimeError("boom")

    store._embedding_function = DummyEmbedding()
    store._lock = threading.RLock()
    store._collection = object()

    assert store.similarity_search_with_score("q") == []

    class DummyEmbedding2(DummyEmbedding):
        def embed_query(self, text):  # noqa: ANN001
            return [0.0]

    class DummyCollection:
        def query(self, **kwargs):  # noqa: ANN003
            raise RuntimeError("db locked")

    store2 = chroma_helper.ChromaVectorStore.__new__(chroma_helper.ChromaVectorStore)
    store2._embedding_function = DummyEmbedding2()
    store2._lock = threading.RLock()
    store2._collection = DummyCollection()

    assert store2.similarity_search_with_score("q") == []
