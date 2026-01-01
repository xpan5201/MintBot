from __future__ import annotations

import secrets
from pathlib import Path

from src.auth.session_store import (
    is_session_token_valid,
    read_session_token,
    write_session_token_file,
)


def test_read_session_token_missing_returns_none(temp_dir: Path) -> None:
    session_file = temp_dir / "session.txt"
    assert read_session_token(session_file) is None


def test_write_and_read_session_token_roundtrip(temp_dir: Path) -> None:
    session_file = temp_dir / "session.txt"
    token = secrets.token_urlsafe(64)
    assert is_session_token_valid(token)
    assert write_session_token_file(session_file, token) is True
    assert read_session_token(session_file) == token


def test_read_session_token_delete_on_invalid_removes_file(temp_dir: Path) -> None:
    session_file = temp_dir / "session.txt"
    session_file.write_text("not valid!!", encoding="utf-8")

    assert read_session_token(session_file, delete_on_invalid=False) is None
    assert session_file.exists()

    assert read_session_token(session_file, delete_on_invalid=True) is None
    assert not session_file.exists()


def test_write_session_token_rejects_invalid_token(temp_dir: Path) -> None:
    session_file = temp_dir / "session.txt"
    assert write_session_token_file(session_file, "bad token") is False
    assert not session_file.exists()
