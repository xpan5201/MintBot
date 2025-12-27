import json
from pathlib import Path

import pytest

from src.agent.style_learner import StyleLearner
from src.config.settings import settings


def test_style_learner_persist_path_is_user_isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path), raising=False)

    global_learner = StyleLearner()
    assert Path(global_learner.persist_file) == tmp_path / "memory" / "style_profile.json"

    user_learner = StyleLearner(user_id=123)
    assert Path(user_learner.persist_file) == tmp_path / "users" / "123" / "memory" / "style_profile.json"


def test_style_learner_skips_noisy_messages(tmp_path, monkeypatch):
    monkeypatch.setattr(settings.agent, "style_learning_enabled", True, raising=False)
    learner = StyleLearner(persist_file=str(tmp_path / "style_profile.json"))

    learner.learn_from_message("```python\nprint('hello')\n```")
    learner.learn_from_message("2025-12-23 13:06:33.332 | WARNING  | root | callHandlers:1737 | test\nmore\nlines\nhere")
    assert learner.total_interactions == 0

    learner.learn_from_message("你好呀")
    assert learner.total_interactions == 1


def test_style_learner_guidance_gate_and_max_chars(tmp_path, monkeypatch):
    monkeypatch.setattr(settings.agent, "style_learning_enabled", True, raising=False)
    monkeypatch.setattr(settings.agent, "style_guidance_min_interactions", 3, raising=False)
    monkeypatch.setattr(settings.agent, "style_guidance_max_chars", 60, raising=False)
    monkeypatch.setattr(settings.agent, "style_learning_max_message_chars", 800, raising=False)

    learner = StyleLearner(persist_file=str(tmp_path / "style_profile.json"))

    learner.learn_from_message("你好")
    learner.learn_from_message("最近怎么样？")
    assert learner.get_style_guidance() == ""

    learner.learn_from_message("我想吃点好吃的～")
    guidance = learner.get_style_guidance()
    assert guidance
    assert len(guidance) <= 60


def test_style_learner_persist_throttle(tmp_path, monkeypatch):
    monkeypatch.setattr(settings.agent, "style_learning_enabled", True, raising=False)
    monkeypatch.setattr(settings.agent, "style_persist_interval_s", 10.0, raising=False)
    monkeypatch.setattr(settings.agent, "style_persist_every_n_interactions", 999, raising=False)

    import src.agent.style_learner as style_mod

    now = {"t": 1000.0}
    monkeypatch.setattr(style_mod.time, "monotonic", lambda: now["t"])

    persist_path = tmp_path / "style_profile.json"
    learner = style_mod.StyleLearner(persist_file=str(persist_path))

    learner.learn_from_message("你好")
    first = persist_path.read_text(encoding="utf-8")
    json.loads(first)

    now["t"] = 1000.1
    learner.learn_from_message("再来一条")
    second = persist_path.read_text(encoding="utf-8")
    assert second == first

    now["t"] = 1011.0
    learner.learn_from_message("第三条")
    third = persist_path.read_text(encoding="utf-8")
    assert third != first
    json.loads(third)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("你好", "casual"),
        ("请问您现在方便吗？", "formal"),
        ("喵~ 好耶", "cute"),
    ],
)
def test_style_learner_formality_classification(tmp_path, monkeypatch, message, expected):
    monkeypatch.setattr(settings.agent, "style_learning_enabled", True, raising=False)
    monkeypatch.setattr(settings.agent, "style_guidance_min_interactions", 0, raising=False)
    monkeypatch.setattr(settings.agent, "style_learning_max_message_chars", 800, raising=False)
    monkeypatch.setattr(settings.agent, "style_learning_max_message_lines", 12, raising=False)

    learner = StyleLearner(persist_file=str(tmp_path / "style_profile.json"))
    learner.learn_from_message(message)
    assert learner.preferred_formality == expected

