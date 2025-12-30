from __future__ import annotations

from src.agent.memory_optimizer import MemoryDeduplicator


def test_memory_deduplicator_max_seen_hashes_eviction():
    dedup = MemoryDeduplicator(max_seen_hashes=3)

    h1 = dedup.get_content_hash("one")
    assert dedup.add_memory("one") is True
    assert dedup.contains_hash(h1) is True

    assert dedup.add_memory("two") is True
    assert dedup.add_memory("three") is True

    # 触发淘汰
    assert dedup.add_memory("four") is True
    assert len(dedup.seen_hashes) == 3
    assert dedup.contains_hash(h1) is False
