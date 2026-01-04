from __future__ import annotations

from types import SimpleNamespace

from src.llm_native.backend import BackendConfig, ChatRequest
from src.llm_native.events import DoneEvent, TextDeltaEvent, ToolCallDeltaEvent
from src.llm_native.messages import Message
from src.llm_native.openai_backend import OpenAICompatibleBackend, _normalize_base_url


class DummyStream:
    def __init__(self, events) -> None:  # noqa: ANN001 - test stub
        self._events = list(events or [])

    def __enter__(self):  # noqa: ANN204 - test stub
        return self

    def __exit__(self, exc_type, exc, tb):  # noqa: ANN001 - test stub
        return False

    def __iter__(self):  # noqa: ANN204 - test stub
        return iter(self._events)


class DummyChatCompletions:
    def __init__(
        self, *, complete_response=None, stream_chunks=None, stream_events=None, stream_error=None
    ) -> None:
        self._complete_response = complete_response
        self._stream_chunks = list(stream_chunks or [])
        self._stream_events = list(stream_events or []) if stream_events is not None else []
        self._stream_error = stream_error
        if stream_events is None:
            # Disable the SDK `.stream()` helper for this instance so we can exercise the
            # `.create(stream=True)` fallback path.
            self.stream = None  # type: ignore[assignment]

    def create(self, **kwargs):  # noqa: ANN003 - test stub
        if kwargs.get("stream"):
            return iter(self._stream_chunks)
        return self._complete_response

    def stream(self, **kwargs):  # noqa: ANN003 - test stub
        if self._stream_error is not None:
            raise self._stream_error
        return DummyStream(self._stream_events)


class DummyClient:
    def __init__(
        self, *, complete_response=None, stream_chunks=None, stream_events=None, stream_error=None
    ) -> None:
        self.chat = SimpleNamespace(
            completions=DummyChatCompletions(
                complete_response=complete_response,
                stream_chunks=stream_chunks,
                stream_events=stream_events,
                stream_error=stream_error,
            )
        )
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_normalize_base_url_adds_v1_for_bare_host():
    assert _normalize_base_url("https://api.example.com") == "https://api.example.com/v1"
    assert _normalize_base_url("https://api.example.com/") == "https://api.example.com/v1"
    assert _normalize_base_url("https://api.example.com/v1") == "https://api.example.com/v1"
    assert _normalize_base_url("localhost:8000") == "localhost:8000"


def test_openai_backend_close_is_best_effort():
    client = DummyClient(complete_response=None, stream_chunks=[])
    backend = OpenAICompatibleBackend(
        BackendConfig(base_url="", api_key="k", model="m"),
        client=client,
    )
    backend.close()
    assert client.closed is True


def test_openai_backend_complete_returns_text_and_finish_reason():
    resp = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content="hello"),
            )
        ]
    )
    client = DummyClient(complete_response=resp, stream_chunks=[])
    backend = OpenAICompatibleBackend(
        BackendConfig(base_url="", api_key="k", model="m"),
        client=client,
    )
    out = backend.complete(ChatRequest(messages=[Message(role="user", content="hi")]))
    assert out.output_text == "hello"
    assert out.finish_reason == "stop"


def test_openai_backend_stream_emits_text_and_tool_deltas():
    tool_call = SimpleNamespace(
        index=0,
        id="call_1",
        function=SimpleNamespace(name="get_weather", arguments="{"),
        type="function",
    )
    chunks = [
        SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="he"), finish_reason=None)]
        ),
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(tool_calls=[tool_call]),
                    finish_reason=None,
                )
            ]
        ),
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(
                        function_call=SimpleNamespace(name="legacy", arguments="{}")
                    ),
                    finish_reason=None,
                )
            ]
        ),
        SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="llo"), finish_reason="stop")]
        ),
    ]

    client = DummyClient(complete_response=None, stream_chunks=chunks)
    backend = OpenAICompatibleBackend(
        BackendConfig(base_url="", api_key="k", model="m"),
        client=client,
    )

    events = list(backend.stream(ChatRequest(messages=[Message(role="user", content="hi")])))

    assert any(isinstance(e, TextDeltaEvent) and e.delta == "he" for e in events)
    assert any(isinstance(e, TextDeltaEvent) and e.delta == "llo" for e in events)

    tool_events = [e for e in events if isinstance(e, ToolCallDeltaEvent)]
    assert len(tool_events) == 2
    assert tool_events[0].index == 0
    assert tool_events[0].tool_call_id == "call_1"
    assert tool_events[0].name == "get_weather"
    assert tool_events[0].arguments_delta == "{"
    assert tool_events[1].name == "legacy"
    assert tool_events[1].arguments_delta == "{}"

    assert isinstance(events[-1], DoneEvent)
    assert events[-1].finish_reason == "stop"


def test_openai_backend_stream_emits_heartbeat_for_role_only_chunks():
    chunks = [
        SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(role="assistant"), finish_reason=None)]
        ),
        SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="hello"), finish_reason="stop")]
        ),
    ]

    client = DummyClient(complete_response=None, stream_chunks=chunks)
    backend = OpenAICompatibleBackend(
        BackendConfig(base_url="", api_key="k", model="m"),
        client=client,
    )

    events = list(backend.stream(ChatRequest(messages=[Message(role="user", content="hi")])))

    assert isinstance(events[0], TextDeltaEvent)
    assert events[0].delta == ""
    assert any(isinstance(e, TextDeltaEvent) and e.delta == "hello" for e in events)
    assert isinstance(events[-1], DoneEvent)
    assert events[-1].finish_reason == "stop"


def test_openai_backend_stream_prefers_sdk_stream_helper_when_available():
    chunks = [
        SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="hi"), finish_reason=None)]
        ),
        SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="!"), finish_reason="stop")]
        ),
    ]
    stream_events = [
        SimpleNamespace(type="chunk", chunk=chunks[0], snapshot=None),
        SimpleNamespace(type="chunk", chunk=chunks[1], snapshot=None),
    ]

    # Provide no `.create(stream=True)` chunks so the test would fail unless the backend uses
    # the `.stream()` helper.
    client = DummyClient(complete_response=None, stream_chunks=[], stream_events=stream_events)
    backend = OpenAICompatibleBackend(
        BackendConfig(base_url="", api_key="k", model="m"),
        client=client,
    )

    events = list(backend.stream(ChatRequest(messages=[Message(role="user", content="yo")])))
    assert any(isinstance(e, TextDeltaEvent) and e.delta == "hi" for e in events)
    assert any(isinstance(e, TextDeltaEvent) and e.delta == "!" for e in events)
    assert isinstance(events[-1], DoneEvent)
    assert events[-1].finish_reason == "stop"


def test_openai_backend_stream_falls_back_to_create_on_stream_assertion_error():
    chunks = [
        SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="hi"), finish_reason=None)]
        ),
        SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="!"), finish_reason="stop")]
        ),
    ]

    client = DummyClient(
        complete_response=None,
        stream_chunks=chunks,
        stream_events=[],
        stream_error=AssertionError(),
    )
    backend = OpenAICompatibleBackend(
        BackendConfig(base_url="", api_key="k", model="m"),
        client=client,
    )

    events = list(backend.stream(ChatRequest(messages=[Message(role="user", content="yo")])))
    assert any(isinstance(e, TextDeltaEvent) and e.delta == "hi" for e in events)
    assert any(isinstance(e, TextDeltaEvent) and e.delta == "!" for e in events)
    assert isinstance(events[-1], DoneEvent)
    assert events[-1].finish_reason == "stop"
