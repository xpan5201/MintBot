from __future__ import annotations

from src.agent.core import MintChatAgent
from src.config.settings import settings


def test_save_interaction_to_memory_schedules_background_tasks(monkeypatch) -> None:
    monkeypatch.setattr(settings.agent, "memory_fast_mode", False, raising=False)
    monkeypatch.setattr(settings.agent, "lore_books", True, raising=False)
    monkeypatch.setattr(settings.agent, "auto_learn_from_conversation", True, raising=False)

    agent = MintChatAgent.__new__(MintChatAgent)

    calls: list[tuple[str, object]] = []

    class DummyMemory:
        def add_interaction(self, **kwargs: object) -> None:
            calls.append(("memory.add_interaction", kwargs))

    class DummyDiary:
        vectorstore = object()
        daily_summary_enabled = True

        def add_diary_entry(self, _text: str) -> None:  # pragma: no cover
            raise AssertionError("diary entry should be scheduled in background")

        def generate_daily_summary(self) -> None:  # pragma: no cover
            raise AssertionError("daily summary should be scheduled in background")

    class DummyLore:
        def learn_from_conversation(
            self, *_args: object, **_kwargs: object
        ) -> None:  # pragma: no cover
            raise AssertionError("lore learning should be scheduled in background")

    submitted: list[str] = []

    def submit_task(func, *, label: str):
        submitted.append(label)
        # Do not run the task here; we only verify it is not executed synchronously.
        return None

    agent.memory = DummyMemory()  # type: ignore[assignment]
    agent.diary_memory = DummyDiary()  # type: ignore[assignment]
    agent.lore_book = DummyLore()  # type: ignore[assignment]
    agent._submit_background_task = submit_task  # type: ignore[assignment]

    agent._save_interaction_to_memory("hi", "ok", save_to_long_term=False)

    assert [name for name, _ in calls] == ["memory.add_interaction"]
    assert submitted == ["post-persist"]


def test_save_stream_interaction_schedules_background_tasks(monkeypatch) -> None:
    monkeypatch.setattr(settings.agent, "memory_fast_mode", False, raising=False)
    monkeypatch.setattr(settings.agent, "lore_books", True, raising=False)
    monkeypatch.setattr(settings.agent, "auto_learn_from_conversation", True, raising=False)

    agent = MintChatAgent.__new__(MintChatAgent)

    calls: list[tuple[str, object]] = []

    class DummyMemory:
        def add_interaction(self, **kwargs: object) -> None:
            calls.append(("memory.add_interaction", kwargs))

    class DummyDiary:
        vectorstore = object()
        daily_summary_enabled = True

        def add_diary_entry(self, _text: str) -> None:  # pragma: no cover
            raise AssertionError("diary entry should be scheduled in background")

        def generate_daily_summary(self) -> None:  # pragma: no cover
            raise AssertionError("daily summary should be scheduled in background")

    class DummyLore:
        def learn_from_conversation(
            self, *_args: object, **_kwargs: object
        ) -> None:  # pragma: no cover
            raise AssertionError("lore learning should be scheduled in background")

    submitted: list[str] = []

    def submit_task(func, *, label: str):
        submitted.append(label)
        return None

    agent.memory = DummyMemory()  # type: ignore[assignment]
    agent.diary_memory = DummyDiary()  # type: ignore[assignment]
    agent.lore_book = DummyLore()  # type: ignore[assignment]
    agent._submit_background_task = submit_task  # type: ignore[assignment]

    agent._save_stream_interaction("hi", "ok", save_to_long_term=False)

    assert [name for name, _ in calls] == ["memory.add_interaction"]
    assert submitted == ["post-persist"]
