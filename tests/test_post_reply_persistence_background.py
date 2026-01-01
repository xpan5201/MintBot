from __future__ import annotations

from collections import deque
from concurrent.futures import Future
from threading import Lock

from src.agent.core import MintChatAgent


def test_save_stream_interaction_defers_long_term_write() -> None:
    agent = MintChatAgent.__new__(MintChatAgent)

    short_term_calls: list[dict] = []
    long_term_calls: list[dict] = []

    class DummyLongTerm:
        def __init__(self) -> None:
            self.flush_calls = 0

        def flush_batch(self) -> int:
            self.flush_calls += 1
            return 0

    class DummyMemory:
        def __init__(self) -> None:
            self.long_term = DummyLongTerm()

        def add_interaction(self, **kwargs: object) -> None:
            short_term_calls.append(dict(kwargs))

        def add_interaction_long_term(self, **kwargs: object) -> bool:
            long_term_calls.append(dict(kwargs))
            return True

    submitted: list[str] = []
    scheduled: list[tuple[callable, Future]] = []

    def submit_task(func, *, label: str):
        submitted.append(label)
        fut: Future = Future()
        scheduled.append((func, fut))
        return fut

    memory = DummyMemory()
    agent.memory = memory  # type: ignore[assignment]
    agent._submit_background_task = submit_task  # type: ignore[assignment]
    agent._long_term_write_lock = Lock()  # type: ignore[assignment]
    agent._pending_long_term_write = None  # type: ignore[assignment]
    agent._long_term_write_buffer = deque()  # type: ignore[assignment]
    agent._long_term_write_buffer_max = 256  # type: ignore[assignment]

    agent._save_stream_interaction("u1", "a1", save_to_long_term=True)
    agent._save_stream_interaction("u2", "a2", save_to_long_term=True)

    assert len(short_term_calls) == 2
    assert all(call.get("save_to_long_term") is False for call in short_term_calls)
    assert submitted == ["long-term-write"]
    assert len(scheduled) == 1

    func, fut = scheduled[0]
    func()
    fut.set_result(None)

    assert [call.get("user_message") for call in long_term_calls] == ["u1", "u2"]
    assert memory.long_term.flush_calls == 1
