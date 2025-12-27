import json

from src.config.settings import settings


def test_character_state_persist_throttle(tmp_path, monkeypatch) -> None:
    persist_path = tmp_path / "character_state.json"
    monkeypatch.setattr(settings.agent, "character_state_persist_interval_s", 10.0, raising=False)

    import src.agent.character_state as state_mod

    now = {"t": 1000.0}
    monkeypatch.setattr(state_mod.time, "monotonic", lambda: now["t"])

    state = state_mod.CharacterState(persist_file=str(persist_path))
    state.on_interaction("chat")
    first = persist_path.read_text(encoding="utf-8")

    now["t"] = 1000.1
    state.on_interaction("chat")
    second = persist_path.read_text(encoding="utf-8")

    assert second == first

    now["t"] = 1011.0
    state.on_interaction("chat")
    third = persist_path.read_text(encoding="utf-8")

    assert third != first
    json.loads(third)

