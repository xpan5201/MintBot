from __future__ import annotations

from src.llm import factory
from src.llm.factory import _normalize_openai_base_url


def test_normalize_openai_base_url_appends_v1_for_bare_host() -> None:
    assert _normalize_openai_base_url("https://api.example.com") == "https://api.example.com/v1"
    assert _normalize_openai_base_url("https://api.example.com/") == "https://api.example.com/v1"


def test_normalize_openai_base_url_keeps_existing_path() -> None:
    assert _normalize_openai_base_url("https://gw.example/v1") == "https://gw.example/v1"
    assert (
        _normalize_openai_base_url("https://openrouter.ai/api/v1") == "https://openrouter.ai/api/v1"
    )


def test_build_openai_backend_uses_normalized_base_url_in_cache_key() -> None:
    factory.reset_llm_cache()

    backend_a = factory._build_openai_backend(
        model="test-model",
        base_url="https://api.example.com",
        api_key="test-key",
        timeout_s=3.0,
        max_retries=0,
    )
    backend_b = factory._build_openai_backend(
        model="test-model",
        base_url="https://api.example.com/",
        api_key="test-key",
        timeout_s=3.0,
        max_retries=0,
    )

    assert backend_a is backend_b


def test_build_openai_backend_applies_defaults_and_reset() -> None:
    factory.reset_llm_cache()
    backend_a = factory._build_openai_backend(
        model="test-model",
        base_url="",
        api_key="test-key",
        timeout_s=2.0,
        max_retries=0,
    )

    assert getattr(backend_a, "config").base_url == "https://api.openai.com/v1"
    assert getattr(backend_a, "config").model == "test-model"

    factory.reset_llm_cache()
    backend_b = factory._build_openai_backend(
        model="test-model",
        base_url="",
        api_key="test-key",
        timeout_s=2.0,
        max_retries=0,
    )
    assert backend_a is not backend_b
