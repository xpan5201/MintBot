from __future__ import annotations

from pathlib import Path

from src.auth.auth_service import AuthService


def test_auth_service_login_accepts_email(temp_dir: Path) -> None:
    db_path = temp_dir / "users.db"

    service = AuthService(db_path=str(db_path))
    ok, _ = service.register(
        username="user1",
        email="user1@example.com",
        password="pass123",
        confirm_password="pass123",
    )
    assert ok

    # new instance to simulate app restart / fresh login
    service2 = AuthService(db_path=str(db_path))
    ok, _ = service2.login(username="user1@example.com", password="pass123", remember_me=False)
    assert ok
