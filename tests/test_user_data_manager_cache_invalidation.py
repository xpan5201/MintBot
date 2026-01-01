from __future__ import annotations

from pathlib import Path

from src.auth.user_data_manager import UserDataManager


def test_contacts_cache_invalidation_does_not_affect_other_user_ids(temp_dir: Path) -> None:
    manager = UserDataManager(db_path=str(temp_dir / "user_data.db"), use_pool=False)
    try:
        manager.add_contact(12, "Bob")
        manager.get_contacts(12)  # warm cache
        assert "contacts_12" in manager._cache  # noqa: SLF001

        manager.add_contact(1, "Alice")  # invalidates contacts_1 only
        assert "contacts_12" in manager._cache  # noqa: SLF001
    finally:
        manager.close()
