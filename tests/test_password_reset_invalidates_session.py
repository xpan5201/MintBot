from __future__ import annotations

from pathlib import Path

from src.auth.auth_service import AuthService


def test_reset_password_invalidates_existing_session(temp_dir: Path) -> None:
    db_path = temp_dir / "users.db"
    service = AuthService(db_path=str(db_path))

    ok, _ = service.register(
        username="user1",
        email="user1@example.com",
        password="pass123",
        confirm_password="pass123",
    )
    assert ok

    ok, _ = service.login(username="user1", password="pass123", remember_me=True)
    assert ok
    session_token = service.current_session
    assert session_token

    # Session works before reset
    service2 = AuthService(db_path=str(db_path))
    assert service2.restore_session(session_token) is True

    ok, _ = service.reset_password(
        username="user1",
        email="user1@example.com",
        new_password="newpass123",
        confirm_password="newpass123",
    )
    assert ok

    # Existing session becomes invalid after reset
    service3 = AuthService(db_path=str(db_path))
    assert service3.restore_session(session_token) is False

    # Old password fails; new password succeeds
    service4 = AuthService(db_path=str(db_path))
    ok, _ = service4.login(username="user1", password="pass123", remember_me=False)
    assert not ok
    ok, _ = service4.login(username="user1", password="newpass123", remember_me=False)
    assert ok
