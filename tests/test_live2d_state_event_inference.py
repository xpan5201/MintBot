from __future__ import annotations


from src.gui.live2d_state_event import infer_state_event_from_text


def test_infer_state_event_from_text_basic() -> None:
    assert infer_state_event_from_text("我好晕呀") == ("dizzy", 0.82)
    assert infer_state_event_from_text("害羞///") == ("shy", 0.86)
    assert infer_state_event_from_text("我超喜欢你！") == ("love", 0.84)


def test_infer_state_event_from_text_negation_ignored() -> None:
    # Negated emotions should not trigger (roleplay often uses "别/不要/不" to calm down).
    assert infer_state_event_from_text("别生气啦") is None
    assert infer_state_event_from_text("不要哭哭") is None
    assert infer_state_event_from_text("不用害羞啦") is None


def test_infer_state_event_from_text_last_emotion_wins() -> None:
    # Prefer the emotion appearing later in the text when multiple are present.
    assert infer_state_event_from_text("我有点难过…但我还是很喜欢你") == ("love", 0.84)
    assert infer_state_event_from_text("别难过啦，我喜欢你") == ("love", 0.84)


def test_infer_state_event_from_text_angry_overrides_generic_love() -> None:
    # Roleplay replies often end with affectionate words; keep an explicit angry signal readable.
    assert infer_state_event_from_text("我生气了…但我还是喜欢你") == ("angry", 0.92)


def test_infer_state_event_from_text_yes_no_gesture_fallback() -> None:
    assert infer_state_event_from_text("好的") == ("nod", 0.65)
    assert infer_state_event_from_text("可以") == ("nod", 0.65)
    assert infer_state_event_from_text("不行") == ("shake", 0.65)
    assert infer_state_event_from_text("不可以") == ("shake", 0.65)
