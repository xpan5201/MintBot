from __future__ import annotations

import asyncio

from src.agent import builtin_tools


def test_connection_pool_session_is_reused_in_async_runtime():
    @builtin_tools.async_to_sync
    async def _get_session_id() -> int:
        session = await builtin_tools.ConnectionPool.get_session()
        return id(session)

    try:
        first = _get_session_id()
        second = _get_session_id()
        assert first == second
    finally:
        builtin_tools.shutdown_builtin_tools_runtime()


def test_connection_pool_is_isolated_per_event_loop():
    @builtin_tools.async_to_sync
    async def _get_runtime_session_id() -> int:
        session = await builtin_tools.ConnectionPool.get_session()
        return id(session)

    async def _get_other_loop_session_id() -> int:
        session = await builtin_tools.ConnectionPool.get_session()
        session_id = id(session)
        await builtin_tools.ConnectionPool.close()
        return session_id

    try:
        runtime_session_id = _get_runtime_session_id()
        other_session_id = asyncio.run(_get_other_loop_session_id())
        assert runtime_session_id != other_session_id
    finally:
        builtin_tools.shutdown_builtin_tools_runtime()
