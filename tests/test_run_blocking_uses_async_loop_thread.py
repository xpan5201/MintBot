from __future__ import annotations

import asyncio


def test_run_blocking_does_not_use_asyncio_run(monkeypatch) -> None:
    from src.agent.core import MintChatAgent

    agent = MintChatAgent.__new__(MintChatAgent)

    def boom(*_args, **_kwargs):  # noqa: ANN001
        raise AssertionError("asyncio.run should not be used for _run_blocking()")

    monkeypatch.setattr(asyncio, "run", boom)

    try:
        result = agent._run_blocking(lambda: asyncio.sleep(0, result=123))
    finally:
        loop_thread = getattr(agent, "_async_loop_thread", None)
        if loop_thread is not None:
            loop_thread.close(timeout=1.0)

    assert result == 123
