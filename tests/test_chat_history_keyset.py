from __future__ import annotations

import json
from pathlib import Path

from src.auth.user_data_manager import UserDataManager


def test_get_chat_history_page_paginates_by_before_id(temp_dir: Path) -> None:
    manager = UserDataManager(db_path=str(temp_dir / "user_data.db"), use_pool=False)

    user_id = 1
    contact = "Alice"
    manager.add_contact(user_id, contact)

    messages = [
        {"user_id": user_id, "contact_name": contact, "role": "user", "content": f"m{i}"}
        for i in range(1, 51)
    ]
    manager.add_messages_batch(messages)

    page1 = manager.get_chat_history_page(user_id, contact, limit=10, before_id=None)
    assert [m["content"] for m in page1] == [f"m{i}" for i in range(41, 51)]
    assert page1[0]["id"] < page1[-1]["id"]

    before_id = page1[0]["id"]
    page2 = manager.get_chat_history_page(user_id, contact, limit=10, before_id=before_id)
    assert [m["content"] for m in page2] == [f"m{i}" for i in range(31, 41)]

    before_id_2 = page2[0]["id"]
    page3 = manager.get_chat_history_page(user_id, contact, limit=10, before_id=before_id_2)
    assert [m["content"] for m in page3] == [f"m{i}" for i in range(21, 31)]


def test_export_user_data_includes_full_chat_history(temp_dir: Path) -> None:
    manager = UserDataManager(db_path=str(temp_dir / "user_data.db"), use_pool=False)

    user_id = 1
    contact = "Alice"
    manager.add_contact(user_id, contact)

    messages = [
        {"user_id": user_id, "contact_name": contact, "role": "user", "content": f"m{i}"}
        for i in range(1, 151)
    ]
    inserted = manager.add_messages_batch(messages)
    assert inserted == len(messages)

    export_dir = temp_dir / "exports"
    export_path = manager.export_user_data(user_id, export_dir=str(export_dir))
    assert export_path is not None

    payload = json.loads(Path(export_path).read_text(encoding="utf-8"))
    assert payload["user_id"] == user_id
    assert payload["chat_history"][contact]
    assert len(payload["chat_history"][contact]) == len(messages)

