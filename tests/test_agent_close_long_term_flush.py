from __future__ import annotations

from collections import deque
from concurrent.futures import Future
from threading import Lock

from src.agent.core import MintChatAgent


def test_agent_close_drains_long_term_write_buffer_and_flushes() -> None:
    agent = MintChatAgent.__new__(MintChatAgent)

    drained: list[dict] = []

    class DummyLongTerm:
        def __init__(self) -> None:
            self.flush_calls = 0

        def flush_batch(self) -> int:
            self.flush_calls += 1
            return 0

    class DummyMemory:
        def __init__(self) -> None:
            self.long_term = DummyLongTerm()

        def add_interaction_long_term(self, **kwargs: object) -> bool:
            drained.append(dict(kwargs))
            return True

        def add_interaction(self, **kwargs: object) -> None:
            drained.append(dict(kwargs))

        def cleanup_cache(self) -> None:
            return None

    agent.memory = DummyMemory()  # type: ignore[assignment]
    agent._long_term_write_lock = Lock()  # type: ignore[assignment]
    agent._long_term_write_buffer = deque(  # type: ignore[assignment]
        [
            ("u1", "a1", None),
            ("u2", "a2", 0.7),
        ]
    )
    fut: Future = Future()
    fut.set_result(None)
    agent._pending_long_term_write = fut  # type: ignore[assignment]

    agent.close()

    assert [item.get("user_message") for item in drained[:2]] == ["u1", "u2"]
    assert agent.memory.long_term.flush_calls >= 1  # type: ignore[attr-defined]
    assert len(agent._long_term_write_buffer) == 0  # type: ignore[arg-type]
