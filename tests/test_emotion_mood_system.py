import json
from datetime import datetime, timedelta

import pytest

from src.agent.emotion import EmotionEngine, EmotionType
from src.agent.mood_system import MoodSystem, PAD_BASELINE
from src.config.settings import settings


def test_mood_natural_decay_targets_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr(settings.agent, "mood_persists", False, raising=False)

    mood = MoodSystem(persist_file=str(tmp_path / "mood_state.json"))
    mood.pad_state.pleasure = 1.0
    mood.pad_state.arousal = 1.0
    mood.pad_state.dominance = 1.0
    mood.mood_value = mood.pad_state.to_mood_value()
    mood.last_update_time = datetime.now() - timedelta(seconds=100_000)

    mood._apply_natural_decay()

    assert abs(mood.pad_state.pleasure - PAD_BASELINE.pleasure) < 1e-3
    assert abs(mood.pad_state.arousal - PAD_BASELINE.arousal) < 1e-3
    assert abs(mood.pad_state.dominance - PAD_BASELINE.dominance) < 1e-3
    assert mood.mood_value == pytest.approx(mood.pad_state.to_mood_value())


def test_mood_value_is_consistent_with_pad_after_update(tmp_path, monkeypatch):
    monkeypatch.setattr(settings.agent, "mood_persists", False, raising=False)

    mood = MoodSystem(persist_file=str(tmp_path / "mood_state.json"))
    mood.update_mood(impact=0.8, reason="test", is_positive=False)

    assert mood.mood_value == pytest.approx(mood.pad_state.to_mood_value())


def test_mood_reset_consistent(tmp_path, monkeypatch):
    monkeypatch.setattr(settings.agent, "mood_persists", False, raising=False)

    mood = MoodSystem(persist_file=str(tmp_path / "mood_state.json"))
    mood.update_mood(impact=0.5, reason="before reset", is_positive=False)
    mood.reset_mood()

    assert mood.mood_history == []
    assert mood.mood_value == pytest.approx(mood.pad_state.to_mood_value())


def test_mood_history_is_capped(tmp_path, monkeypatch):
    monkeypatch.setattr(settings.agent, "mood_persists", False, raising=False)
    monkeypatch.setattr(settings.agent, "mood_history_max_len", 3, raising=False)

    mood = MoodSystem(persist_file=str(tmp_path / "mood_state.json"))
    for i in range(6):
        mood.update_mood(impact=0.2, reason=f"#{i}", is_positive=True)

    assert len(mood.mood_history) == 3


def test_mood_persist_throttle(tmp_path, monkeypatch):
    persist_path = tmp_path / "mood_state.json"
    monkeypatch.setattr(settings.agent, "mood_persists", True, raising=False)
    monkeypatch.setattr(settings.agent, "mood_persist_interval_s", 10.0, raising=False)

    import src.agent.mood_system as mood_mod

    now = {"t": 1000.0}
    monkeypatch.setattr(mood_mod.time, "monotonic", lambda: now["t"])

    mood = mood_mod.MoodSystem(persist_file=str(persist_path))
    mood.update_mood(impact=0.3, reason="first", is_positive=True)
    first = persist_path.read_text(encoding="utf-8")

    now["t"] = 1000.1
    mood.update_mood(impact=0.3, reason="second", is_positive=True)
    second = persist_path.read_text(encoding="utf-8")

    assert second == first

    now["t"] = 1011.0
    mood.update_mood(impact=0.3, reason="third", is_positive=True)
    third = persist_path.read_text(encoding="utf-8")

    assert third != first
    json.loads(third)


def test_emotion_persist_throttle(tmp_path, monkeypatch):
    persist_path = tmp_path / "emotion_state.json"
    monkeypatch.setattr(settings.agent, "emotion_persist_interval_s", 10.0, raising=False)

    import src.agent.emotion as emotion_mod

    now = {"t": 1000.0}
    monkeypatch.setattr(emotion_mod.time, "monotonic", lambda: now["t"])

    engine = EmotionEngine(persist_file=str(persist_path))
    engine.update_emotion(EmotionType.HAPPY, 0.9, trigger="first")
    first = persist_path.read_text(encoding="utf-8")

    now["t"] = 1000.1
    engine.update_emotion(EmotionType.SAD, 0.9, trigger="second")
    second = persist_path.read_text(encoding="utf-8")

    assert second == first

    now["t"] = 1011.0
    engine.update_emotion(EmotionType.HAPPY, 0.9, trigger="third")
    third = persist_path.read_text(encoding="utf-8")

    assert third != first
    json.loads(third)


def test_emotion_intensity_estimation_is_reasonable(tmp_path):
    engine = EmotionEngine(persist_file=str(tmp_path / "emotion_state.json"))
    low = engine.estimate_message_intensity("好", EmotionType.HAPPY)
    high = engine.estimate_message_intensity("太好了！！！", EmotionType.HAPPY)
    assert 0.0 <= low <= 1.0
    assert 0.0 <= high <= 1.0
    assert high > low


def test_emotion_negative_interaction_detection(tmp_path):
    engine = EmotionEngine(persist_file=str(tmp_path / "emotion_state.json"))
    assert engine.is_negative_interaction("滚开", EmotionType.HAPPY)
    assert engine.is_negative_interaction("走开！别烦我！", EmotionType.ANGRY)
    assert not engine.is_negative_interaction("我有点难过", EmotionType.SAD)
