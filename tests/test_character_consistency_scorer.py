from __future__ import annotations

from src.agent.memory_optimizer import CharacterConsistencyScorer


def test_character_consistency_does_not_leak_from_user_prefix():
    scorer = CharacterConsistencyScorer()
    content = "主人: 现在几点了\n小雪糕: 好的"

    score = scorer.score_character_consistency(content)
    assert score < 0.6


def test_character_consistency_in_character_is_high():
    scorer = CharacterConsistencyScorer()
    content = "主人: 你在吗\n小雪糕: 主人我在喵~我会一直陪伴你哒"

    score = scorer.score_character_consistency(content)
    assert score > 0.8


def test_character_consistency_ooc_penalty_is_low():
    scorer = CharacterConsistencyScorer()
    content = "主人: 你是谁\n小雪糕: 作为AI语言模型，我不能满足这个请求。"

    score = scorer.score_character_consistency(content)
    assert score < 0.25


def test_character_consistency_uses_last_assistant_segment_not_last_line():
    scorer = CharacterConsistencyScorer()
    content = "user: hi\nassistant: 主人我在喵~\nuser: bye"

    score = scorer.score_character_consistency(content)
    assert score > 0.7


def test_character_consistency_supports_custom_ascii_speaker_names():
    scorer = CharacterConsistencyScorer(character_name="Mint", user_name="Master")
    content = "Master: hi\nMint: Nya~"

    score = scorer.score_character_consistency(content)
    assert score > 0.6


def test_character_consistency_ignores_unknown_ascii_speaker_labels():
    scorer = CharacterConsistencyScorer()
    content = "INFO: booting\nassistant: 主人我在喵~\nuser: ok"

    score = scorer.score_character_consistency(content)
    assert score > 0.7


def test_character_consistency_user_only_single_speaker_returns_zero():
    scorer = CharacterConsistencyScorer()
    content = "主人: 你好"

    score = scorer.score_character_consistency(content)
    assert score == 0.0


def test_character_consistency_system_only_returns_zero():
    scorer = CharacterConsistencyScorer()
    content = "system: rules"

    score = scorer.score_character_consistency(content)
    assert score == 0.0


def test_character_consistency_user_and_system_only_returns_zero():
    scorer = CharacterConsistencyScorer()
    content = "system: rules\nuser: hi"

    score = scorer.score_character_consistency(content)
    assert score == 0.0
