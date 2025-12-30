from __future__ import annotations

import sys
from types import SimpleNamespace


def test_asr_initializer_auto_fixes_hub_mismatch_iic_with_hf(monkeypatch):
    import src.multimodal.asr_initializer as mod

    captured: list[dict] = []

    class DummyAutoModel:
        def __init__(self, **kwargs):  # noqa: ANN003
            captured.append(dict(kwargs))

    monkeypatch.setitem(sys.modules, "funasr", SimpleNamespace(AutoModel=DummyAutoModel))

    dummy_asr = SimpleNamespace(
        enabled=True,
        model="iic/SenseVoiceSmall",
        device="cpu",
        hub="hf",  # mismatched on purpose
        trust_remote_code=True,  # should be ignored after hub auto-fix
        vad_model="none",
        warmup=False,
        sample_rate=16000,
    )
    monkeypatch.setattr(mod, "settings", SimpleNamespace(asr=dummy_asr))

    ok = mod.init_asr(force=True)
    assert ok is True
    assert captured

    passed = captured[-1]
    assert passed.get("hub") == "ms"
    assert passed.get("trust_remote_code") is False
