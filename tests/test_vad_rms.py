import threading

import numpy as np

from src.gui.workers.asr_listen import ASRListenThread
from src.multimodal.vad_rms import RmsVad


def _pcm_chunk(*, amplitude: int, duration_ms: int, sample_rate: int = 16000) -> bytes:
    n = int(sample_rate * (duration_ms / 1000.0))
    n = max(0, n)
    arr = np.full((n,), int(amplitude), dtype=np.int16)
    return arr.tobytes()


def test_rms_vad_starts_after_min_speech_ms():
    vad = RmsVad(
        sample_rate=16000,
        threshold_mode="fixed",
        fixed_threshold=0.02,
        min_speech_ms=180,
        endpoint_silence_ms=0,
        pre_roll_ms=200,
        max_utterance_s=60.0,
    )

    # 2x100ms silence -> pre-roll filled, but not started.
    vad.process_chunk(_pcm_chunk(amplitude=0, duration_ms=100))
    assert not vad.speech_started
    vad.process_chunk(_pcm_chunk(amplitude=0, duration_ms=100))
    assert not vad.speech_started

    # 2x100ms speech -> started (>=180ms)
    res1 = vad.process_chunk(_pcm_chunk(amplitude=10000, duration_ms=100))
    assert not res1.speech_started_now
    assert vad.speech_started is False
    res2 = vad.process_chunk(_pcm_chunk(amplitude=10000, duration_ms=100))
    assert res2.speech_started_now
    assert vad.speech_started is True
    assert len(vad.recording_pcm) > 0

    # Pre-roll should make recording longer than pure speech.
    speech_bytes = len(_pcm_chunk(amplitude=10000, duration_ms=200))
    assert len(vad.recording_pcm) > speech_bytes


def test_rms_vad_endpoint_trims_tail_silence():
    vad = RmsVad(
        sample_rate=16000,
        threshold_mode="fixed",
        fixed_threshold=0.02,
        min_speech_ms=100,
        endpoint_silence_ms=200,
        pre_roll_ms=0,
        max_utterance_s=60.0,
    )

    # Start speech.
    vad.process_chunk(_pcm_chunk(amplitude=12000, duration_ms=100))
    assert vad.speech_started

    # 2x100ms silence -> endpoint.
    vad.process_chunk(_pcm_chunk(amplitude=0, duration_ms=100))
    res = vad.process_chunk(_pcm_chunk(amplitude=0, duration_ms=100))
    assert res.endpoint_reached

    # Tail silence should have been trimmed (recording should roughly equal 100ms speech).
    assert len(vad.recording_pcm) == len(_pcm_chunk(amplitude=12000, duration_ms=100))


def test_rms_vad_max_utterance_forces_endpoint():
    vad = RmsVad(
        sample_rate=16000,
        threshold_mode="fixed",
        fixed_threshold=0.02,
        min_speech_ms=0,
        endpoint_silence_ms=0,
        pre_roll_ms=0,
        max_utterance_s=0.25,
    )

    # 3x100ms speech -> exceed 250ms
    vad.process_chunk(_pcm_chunk(amplitude=12000, duration_ms=100))
    vad.process_chunk(_pcm_chunk(amplitude=12000, duration_ms=100))
    res = vad.process_chunk(_pcm_chunk(amplitude=12000, duration_ms=100))
    assert vad.speech_started
    assert res.endpoint_reached


def test_rms_vad_captured_audio_bytes_returns_pre_roll_before_speech():
    vad = RmsVad(
        sample_rate=16000,
        threshold_mode="fixed",
        fixed_threshold=0.02,
        min_speech_ms=1000,  # intentionally large to avoid starting
        endpoint_silence_ms=0,
        pre_roll_ms=200,
        max_utterance_s=60.0,
    )

    chunk = _pcm_chunk(amplitude=12000, duration_ms=100)
    vad.process_chunk(chunk)
    assert not vad.speech_started
    assert vad.captured_audio_bytes() == chunk


def test_asr_listen_infer_text_uses_inference_for_partial_and_generate_for_final():
    class DummyModel:
        def __init__(self):
            self.calls: list[str] = []

        def inference(self, **kwargs):
            self.calls.append("inference")
            return {"text": "hello"}

        def generate(self, **kwargs):
            self.calls.append("generate")
            return {"text": "world"}

    pcm = _pcm_chunk(amplitude=10000, duration_ms=200)
    pcm_view = memoryview(pcm)
    lock = threading.Lock()
    model = DummyModel()

    partial = ASRListenThread._infer_text(model, lock, pcm_view, sample_rate=16000, is_final=False, gen_kwargs={})
    assert partial == "hello"
    assert model.calls == ["inference"]

    model.calls.clear()
    final = ASRListenThread._infer_text(model, lock, pcm_view, sample_rate=16000, is_final=True, gen_kwargs={})
    assert final == "world"
    assert model.calls == ["generate"]
