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
    class DummyOpenAIEmbeddings:
        instances = 0

        def __init__(self, **kwargs):
            DummyOpenAIEmbeddings.instances += 1
            self.kwargs = kwargs

    monkeypatch.setattr(chroma_helper, "OpenAIEmbeddings", DummyOpenAIEmbeddings)
    chroma_helper._get_openai_embedding_function.cache_clear()

    emb = chroma_helper._get_openai_embedding_function("model-x", "", "key")
    emb2 = chroma_helper._get_openai_embedding_function("model-x", "", "key")
    assert emb is emb2
    assert DummyOpenAIEmbeddings.instances == 1
    assert emb.kwargs == {"model": "model-x", "api_key": "key"}

    emb3 = chroma_helper._get_openai_embedding_function("model-x", "https://gw.example/v1", "key")
    assert emb3.kwargs["base_url"] == "https://gw.example/v1"
