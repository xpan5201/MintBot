from __future__ import annotations

from pathlib import Path

from src.auth.user_data_manager import UserDataManager


def test_get_custom_stickers_uses_cache_and_invalidates(temp_dir: Path) -> None:
    db_path = temp_dir / "user_data.db"
    manager = UserDataManager(db_path=str(db_path))

    sticker_file = temp_dir / "sticker.gif"
    sticker_file.write_bytes(b"not-a-real-gif")

    assert manager.add_custom_sticker(
        user_id=1,
        sticker_id="s1",
        file_path=str(sticker_file),
        file_name="sticker",
        file_type=".gif",
        file_size=123,
    )

    first = manager.get_custom_stickers(1)
    assert len(first) == 1

    # 第二次读取应命中缓存，且返回的是拷贝（避免外部修改污染缓存）
    second = manager.get_custom_stickers(1)
    assert len(second) == 1
    assert first is not second
    assert first[0] is not second[0]

    assert manager.update_custom_sticker_caption(user_id=1, sticker_id="s1", caption="开心挥手")
    third = manager.get_custom_stickers(1)
    assert third[0]["caption"] == "开心挥手"

    assert manager.get_sticker_count(1) == 1

    assert manager.delete_custom_sticker(user_id=1, sticker_id="s1")
    assert manager.get_custom_stickers(1) == []
    assert manager.get_sticker_count(1) == 0
