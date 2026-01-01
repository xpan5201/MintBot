from __future__ import annotations

from pathlib import Path

from src.auth.database import UserDatabase


def test_update_ai_avatar_normalizes_and_is_idempotent(temp_dir: Path) -> None:
    db_path = temp_dir / "users.db"
    db = UserDatabase(db_path=str(db_path), use_prepared=False)

    user_id = db.create_user("user1", "user1@example.com", "pass123")
    assert user_id is not None

    assert db.update_ai_avatar(user_id, "🐶") is True
    assert db.get_user_avatars(user_id) == {"user_avatar": "👤", "ai_avatar": "🐶"}

    # setting to the same value should still report success
    assert db.update_ai_avatar(user_id, "🐶") is True
    assert db.get_user_avatars(user_id) == {"user_avatar": "👤", "ai_avatar": "🐶"}

    # blank/whitespace should fall back to default
    assert db.update_ai_avatar(user_id, "   ") is True
    assert db.get_user_avatars(user_id) == {"user_avatar": "👤", "ai_avatar": "🐱"}


def test_update_user_avatar_trims_and_limits_length(temp_dir: Path) -> None:
    db_path = temp_dir / "users.db"
    db = UserDatabase(db_path=str(db_path), use_prepared=False)

    user_id = db.create_user("user1", "user1@example.com", "pass123")
    assert user_id is not None

    assert db.update_user_avatar(user_id, "  😺  ") is True
    assert db.get_user_avatars(user_id) == {"user_avatar": "😺", "ai_avatar": "🐱"}

    long_value = "a" * 600
    assert db.update_user_avatar(user_id, long_value) is True
    avatars = db.get_user_avatars(user_id)
    assert avatars is not None
    assert len(avatars["user_avatar"]) == 512
