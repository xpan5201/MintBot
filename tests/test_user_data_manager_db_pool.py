from __future__ import annotations

from pathlib import Path

from src.auth.user_data_manager import UserDataManager


def test_user_data_manager_can_enable_db_pool(temp_dir: Path) -> None:
    manager = UserDataManager(db_path=str(temp_dir / "user_data.db"), use_pool=True)
    try:
        assert manager.use_pool is True
        with manager._get_connection() as conn:  # noqa: SLF001
            cursor = conn.execute("PRAGMA foreign_keys")
            foreign_keys = cursor.fetchone()[0]
            cursor.close()
            assert foreign_keys == 0
        manager.add_contact(1, "Alice")
    finally:
        manager.close()
