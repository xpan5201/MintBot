from __future__ import annotations

import json
from pathlib import Path

from src.agent.core import MintChatAgent


class _StubMemory:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def import_from_data(self, data, *, overwrite_long_term, replace_short_term):  # noqa: ANN001
        self.calls.append(
            {
                "overwrite_long_term": overwrite_long_term,
                "replace_short_term": replace_short_term,
                "keys": sorted(list(data.keys())),
            }
        )
        return {"short_term": 1, "long_term": 2}


class _StubCore:
    def import_records(self, records, *, overwrite):  # noqa: ANN001
        assert overwrite is True
        assert isinstance(records, list)
        return 3


def test_agent_import_memory_reads_pack_and_delegates(temp_dir: Path):
    agent = MintChatAgent.__new__(MintChatAgent)
    agent.memory = _StubMemory()
    agent.core_memory = _StubCore()

    payload = {
        "format_version": 3,
        "short_term": [{"role": "user", "content": "hi"}],
        "long_term": {"items": [{"id": "x", "content": "m", "metadata": {}}]},
        "advanced_memory": {
            "core_memory": {"items": [{"id": "c", "content": "cc", "metadata": {}}]},
        },
    }

    path = temp_dir / "pack.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    stats = agent.import_memory(str(path), overwrite=True)
    assert stats == {"short_term": 1, "long_term": 2, "core_memory": 3}
