from __future__ import annotations

import json

import langchain_openai

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


def test_build_openai_llm_streaming_false_overrides_extra_config(monkeypatch) -> None:
    factory.reset_llm_cache()

    captured: dict[str, object] = {}
    streaming_sentinel = object()

    class DummyChatOpenAI:  # pragma: no cover - used via monkeypatch
        def __init__(
            self,
            *,
            model: str,
            temperature: float,
            max_completion_tokens: int | None = None,
            base_url: str | None = None,
            api_key: object | None = None,
            streaming: object = streaming_sentinel,
            model_kwargs: dict[str, object] | None = None,
            **kwargs: object,
        ) -> None:
            captured["model"] = model
            captured["temperature"] = temperature
            captured["max_completion_tokens"] = max_completion_tokens
            captured["base_url"] = base_url
            captured["api_key"] = api_key
            captured["streaming"] = streaming
            captured["model_kwargs"] = model_kwargs
            captured.update(kwargs)

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", DummyChatOpenAI)

    factory._build_openai_llm(
        model="test-model",
        temperature=0.0,
        max_tokens=1,
        base_url="https://api.example.com",
        api_key="test-key",
        extra_json=json.dumps({"streaming": True}),
        streaming=False,
    )

    assert captured["streaming"] is streaming_sentinel


def test_build_openai_llm_streaming_none_respects_extra_config(monkeypatch) -> None:
    factory.reset_llm_cache()

    captured: dict[str, object] = {}
    streaming_sentinel = object()

    class DummyChatOpenAI:  # pragma: no cover - used via monkeypatch
        def __init__(
            self,
            *,
            model: str,
            temperature: float,
            max_completion_tokens: int | None = None,
            base_url: str | None = None,
            api_key: object | None = None,
            streaming: object = streaming_sentinel,
            model_kwargs: dict[str, object] | None = None,
            **kwargs: object,
        ) -> None:
            captured["model"] = model
            captured["temperature"] = temperature
            captured["max_completion_tokens"] = max_completion_tokens
            captured["base_url"] = base_url
            captured["api_key"] = api_key
            captured["streaming"] = streaming
            captured["model_kwargs"] = model_kwargs
            captured.update(kwargs)

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", DummyChatOpenAI)

    factory._build_openai_llm(
        model="test-model",
        temperature=0.0,
        max_tokens=1,
        base_url="https://api.example.com",
        api_key="test-key",
        extra_json=json.dumps({"streaming": True}),
        streaming=None,
    )

    assert captured.get("streaming") is True


def test_build_openai_llm_unknown_extra_goes_to_model_kwargs(monkeypatch) -> None:
    factory.reset_llm_cache()

    captured: dict[str, object] = {}
    streaming_sentinel = object()

    class DummyChatOpenAI:  # pragma: no cover - used via monkeypatch
        def __init__(
            self,
            *,
            model: str,
            temperature: float,
            max_completion_tokens: int | None = None,
            base_url: str | None = None,
            api_key: object | None = None,
            streaming: object = streaming_sentinel,
            model_kwargs: dict[str, object] | None = None,
            **kwargs: object,
        ) -> None:
            captured["model"] = model
            captured["temperature"] = temperature
            captured["max_completion_tokens"] = max_completion_tokens
            captured["base_url"] = base_url
            captured["api_key"] = api_key
            captured["streaming"] = streaming
            captured["model_kwargs"] = model_kwargs
            captured.update(kwargs)

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", DummyChatOpenAI)

    factory._build_openai_llm(
        model="test-model",
        temperature=0.0,
        max_tokens=1,
        base_url="https://api.example.com",
        api_key="test-key",
        extra_json=json.dumps({"provider_param": "value"}),
        streaming=None,
    )

    assert captured.get("model_kwargs") == {"provider_param": "value"}
