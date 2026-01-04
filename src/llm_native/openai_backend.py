from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator
from urllib.parse import urlparse

from openai import OpenAI

from .backend import BackendConfig, ChatBackend, ChatRequest, ChatResponse
from .events import DoneEvent, StreamEvent, TextDeltaEvent, ToolCallDeltaEvent


def _normalize_base_url(base_url: str) -> str:
    raw = str(base_url or "").strip()
    if not raw:
        return ""
    raw = raw.rstrip("/")
    try:
        parsed = urlparse(raw)
    except Exception:
        return raw
    if not parsed.scheme or not parsed.netloc:
        return raw
    if parsed.path in ("", "/"):
        return f"{raw}/v1"
    return raw


def _prefer_stream_helper(base_url: str) -> bool:
    """
    Prefer `.chat.completions.stream()` only for official OpenAI endpoints.

    Many third-party "OpenAI-compatible" gateways are compatible with
    `.create(stream=True)` but may emit streaming events that the SDK helper
    does not recognize (e.g., triggering AssertionError via `assert_never`).
    """

    raw = str(base_url or "").strip()
    if not raw:
        return True
    try:
        parsed = urlparse(raw)
    except Exception:
        return True
    host = str(parsed.hostname or "").lower()
    return bool(host.endswith("openai.com"))


@dataclass(slots=True)
class OpenAICompatibleBackend(ChatBackend):
    """
    Native backend using the official OpenAI Python SDK, configured via base_url.

    Notes:
    - Used by MintChatAgent native tool-loop runtime and tests.
    - Supports Chat Completions streaming (content + tool_calls delta).
    """

    config: BackendConfig
    _client: Any

    def __init__(self, config: BackendConfig, *, client: Any | None = None) -> None:
        self.config = config
        kwargs: dict[str, Any] = {
            "base_url": _normalize_base_url(config.base_url) or None,
            "timeout": float(config.timeout_s),
            "max_retries": int(config.max_retries),
        }
        api_key = str(config.api_key or "").strip()
        if api_key:
            kwargs["api_key"] = api_key
        self._client = client or OpenAI(**kwargs)

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass

    def complete(self, request: ChatRequest) -> ChatResponse:
        kwargs = request.to_openai_kwargs()
        kwargs["model"] = self.config.model
        kwargs.pop("stream", None)

        resp = self._client.chat.completions.create(**kwargs)
        choice0 = (getattr(resp, "choices", None) or [None])[0]
        finish_reason = getattr(choice0, "finish_reason", None) if choice0 is not None else None
        msg = getattr(choice0, "message", None) if choice0 is not None else None
        content = getattr(msg, "content", None)
        output_text = "" if content is None else str(content)
        return ChatResponse(
            output_text=output_text, finish_reason=str(finish_reason) if finish_reason else None
        )

    def stream(self, request: ChatRequest) -> Iterator[StreamEvent]:
        kwargs = request.to_openai_kwargs()
        kwargs["model"] = self.config.model

        finish_reason: str | None = None
        completions = getattr(getattr(self._client, "chat", None), "completions", None)
        stream_cm = getattr(completions, "stream", None) if completions is not None else None
        if callable(stream_cm) and _prefer_stream_helper(self.config.base_url):
            # Prefer the SDK helper to ensure response is properly closed and to benefit from
            # upstream filtering/normalization (some gateways may emit non-chunk SSE events).
            emitted_any_chunk = False
            try:
                with stream_cm(**kwargs) as stream:
                    for event in stream:
                        if str(getattr(event, "type", "") or "") != "chunk":
                            continue
                        chunk = getattr(event, "chunk", None)
                        if chunk is None:
                            continue
                        emitted_any_chunk = True
                        emitted_in_chunk = False
                        for choice in getattr(chunk, "choices", None) or []:
                            delta = getattr(choice, "delta", None)
                            if delta is not None:
                                content = getattr(delta, "content", None)
                                if content:
                                    yield TextDeltaEvent(delta=str(content))
                                    emitted_in_chunk = True

                                tool_calls = getattr(delta, "tool_calls", None) or []
                                for tool_call in tool_calls:
                                    function = getattr(tool_call, "function", None)
                                    yield ToolCallDeltaEvent(
                                        index=int(getattr(tool_call, "index", 0)),
                                        tool_call_id=(
                                            str(getattr(tool_call, "id"))
                                            if getattr(tool_call, "id", None)
                                            else None
                                        ),
                                        name=(
                                            str(getattr(function, "name"))
                                            if function is not None
                                            and getattr(function, "name", None)
                                            else None
                                        ),
                                        arguments_delta=(
                                            str(getattr(function, "arguments"))
                                            if function is not None
                                            and getattr(function, "arguments", None)
                                            else None
                                        ),
                                    )
                                    emitted_in_chunk = True

                                function_call = getattr(delta, "function_call", None)
                                if function_call is not None:
                                    yield ToolCallDeltaEvent(
                                        index=0,
                                        tool_call_id=None,
                                        name=(
                                            str(getattr(function_call, "name"))
                                            if getattr(function_call, "name", None)
                                            else None
                                        ),
                                        arguments_delta=(
                                            str(getattr(function_call, "arguments"))
                                            if getattr(function_call, "arguments", None)
                                            else None
                                        ),
                                    )
                                    emitted_in_chunk = True

                            fr = getattr(choice, "finish_reason", None)
                            if fr:
                                finish_reason = str(fr)
                        if not emitted_in_chunk:
                            yield TextDeltaEvent(delta="")
            except AssertionError:
                # Some OpenAI-compatible gateways emit streaming events that the SDK's
                # `.stream()` helper doesn't recognize (it may raise AssertionError via
                # `assert_never`). If we haven't emitted anything yet, fall back to the
                # raw chunk iterator for better compatibility.
                if emitted_any_chunk:
                    raise
                kwargs["stream"] = True
                for chunk in self._client.chat.completions.create(**kwargs):
                    emitted_in_chunk = False
                    for choice in getattr(chunk, "choices", None) or []:
                        delta = getattr(choice, "delta", None)
                        if delta is not None:
                            content = getattr(delta, "content", None)
                            if content:
                                yield TextDeltaEvent(delta=str(content))
                                emitted_in_chunk = True

                            tool_calls = getattr(delta, "tool_calls", None) or []
                            for tool_call in tool_calls:
                                function = getattr(tool_call, "function", None)
                                yield ToolCallDeltaEvent(
                                    index=int(getattr(tool_call, "index", 0)),
                                    tool_call_id=(
                                        str(getattr(tool_call, "id"))
                                        if getattr(tool_call, "id", None)
                                        else None
                                    ),
                                    name=(
                                        str(getattr(function, "name"))
                                        if function is not None and getattr(function, "name", None)
                                        else None
                                    ),
                                    arguments_delta=(
                                        str(getattr(function, "arguments"))
                                        if function is not None
                                        and getattr(function, "arguments", None)
                                        else None
                                    ),
                                )
                                emitted_in_chunk = True

                            function_call = getattr(delta, "function_call", None)
                            if function_call is not None:
                                yield ToolCallDeltaEvent(
                                    index=0,
                                    tool_call_id=None,
                                    name=(
                                        str(getattr(function_call, "name"))
                                        if getattr(function_call, "name", None)
                                        else None
                                    ),
                                    arguments_delta=(
                                        str(getattr(function_call, "arguments"))
                                        if getattr(function_call, "arguments", None)
                                        else None
                                    ),
                                )
                                emitted_in_chunk = True

                        fr = getattr(choice, "finish_reason", None)
                        if fr:
                            finish_reason = str(fr)
                    if not emitted_in_chunk:
                        yield TextDeltaEvent(delta="")
        else:
            kwargs["stream"] = True
            for chunk in self._client.chat.completions.create(**kwargs):
                emitted_in_chunk = False
                for choice in getattr(chunk, "choices", None) or []:
                    delta = getattr(choice, "delta", None)
                    if delta is not None:
                        content = getattr(delta, "content", None)
                        if content:
                            yield TextDeltaEvent(delta=str(content))
                            emitted_in_chunk = True

                        tool_calls = getattr(delta, "tool_calls", None) or []
                        for tool_call in tool_calls:
                            function = getattr(tool_call, "function", None)
                            yield ToolCallDeltaEvent(
                                index=int(getattr(tool_call, "index", 0)),
                                tool_call_id=(
                                    str(getattr(tool_call, "id"))
                                    if getattr(tool_call, "id", None)
                                    else None
                                ),
                                name=(
                                    str(getattr(function, "name"))
                                    if function is not None and getattr(function, "name", None)
                                    else None
                                ),
                                arguments_delta=(
                                    str(getattr(function, "arguments"))
                                    if function is not None and getattr(function, "arguments", None)
                                    else None
                                ),
                            )
                            emitted_in_chunk = True

                        function_call = getattr(delta, "function_call", None)
                        if function_call is not None:
                            yield ToolCallDeltaEvent(
                                index=0,
                                tool_call_id=None,
                                name=(
                                    str(getattr(function_call, "name"))
                                    if getattr(function_call, "name", None)
                                    else None
                                ),
                                arguments_delta=(
                                    str(getattr(function_call, "arguments"))
                                    if getattr(function_call, "arguments", None)
                                    else None
                                ),
                            )
                            emitted_in_chunk = True

                    fr = getattr(choice, "finish_reason", None)
                    if fr:
                        finish_reason = str(fr)
                if not emitted_in_chunk:
                    yield TextDeltaEvent(delta="")

        yield DoneEvent(finish_reason=finish_reason)


__all__ = ["OpenAICompatibleBackend"]
