from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize(
    ("hub", "trust_remote_code", "expect_passed"),
    [
        ("ms", True, False),
        ("ms", False, False),
        ("hf", True, True),
        ("huggingface", True, True),
        ("hf", False, False),
    ],
)
def test_asr_initializer_trust_remote_code_only_passed_for_hf(
    monkeypatch: pytest.MonkeyPatch,
    hub: str,
    trust_remote_code: bool,
    expect_passed: bool,
):
    import src.multimodal.asr_initializer as mod

    captured: list[dict] = []

    class DummyAutoModel:
        def __init__(self, **kwargs):  # noqa: ANN003
            captured.append(dict(kwargs))

    # Patch `funasr` import inside init_asr()
    monkeypatch.setitem(sys.modules, "funasr", SimpleNamespace(AutoModel=DummyAutoModel))

    # Patch settings used by init_asr() to avoid real model downloads / warmup.
    dummy_asr = SimpleNamespace(
        enabled=True,
        model="iic/SenseVoiceSmall",
        device="cpu",
        hub=hub,
        trust_remote_code=trust_remote_code,
        vad_model="none",
        warmup=False,
        sample_rate=16000,
    )
    monkeypatch.setattr(mod, "settings", SimpleNamespace(asr=dummy_asr))

    ok = mod.init_asr(force=True)
    assert ok is True
    assert captured

    passed = captured[-1]
    assert ("trust_remote_code" in passed) is expect_passed

