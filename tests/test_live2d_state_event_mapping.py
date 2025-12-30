from __future__ import annotations


from src.gui.live2d_gl_widget import (
    _choose_expression_file_for_event,
    _event_key_for_hit_parts,
    _gesture_kind_for_event,
)


def test_choose_expression_file_for_event_direct_name() -> None:
    available = [
        "生气.exp3.json",
        "脸红.exp3.json",
        "晕.exp3.json",
        "心心眼.exp3.json",
        "哭哭.exp3.json",
        "星星眼.exp3.json",
    ]
    assert _choose_expression_file_for_event("脸红.exp3.json", available) == "脸红.exp3.json"


def test_choose_expression_file_for_event_semantic_keys() -> None:
    available = [
        "变小.exp3.json",
        "哭哭.exp3.json",
        "打米.exp3.json",
        "耳机.exp3.json",
        "耳朵.exp3.json",
        "花花.exp3.json",
        "钢板.exp3.json",
        "脸红.exp3.json",
        "猫尾.exp3.json",
        "生气.exp3.json",
        "心心眼.exp3.json",
        "小胸.exp3.json",
        "星星眼.exp3.json",
        "雾气.exp3.json",
        "舌头.exp3.json",
        "脸黑.exp3.json",
        "鱼干.exp3.json",
        "晕.exp3.json",
        "只有头.exp3.json",
    ]
    assert _choose_expression_file_for_event("angry", available) == "生气.exp3.json"
    assert _choose_expression_file_for_event("shy", available) == "脸红.exp3.json"
    assert _choose_expression_file_for_event("dizzy", available) == "晕.exp3.json"
    assert _choose_expression_file_for_event("love", available) == "心心眼.exp3.json"
    assert _choose_expression_file_for_event("sad", available) == "哭哭.exp3.json"
    assert _choose_expression_file_for_event("surprise", available) == "星星眼.exp3.json"
    assert _choose_expression_file_for_event("tail", available) == "猫尾.exp3.json"
    assert _choose_expression_file_for_event("ears", available) == "耳朵.exp3.json"
    assert _choose_expression_file_for_event("headphones", available) == "耳机.exp3.json"
    assert _choose_expression_file_for_event("fog", available) == "雾气.exp3.json"
    assert _choose_expression_file_for_event("tongue", available) == "舌头.exp3.json"
    assert _choose_expression_file_for_event("fish", available) == "鱼干.exp3.json"
    assert _choose_expression_file_for_event("small", available) == "变小.exp3.json"
    assert _choose_expression_file_for_event("black", available) == "脸黑.exp3.json"
    assert _choose_expression_file_for_event("rice", available) == "打米.exp3.json"
    assert _choose_expression_file_for_event("flower", available) == "花花.exp3.json"
    assert _choose_expression_file_for_event("armor", available) == "钢板.exp3.json"
    assert _choose_expression_file_for_event("only_head", available) == "只有头.exp3.json"
    assert _choose_expression_file_for_event("small_chest", available) == "小胸.exp3.json"


def test_choose_expression_file_for_event_keyword_token() -> None:
    available = [
        "脸红.exp3.json",
        "生气.exp3.json",
        "心心眼.exp3.json",
        "晕.exp3.json",
    ]
    assert _choose_expression_file_for_event("生气", available) == "生气.exp3.json"
    assert _choose_expression_file_for_event("脸红", available) == "脸红.exp3.json"
    assert _choose_expression_file_for_event("心心眼", available) == "心心眼.exp3.json"
    assert _choose_expression_file_for_event("头晕", available) == "晕.exp3.json"


def test_choose_expression_file_for_event_unknown() -> None:
    available = [
        "脸红.exp3.json",
        "生气.exp3.json",
    ]
    assert _choose_expression_file_for_event("nonexistent", available) is None
    assert _choose_expression_file_for_event("", available) is None
    assert _choose_expression_file_for_event("   ", available) is None


def test_gesture_kind_for_event_mapping() -> None:
    assert _gesture_kind_for_event("nod") == "nod"
    assert _gesture_kind_for_event("shake") == "shake"
    assert _gesture_kind_for_event("yes") == "nod"
    assert _gesture_kind_for_event("no") == "shake"
    assert _gesture_kind_for_event("affirm") == "nod"
    assert _gesture_kind_for_event("deny") == "shake"
    assert _gesture_kind_for_event("肯定") == "nod"
    assert _gesture_kind_for_event("否定") == "shake"
    assert _gesture_kind_for_event("angry") == "shake"
    assert _gesture_kind_for_event("love") == "tilt"


def test_event_key_for_hit_parts_mapping() -> None:
    assert _event_key_for_hit_parts(["PartTail"]) == "tail"
    assert _event_key_for_hit_parts(["PartEarL"]) == "ears"
    assert _event_key_for_hit_parts(["Headphone"]) == "headphones"
    assert _event_key_for_hit_parts(["Tongue"]) == "tongue"
    assert _event_key_for_hit_parts(["FishSnack"]) == "fish"
    assert _event_key_for_hit_parts(["Flower"]) == "flower"
    assert _event_key_for_hit_parts(["ArmorPlate"]) == "armor"
    assert _event_key_for_hit_parts(["BlackFace"]) == "black"
    assert _event_key_for_hit_parts(["猫尾"]) == "tail"
    assert _event_key_for_hit_parts(["SomethingElse"]) is None
