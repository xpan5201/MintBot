from __future__ import annotations

import pytest


def test_style_learner_persist_false_skips_disk_write(monkeypatch, tmp_path):
    from src.agent import style_learner as style_mod
    from src.agent.style_learner import StyleLearner
    from src.config.settings import settings

    monkeypatch.setattr(settings.agent, "style_learning_enabled", True, raising=False)

    def _boom(*_args, **_kwargs):  # noqa: ANN001
        raise AssertionError("_atomic_write_json should not be called on hot path")

    monkeypatch.setattr(style_mod, "_atomic_write_json", _boom)

    learner = StyleLearner(persist_file=str(tmp_path / "style.json"), user_id=1)
    learner.learn_from_message("hello", persist=False)


def test_character_state_persist_false_skips_disk_write(monkeypatch, tmp_path):
    from src.agent import character_state as state_mod
    from src.agent.character_state import CharacterState

    def _boom(*_args, **_kwargs):  # noqa: ANN001
        raise AssertionError("_atomic_write_json should not be called on hot path")

    monkeypatch.setattr(state_mod, "_atomic_write_json", _boom)

    state = CharacterState(persist_file=str(tmp_path / "state.json"))
    state.on_interaction("chat", persist=False)


def test_agent_pre_interaction_update_defers_persistence():
    from src.agent.core import MintChatAgent

    called = {"style": None, "char": None}

    class _DummyStyleLearner:
        def learn_from_message(self, message: str, persist: bool = True) -> None:  # noqa: ARG002
            called["style"] = persist

    class _DummyCharacterState:
        def on_interaction(
            self, channel: str = "chat", persist: bool = True
        ) -> None:  # noqa: ARG002
            called["char"] = persist

    agent = MintChatAgent.__new__(MintChatAgent)
    agent.style_learner = _DummyStyleLearner()
    agent.character_state = _DummyCharacterState()

    agent._pre_interaction_update("hi", analyze_emotion=False)

    assert called["style"] is False
    assert called["char"] is False
