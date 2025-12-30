from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", "iic/SenseVoiceSmall"),
        ("SenseVoice-Small", "iic/SenseVoiceSmall"),
        ("sensevoicesmall", "iic/SenseVoiceSmall"),
        ("FunAudioLLM/SenseVoiceSmall", "iic/SenseVoiceSmall"),
        ("funaudiollm/sensevoicesmall", "iic/SenseVoiceSmall"),
        ("'FunAudioLLM/SenseVoiceSmall'", "iic/SenseVoiceSmall"),
        ('"FunAudioLLM/SenseVoiceSmall"', "iic/SenseVoiceSmall"),
        ("ls.FunAudioLLM/SenseVoiceSmall'", "iic/SenseVoiceSmall"),
        ("fun-asr-nano-2512", "FunAudioLLM/Fun-ASR-Nano-2512"),
        ("some-owner/some-model", "some-owner/some-model"),
    ],
)
def test_normalize_model_id_handles_common_mistakes(raw: str, expected: str) -> None:
    import src.multimodal.asr_initializer as mod

    assert mod._normalize_model_id(raw) == expected
