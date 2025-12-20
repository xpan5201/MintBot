from __future__ import annotations

from src.agent.memory import MemoryManager, ShortTermMemory


def test_short_term_memory_keeps_last_k_interactions() -> None:
    mem = ShortTermMemory(k=2)  # keeps last 4 messages (2 user+assistant pairs)
    assert mem.version == 0

    mem.add_messages((("user", "u1"), ("assistant", "a1")))
    assert mem.version == 1

    mem.add_messages((("user", "u2"), ("assistant", "a2")))
    assert mem.version == 2

    mem.add_messages((("user", "u3"), ("assistant", "a3")))
    assert mem.version == 3

    messages = mem.get_messages_as_dict()
    assert [m["content"] for m in messages] == ["u2", "a2", "u3", "a3"]

    mem.clear()
    assert mem.version == 4
    assert mem.get_messages_as_dict() == []


def test_memory_manager_short_term_version_tracks_short_term_memory() -> None:
    mgr = MemoryManager(
        short_term_k=1,
        enable_long_term=False,
        enable_optimizer=False,
        enable_auto_consolidate=False,
    )
    assert mgr.short_term_version == 0

    mgr.add_interaction("u1", "a1", save_to_long_term=False)
    assert mgr.short_term_version == 1
    assert [m["content"] for m in mgr.get_recent_messages()] == ["u1", "a1"]

    mgr.add_interaction("u2", "a2", save_to_long_term=False)
    assert mgr.short_term_version == 2
    # k=1 -> keep last 2 messages (one interaction)
    assert [m["content"] for m in mgr.get_recent_messages()] == ["u2", "a2"]

    mgr.clear_all()
    assert mgr.short_term_version == 3
    assert mgr.get_recent_messages() == []

