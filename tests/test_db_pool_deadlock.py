from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading
import time


from src.utils.db_pool import DatabaseConnectionPool


def test_db_pool_get_connection_does_not_deadlock(tmp_path: Path) -> None:
    pool = DatabaseConnectionPool(
        database_path=str(tmp_path / "test.db"),
        max_connections=2,
        warmup=False,
    )

    def worker() -> None:
        with pool.get_connection() as conn:
            conn.execute("SELECT 1")

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(worker)
            future.result(timeout=3.0)
    finally:
        pool.close()


def test_db_pool_concurrent_get_connection_respects_max_connections(tmp_path: Path) -> None:
    pool = DatabaseConnectionPool(
        database_path=str(tmp_path / "test.db"),
        max_connections=2,
        warmup=False,
    )
    start = threading.Barrier(4)

    def worker() -> None:
        start.wait(timeout=2.0)
        with pool.get_connection() as conn:
            conn.execute("SELECT 1")
            time.sleep(0.05)

    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(worker) for _ in range(4)]
            for fut in futures:
                fut.result(timeout=5.0)

        stats = pool.get_stats()
        assert stats["total_connections"] <= 2
        assert stats["active_connections"] == 0
        assert stats["creating_connections"] == 0
        assert stats["pool_size"] <= 2
    finally:
        pool.close()


def test_db_pool_close_does_not_break_active_connection(tmp_path: Path) -> None:
    pool = DatabaseConnectionPool(
        database_path=str(tmp_path / "test.db"),
        max_connections=1,
        warmup=False,
    )
    ready = threading.Event()
    proceed = threading.Event()

    def worker() -> None:
        with pool.get_connection() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER PRIMARY KEY)")
            ready.set()
            proceed.wait(timeout=2.0)
            conn.execute("SELECT 1")

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(worker)
        assert ready.wait(timeout=2.0)
        pool.close()
        proceed.set()
        future.result(timeout=3.0)
