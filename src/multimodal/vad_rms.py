from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

SilenceThresholdMode = Literal["fixed", "auto"]


def pcm16_mono_rms(pcm_bytes: bytes) -> float:
    """Compute RMS (0-1) from int16 mono PCM bytes."""
    if not pcm_bytes:
        return 0.0
    arr = np.frombuffer(pcm_bytes, dtype=np.int16)
    if arr.size <= 0:
        return 0.0
    wav = arr.astype(np.float32) / 32768.0
    return float(np.sqrt(np.mean(wav * wav)))


@dataclass(frozen=True)
class RmsVadResult:
    rms: float
    threshold: float
    speech_started: bool
    speech_started_now: bool
    endpoint_reached: bool


class RmsVad:
    """Lightweight RMS-based VAD + endpointing for realtime mic audio (int16 mono).

    This is intentionally dependency-light and fast. It is *not* intended to be a perfect VAD,
    but works well for typical "press-to-talk" UX and reduces expensive ASR inference calls.
    """

    def __init__(
        self,
        *,
        sample_rate: int,
        threshold_mode: SilenceThresholdMode = "fixed",
        fixed_threshold: float = 0.006,
        threshold_multiplier: float = 3.0,
        noise_calibration_ms: int = 400,
        min_speech_ms: int = 180,
        endpoint_silence_ms: int = 900,
        pre_roll_ms: int = 250,
        max_utterance_s: float = 25.0,
        recording_pcm: bytearray | None = None,
    ) -> None:
        self.sample_rate = max(8000, int(sample_rate))
        self.bytes_per_second = self.sample_rate * 2  # int16 mono

        self.threshold_mode: SilenceThresholdMode = threshold_mode
        self.fixed_threshold = float(max(0.0, fixed_threshold))
        self.threshold_multiplier = float(max(1.0, threshold_multiplier))

        self.noise_calibration_ms = int(max(0, noise_calibration_ms))
        self.min_speech_ms = int(max(0, min_speech_ms))
        self.endpoint_silence_ms = int(max(0, endpoint_silence_ms))
        self.pre_roll_ms = int(max(0, pre_roll_ms))
        self.max_utterance_s = float(max(0.0, max_utterance_s))

        self.pre_roll_bytes = int(self.bytes_per_second * (self.pre_roll_ms / 1000.0))

        self._pre_roll_pcm = bytearray()
        self.recording_pcm = recording_pcm if recording_pcm is not None else bytearray()

        self._speech_started = False
        self._above_ms = 0
        self._below_ms = 0
        self._calibrated_ms = 0

        # Noise floor estimate used in "auto" mode (RMS). Keep it stable and fast with EMA.
        # Initialize so that threshold starts at fixed_threshold.
        self._noise_rms = self.fixed_threshold / max(self.threshold_multiplier, 1.0)
        self._ema_alpha = 0.15

    @property
    def speech_started(self) -> bool:
        return bool(self._speech_started)

    def captured_audio_bytes(self) -> bytes:
        """Return captured audio bytes for ASR.

        - If speech has started: returns the full recording buffer.
        - Otherwise: returns the current pre-roll buffer (useful when user manually stops quickly).
        """
        if self._speech_started:
            return bytes(self.recording_pcm)
        return bytes(self._pre_roll_pcm)

    def current_threshold(self) -> float:
        if self.threshold_mode == "auto":
            return float(max(self.fixed_threshold, self._noise_rms * self.threshold_multiplier))
        return float(self.fixed_threshold)

    def process_chunk(self, pcm_chunk: bytes) -> RmsVadResult:
        if not pcm_chunk:
            return RmsVadResult(
                rms=0.0,
                threshold=self.current_threshold(),
                speech_started=self.speech_started,
                speech_started_now=False,
                endpoint_reached=False,
            )

        chunk_ms = int(round((len(pcm_chunk) / max(self.bytes_per_second, 1)) * 1000.0))
        chunk_ms = max(0, chunk_ms)
        rms = pcm16_mono_rms(pcm_chunk)

        threshold = self.current_threshold()

        speech_started_now = False
        endpoint_reached = False

        if not self._speech_started:
            # Update noise floor estimate before speech starts.
            if self.threshold_mode == "auto" and (
                self.noise_calibration_ms <= 0 or self._calibrated_ms < self.noise_calibration_ms
            ):
                self._noise_rms = (
                    1.0 - self._ema_alpha
                ) * self._noise_rms + self._ema_alpha * float(rms)
                self._calibrated_ms += chunk_ms
                threshold = self.current_threshold()

            if rms >= threshold:
                self._above_ms += chunk_ms
            else:
                self._above_ms = 0

            if self._above_ms >= self.min_speech_ms:
                self._speech_started = True
                speech_started_now = True
                self._below_ms = 0
                if self._pre_roll_pcm:
                    self.recording_pcm.extend(self._pre_roll_pcm)
                    self._pre_roll_pcm.clear()
                # Always include the current chunk when speech starts (even when pre_roll_ms=0).
                self.recording_pcm.extend(pcm_chunk)
            else:
                # Maintain pre-roll buffer (bounded) so we don't miss the first syllable.
                if self.pre_roll_bytes > 0:
                    self._pre_roll_pcm.extend(pcm_chunk)
                    if len(self._pre_roll_pcm) > self.pre_roll_bytes:
                        drop = len(self._pre_roll_pcm) - self.pre_roll_bytes
                        del self._pre_roll_pcm[:drop]
        else:
            # Once speech has started, keep recording.
            self.recording_pcm.extend(pcm_chunk)

            if rms < threshold:
                self._below_ms += chunk_ms
            else:
                self._below_ms = 0

            if self.endpoint_silence_ms > 0 and self._below_ms >= self.endpoint_silence_ms:
                # Trim the trailing silence so final ASR is faster and cleaner.
                silence_bytes = int(self.bytes_per_second * (self._below_ms / 1000.0))
                if silence_bytes > 0 and silence_bytes < len(self.recording_pcm):
                    del self.recording_pcm[-silence_bytes:]
                endpoint_reached = True

            if not endpoint_reached and self.max_utterance_s > 0.0:
                max_bytes = int(self.bytes_per_second * self.max_utterance_s)
                if max_bytes > 0 and len(self.recording_pcm) >= max_bytes:
                    endpoint_reached = True

        return RmsVadResult(
            rms=float(rms),
            threshold=float(threshold),
            speech_started=self.speech_started,
            speech_started_now=speech_started_now,
            endpoint_reached=endpoint_reached,
        )
