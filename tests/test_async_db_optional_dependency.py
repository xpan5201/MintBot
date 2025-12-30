from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def test_async_db_module_imports_without_aiosqlite() -> None:
    async_db = importlib.import_module("src.utils.async_db")

    assert isinstance(async_db.HAS_AIOSQLITE, bool)

    if not async_db.HAS_AIOSQLITE:
        with pytest.raises(RuntimeError):
            async_db.get_async_db_pool(Path("test.db"))
