from __future__ import annotations

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

