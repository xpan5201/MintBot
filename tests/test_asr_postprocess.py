from __future__ import annotations


def test_postprocess_asr_text_removes_rich_tokens_and_collapses_whitespace(monkeypatch):
    import src.gui.workers.asr_listen as mod

    # Force fallback path so this test is stable across different FunASR versions.
    monkeypatch.setattr(mod, "_RICH_POSTPROCESS", False, raising=False)

    raw = " <|zh|>  hello   \n  world <|HAPPY|> "
    assert mod._postprocess_asr_text(raw) == "hello world"

